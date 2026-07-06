from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()


def find_app_dir() -> Path:
    for candidate in (SCRIPT_PATH.parent, *SCRIPT_PATH.parents):
        if (candidate / "app" / "configurator.py").is_file():
            return candidate
    raise FileNotFoundError("Could not find app/configurator.py from setup script location")


APP_DIR = find_app_dir()
APP_SOURCE_DIR = APP_DIR / "app"
SOURCE_PROFILES_DIR = APP_DIR / "config" / "profiles"
for import_path in (APP_SOURCE_DIR, APP_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
RUNTIME_MOD_FOLDER = "Configuration_Mod"
DEFAULT_PROFILE = SOURCE_PROFILES_DIR / "Premade_Configuration.json"
DEFAULT_MOD_NAME = RUNTIME_MOD_FOLDER
UE4SS_RELEASES_API = "https://api.github.com/repos/UE4SS-RE/RE-UE4SS/releases"
BUNDLED_UE4SS_DLLS = (
    APP_DIR / "tools" / "ue4ss" / "UE4SS.dll",
    APP_DIR / "tools" / "dll" / "out" / "UE4SS.dll",
)


def user_state_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ZSG Studios" / "IcarusConfigMod"
    return Path.home() / "AppData" / "Local" / "ZSG Studios" / "IcarusConfigMod"


APP_STATE_DIR = user_state_dir()

UE4SS_BUILTIN_MODS_TO_DISABLE = {
    "CheatManagerEnablerMod",
    "ActorDumperMod",
    "ConsoleCommandsMod",
    "ConsoleEnablerMod",
    "SplitScreenMod",
    "LineTraceMod",
    "BPModLoaderMod",
    "BPML_GenericFunctions",
    "jsbLuaProfilerMod",
}

OLD_RUNTIME_MOD_NAMES = {
    "ZSG_Balance_w235_Runtime",
    "ZSG_Balance",
    "ZSG_Balance_Runtime",
    "ConfigurationMod",
    "Configuration_Mod_Runtime",
}

MOD_FOLDERS_TO_CLEAN = UE4SS_BUILTIN_MODS_TO_DISABLE | OLD_RUNTIME_MOD_NAMES


def run(arguments: list[str], cwd: Path | None = None) -> None:
    print("> " + subprocess.list2cmdline(arguments))
    completed = subprocess.run(arguments, cwd=str(cwd) if cwd else None, text=True)
    if completed.returncode:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}")


def backup_path(original: Path) -> Path:
    target = APP_STATE_DIR / "backups" / "runtime_setup" / datetime.now().strftime("%Y%m%d_%H%M%S") / original.name
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def locate_steam_libraries() -> list[Path]:
    roots: list[Path] = []
    steam_roots = [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ]
    for steam in steam_roots:
        library_file = steam / "steamapps" / "libraryfolders.vdf"
        if not library_file.is_file():
            continue
        roots.append(steam)
        text = library_file.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if '"path"' not in line:
                continue
            parts = line.split('"')
            if len(parts) >= 4:
                roots.append(Path(parts[3].replace("\\\\", "\\")))
    return list(dict.fromkeys(roots))


def find_icarus_win64() -> Path | None:
    configured = os.environ.get("ICARUS_WIN64_DIR")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            Path(r"C:\Program Files (x86)\Steam\steamapps\common\Icarus\Icarus\Binaries\Win64"),
            Path(r"C:\Program Files\Steam\steamapps\common\Icarus\Icarus\Binaries\Win64"),
        ]
    )
    for library in locate_steam_libraries():
        candidates.append(library / "steamapps" / "common" / "Icarus" / "Icarus" / "Binaries" / "Win64")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def find_ue4ss_zip_asset() -> tuple[str, str]:
    request = urllib.request.Request(UE4SS_RELEASES_API, headers={"User-Agent": "Icarus-Runtime-Setup"})
    with urllib.request.urlopen(request, timeout=30) as response:
        releases = json.loads(response.read().decode("utf-8"))
    for release in releases:
        if release.get("prerelease"):
            continue
        for asset in release.get("assets", []):
            name = str(asset.get("name", ""))
            url = str(asset.get("browser_download_url", ""))
            if name.startswith("UE4SS_") and name.endswith(".zip") and url:
                return name, url
    raise FileNotFoundError("Could not find a stable UE4SS zip asset")


def runtime_mods_root(win64_dir: Path) -> Path:
    modern = win64_dir / "ue4ss"
    if modern.is_dir():
        return modern / "Mods"
    return win64_dir / "Mods"


def running_icarus_processes() -> list[str]:
    try:
        completed = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=False)
    except Exception:
        return []
    found: list[str] = []
    for line in completed.stdout.splitlines():
        lower = line.lower()
        if "icarus" in lower:
            found.append(line)
    return found


def ensure_ue4ss(win64_dir: Path) -> None:
    modern = win64_dir / "ue4ss"
    if (win64_dir / "dwmapi.dll").is_file() and ((modern / "UE4SS.dll").is_file() or (win64_dir / "UE4SS.dll").is_file()):
        print(f"OK: UE4SS loader already present in {win64_dir}")
        return

    asset_name, url = find_ue4ss_zip_asset()
    tools_dir = APP_DIR / "tools" / "ue4ss"
    tools_dir.mkdir(parents=True, exist_ok=True)
    archive = tools_dir / asset_name
    extract_dir = tools_dir / asset_name.removesuffix(".zip")

    print(f"Downloading {asset_name}")
    urllib.request.urlretrieve(url, archive)
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(extract_dir)

    source_root = extract_dir
    nested = [path for path in extract_dir.iterdir() if path.is_dir()]
    if len(nested) == 1 and not any((extract_dir / name).exists() for name in ("dwmapi.dll", "UE4SS.dll", "ue4ss")):
        source_root = nested[0]

    copied = 0
    for item in source_root.iterdir():
        target = win64_dir / item.name
        if item.is_dir():
            if target.exists():
                shutil.move(str(target), str(backup_path(target)))
            shutil.copytree(item, target)
            copied += 1
        elif item.is_file():
            if target.exists():
                shutil.move(str(target), str(backup_path(target)))
            shutil.copy2(item, target)
            copied += 1

    archive.unlink(missing_ok=True)
    shutil.rmtree(extract_dir, ignore_errors=True)
    if copied == 0 or not (win64_dir / "dwmapi.dll").is_file():
        raise RuntimeError("UE4SS archive did not install a usable loader")
    print(f"OK: installed UE4SS loader to {win64_dir}")


def ensure_bundled_ue4ss(win64_dir: Path) -> None:
    bundled = next((candidate for candidate in BUNDLED_UE4SS_DLLS if candidate.is_file()), None)
    if bundled is None:
        return
    target = win64_dir / "UE4SS.dll"
    if target.is_file() and filecmp.cmp(bundled, target, shallow=False):
        print(f"OK: bundled UE4SS runtime already installed in {win64_dir}")
        return
    running = running_icarus_processes()
    if running:
        raise RuntimeError(
            "Icarus is running. Fully close Icarus before replacing UE4SS.dll with the matching DLL runtime."
        )
    if target.exists():
        shutil.move(str(target), str(backup_path(target)))
    shutil.copy2(bundled, target)
    print(f"OK: installed matching UE4SS runtime DLL to {target}")


def backup_remove(path: Path) -> None:
    if not path.exists():
        return
    target = backup_path(path)
    shutil.move(str(path), str(target))
    print(f"OK: moved old runtime file to backup: {path}")


def clean_stale_mods(mods_root: Path, mod_name: str) -> None:
    for folder_name in sorted(MOD_FOLDERS_TO_CLEAN):
        backup_remove(mods_root / folder_name)

    mods_txt = mods_root / "mods.txt"
    existing = mods_txt.read_text(encoding="utf-8", errors="ignore").splitlines() if mods_txt.is_file() else []
    output: list[str] = []
    found = False
    for entry in existing:
        stripped = entry.strip()
        if not stripped or stripped.startswith(";") or ":" not in stripped:
            output.append(entry)
            continue
        key = stripped.split(":", 1)[0].strip().lstrip("\ufeff")
        if key.casefold() == mod_name.casefold():
            output.append(f"{mod_name} : 1")
            found = True
        elif key in MOD_FOLDERS_TO_CLEAN:
            continue
        else:
            output.append(entry)
    if not found:
        output.append(f"{mod_name} : 1")
    mods_txt.parent.mkdir(parents=True, exist_ok=True)
    mods_txt.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def tune_ue4ss_settings(win64_dir: Path) -> None:
    settings = win64_dir / "UE4SS-settings.ini"
    if not settings.is_file():
        return
    text = settings.read_text(encoding="utf-8", errors="ignore")
    replacements = {
        "ConsoleEnabled = 1": "ConsoleEnabled = 0",
        "GuiConsoleEnabled = 1": "GuiConsoleEnabled = 0",
        "GuiConsoleVisible = 1": "GuiConsoleVisible = 0",
        "bUseUObjectArrayCache = true": "bUseUObjectArrayCache = false",
    }
    updated = text
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    if updated != text:
        settings.write_text(updated, encoding="utf-8")
        print(f"OK: tuned UE4SS settings for runtime startup: {settings}")


def enable_mod(mods_root: Path, mod_name: str) -> Path:
    mods_txt = mods_root / "mods.txt"
    existing = mods_txt.read_text(encoding="utf-8", errors="ignore").splitlines() if mods_txt.is_file() else []
    output: list[str] = []
    found = False
    for entry in existing:
        stripped = entry.strip()
        if not stripped or stripped.startswith(";") or ":" not in stripped:
            output.append(entry)
            continue
        key = stripped.split(":", 1)[0].strip().lstrip("\ufeff")
        if key.casefold() == mod_name.casefold():
            output.append(f"{mod_name} : 1")
            found = True
        elif key in UE4SS_BUILTIN_MODS_TO_DISABLE:
            continue
        else:
            output.append(entry)
    if not found:
        output.append(f"{mod_name} : 1")
    mods_txt.parent.mkdir(parents=True, exist_ok=True)
    mods_txt.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return mods_txt


def generate_runtime_package(profile_path: Path) -> Path:
    import tkinter as tk
    import configurator

    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    interp = tk.Tcl()
    app = object.__new__(configurator.Configurator)
    app.app_dir = APP_DIR
    app.state_dir = APP_STATE_DIR
    app.builds_dir = APP_STATE_DIR / "builds"
    app.backups_dir = APP_STATE_DIR / "backups"
    app.runtime_dir = APP_STATE_DIR / "runtime_mods"
    app.profiles_dir = SOURCE_PROFILES_DIR
    app.app_log = APP_STATE_DIR / "configurator.log"
    app.setting_vars = {spec.key: tk.StringVar(interp, value=configurator.display_multiplier(1)) for spec in configurator.SETTINGS}
    app.direct_vars = {
        spec.key: tk.StringVar(interp, value=configurator.display_multiplier(spec.default) if configurator.is_direct_multiplier(spec) else spec.default)
        for spec in configurator.DIRECT_SETTINGS
    }
    app.container_slot_vars = {
        spec.key: tk.StringVar(interp, value=configurator.display_multiplier(spec.default))
        for spec in configurator.CONTAINER_SLOT_SETTINGS
    }
    app.curve_vars = {spec.key: tk.StringVar(interp, value=configurator.display_multiplier(1)) for spec in configurator.CURVE_SETTINGS}
    app.runtime_vars = {spec.key: tk.StringVar(interp, value=configurator.display_multiplier(spec.default)) for spec in configurator.RUNTIME_SETTINGS}
    app.native_group_vars = {
        group.key: [tk.StringVar(interp, value=configurator.display_multiplier(1)) for _minimum, _maximum in group.ranges]
        for group in configurator.NATIVE_GROUPS
    }
    app.group_master_vars = {}
    app.range_label_vars = {}
    app.mod_name_var = tk.StringVar(interp, value=profile.get("mod_name", DEFAULT_MOD_NAME))
    app.status_var = tk.StringVar(interp, value="")
    app.summary_var = tk.StringVar(interp, value="")
    app.log = lambda message: None
    app.show_error = lambda title, error: (_ for _ in ()).throw(error)
    configurator.Configurator.apply_profile_data(app, profile)
    package = configurator.Configurator.write_runtime_mod_package(app, APP_DIR / "builds")
    print(f"OK: generated runtime package {package}")
    return package


def copy_runtime_package(package: Path, mods_root: Path) -> Path:
    target = mods_root / package.name
    if target.exists():
        shutil.move(str(target), str(backup_path(target)))
    shutil.copytree(package, target)
    print(f"OK: installed runtime mod {target}")
    return target


def set_debug_validation(package: Path, *, enabled: bool, log_each: bool, risky: bool) -> None:
    if not enabled:
        return
    settings = package / "settings.ini"
    if not settings.is_file():
        raise FileNotFoundError(f"Missing generated settings.ini in {package}")
    text = settings.read_text(encoding="utf-8")
    replacements = {
        "enabled = false": "enabled = true",
        "forceAllSupported = false": "forceAllSupported = true",
        "logEachMathCheck = false": f"logEachMathCheck = {'true' if log_each else 'false'}",
        "includeRiskyArrayEdits = false": f"includeRiskyArrayEdits = {'true' if risky else 'false'}",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    settings.write_text(text, encoding="utf-8")
    print(
        "OK: enabled debug validation in generated settings.ini "
        f"(logEachMathCheck={log_each}, includeRiskyArrayEdits={risky})"
    )


def validate_install(win64_dir: Path, installed_mod: Path) -> list[str]:
    errors: list[str] = []
    modern = win64_dir / "ue4ss"
    if not (win64_dir / "dwmapi.dll").is_file():
        errors.append("Missing UE4SS loader dwmapi.dll")
    if not ((modern / "UE4SS.dll").is_file() or (win64_dir / "UE4SS.dll").is_file()):
        errors.append("Missing UE4SS.dll")
    required = [
        installed_mod / "dlls" / "main.dll",
        installed_mod / "enabled.txt",
        installed_mod / "option_manifest.json",
        installed_mod / "runtime_config.json",
    ]
    required.extend(installed_mod.glob("*.ini"))
    for path in required:
        if not path.is_file():
            errors.append(f"Missing {path}")
    if not any(installed_mod.glob("*.ini")):
        errors.append("Missing unified INI")
    mods_txt = installed_mod.parent / "mods.txt"
    mod_line = f"{installed_mod.name} : 1"
    if not mods_txt.is_file() or mod_line.casefold() not in mods_txt.read_text(encoding="utf-8", errors="ignore").casefold():
        errors.append(f"mods.txt does not enable {installed_mod.name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build, install, and validate the Icarus runtime mod setup.")
    parser.add_argument("--check-only", action="store_true", help="Only validate an existing install.")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="Profile JSON to package.")
    parser.add_argument("--debug-validation", action="store_true", help="Enable opt-in full supported-setting validation in generated settings.ini.")
    parser.add_argument("--debug-log-each", action="store_true", help="With --debug-validation, log each math check with default/expected/actual values.")
    parser.add_argument(
        "--debug-risky-arrays",
        action="store_true",
        help="With --debug-validation, include array-backed recipe/inventory tests. Free craft leaves ResourceInputs untouched to avoid live resource drain.",
    )
    args = parser.parse_args()

    try:
        print("Icarus runtime setup")
        print(f"Tool folder: {APP_DIR}")
        win64_dir = find_icarus_win64()
        if win64_dir is None:
            raise FileNotFoundError(
                "Could not find Icarus\\Binaries\\Win64. Set ICARUS_WIN64_DIR to the full Win64 folder and run this again."
            )
        print(f"Game Win64 folder: {win64_dir}")

        mods_root = runtime_mods_root(win64_dir)
        installed_mod = mods_root / RUNTIME_MOD_FOLDER

        if not args.check_only:
            if not args.profile.is_file():
                raise FileNotFoundError(f"Profile missing: {args.profile}")
            package = generate_runtime_package(args.profile)
            set_debug_validation(
                package,
                enabled=args.debug_validation,
                log_each=args.debug_log_each,
                risky=args.debug_risky_arrays,
            )
            ensure_ue4ss(win64_dir)
            ensure_bundled_ue4ss(win64_dir)
            tune_ue4ss_settings(win64_dir)
            backup_remove(win64_dir / "UE4SS.log")
            mods_root.mkdir(parents=True, exist_ok=True)
            clean_stale_mods(mods_root, package.name)
            installed_mod = copy_runtime_package(package, mods_root)
            backup_remove(installed_mod / "runtime_dll.log")
            backup_remove(installed_mod / "runtime.log")
            enable_mod(mods_root, installed_mod.name)

        errors = validate_install(win64_dir, installed_mod)
        if errors:
            print("\nSetup is NOT complete:")
            for error in errors:
                print(f"  - {error}")
            return 1

        print("\nSetup is complete.")
        print("Fully close and restart Icarus before testing runtime changes.")
        return 0
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
