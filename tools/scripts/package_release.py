from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()


def find_app_dir() -> Path:
    for candidate in (SCRIPT_PATH.parent, *SCRIPT_PATH.parents):
        if (candidate / "app" / "configurator.py").is_file():
            return candidate
    raise FileNotFoundError("Could not find app/configurator.py from packaging script location")


APP_DIR = find_app_dir()
APP_SOURCE_DIR = APP_DIR / "app"
SOURCE_PROFILES_DIR = APP_DIR / "config" / "profiles"
for import_path in (APP_SOURCE_DIR, APP_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

DIST_DIR = APP_DIR / "dist" / "IcarusConfigMod"
EXE_WORK_DIR = APP_DIR / "tools" / "exe_build"
PACKAGE_WORK_DIR = APP_DIR / "tools" / "package_work"


def run(arguments: list[str]) -> None:
    print("> " + subprocess.list2cmdline(arguments))
    completed = subprocess.run(arguments, cwd=str(APP_DIR), text=True)
    if completed.returncode:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}")


def build_dll() -> Path:
    run([sys.executable, str(APP_DIR / "tools" / "scripts" / "build_dll.py")])
    dll = APP_DIR / "tools" / "dll" / "out" / "main.dll"
    ue4ss = APP_DIR / "tools" / "dll" / "out" / "UE4SS.dll"
    if not dll.is_file():
        raise FileNotFoundError(f"Compiled DLL missing: {dll}")
    if not ue4ss.is_file():
        raise FileNotFoundError(f"Compiled UE4SS runtime missing: {ue4ss}")
    return dll


def ensure_nuitka() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "nuitka", "--version"],
        cwd=str(APP_DIR),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode == 0:
        return
    run([sys.executable, "-m", "pip", "install", "nuitka", "ordered-set", "zstandard"])


def build_configurator_app() -> Path:
    ensure_nuitka()
    if EXE_WORK_DIR.exists():
        shutil.rmtree(EXE_WORK_DIR)
    EXE_WORK_DIR.mkdir(parents=True)
    run(
        [
            sys.executable,
            "-m",
            "nuitka",
            "--standalone",
            "--enable-plugin=tk-inter",
            "--windows-console-mode=disable",
            "--assume-yes-for-downloads",
            "--output-dir=" + str(EXE_WORK_DIR),
            "--output-filename=IcarusConfigMod.exe",
            "--remove-output",
            str(APP_SOURCE_DIR / "configurator.py"),
        ]
    )
    exe = EXE_WORK_DIR / "configurator.dist" / "IcarusConfigMod.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"Nuitka did not produce expected exe: {exe}")
    return exe.parent


def generate_package() -> Path:
    import tkinter as tk
    import configurator

    if PACKAGE_WORK_DIR.exists():
        shutil.rmtree(PACKAGE_WORK_DIR)
    package_builds_dir = PACKAGE_WORK_DIR / "builds"
    profile_path = SOURCE_PROFILES_DIR / "Premade_Configuration.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    interp = tk.Tcl()
    app = object.__new__(configurator.Configurator)
    app.app_dir = APP_DIR
    app.state_dir = PACKAGE_WORK_DIR
    app.builds_dir = package_builds_dir
    app.backups_dir = PACKAGE_WORK_DIR / "backups"
    app.runtime_dir = PACKAGE_WORK_DIR / "runtime_mods"
    app.profiles_dir = SOURCE_PROFILES_DIR
    app.app_log = PACKAGE_WORK_DIR / "configurator.log"
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
    app.mod_name_var = tk.StringVar(interp, value=profile.get("mod_name", "Configuration_Mod"))
    app.status_var = tk.StringVar(interp, value="")
    app.summary_var = tk.StringVar(interp, value="")
    app.log = lambda message: None
    app.show_error = lambda title, error: (_ for _ in ()).throw(error)
    configurator.Configurator.apply_profile_data(app, profile)
    package = configurator.Configurator.write_runtime_mod_package(app, package_builds_dir)
    if not (package / "dlls" / "main.dll").is_file():
        raise FileNotFoundError(f"Generated package missing DLL runtime: {package}")
    return package


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def stage_release(package: Path, app_bundle: Path) -> Path:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    shutil.copytree(app_bundle, DIST_DIR)
    copy_file(APP_DIR / "docs" / "PLAYER_README.md", DIST_DIR / "README.md")
    copy_file(APP_DIR / "docs" / "RELEASE_NOTES.md", DIST_DIR / "RELEASE_NOTES.txt")
    copy_file(APP_DIR / "LICENSE", DIST_DIR / "LICENSE")
    shutil.copytree(SOURCE_PROFILES_DIR, DIST_DIR / "profiles")
    shutil.copytree(package, DIST_DIR / package.name, ignore=shutil.ignore_patterns("dlls"))
    copy_file(package / "dlls" / "main.dll", DIST_DIR / "main.dll")
    copy_file(APP_DIR / "tools" / "dll" / "out" / "UE4SS.dll", DIST_DIR / "UE4SS.dll")
    (DIST_DIR / "PLAYER_README.txt").write_text(
        "Run IcarusConfigMod.exe to edit profiles, install the UE4SS runtime mod, or reset installed files.\n"
        "This player package ships a portable configurator and prebuilt UE4SS C++ DLL runtime.\n"
        "Applying configuration creates an automatic Icarus player/world save backup first.\n"
        "Use the Save Backups tab to create, list, open, and restore save backups.\n"
        "Read RELEASE_NOTES.txt for current beta fixes and known runtime behavior.\n"
        "Close Icarus before creating or restoring save backups.\n"
        "No player-side Python install, build step, batch file, or PowerShell script is required.\n",
        encoding="utf-8",
    )
    for cache in DIST_DIR.rglob("__pycache__"):
        shutil.rmtree(cache)
    for generated in (DIST_DIR / "backups", DIST_DIR / "builds", DIST_DIR / "runtime_mods", DIST_DIR / "save_backups"):
        if generated.exists():
            shutil.rmtree(generated)
    app_log = DIST_DIR / "configurator.log"
    if app_log.exists():
        app_log.unlink()
    return DIST_DIR


def main() -> int:
    try:
        build_dll()
        app_bundle = build_configurator_app()
        package = generate_package()
        dist = stage_release(package, app_bundle)
        archive = shutil.make_archive(str(dist), "zip", root_dir=dist)
        print(f"Release folder: {dist}")
        print(f"Release zip: {archive}")
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
