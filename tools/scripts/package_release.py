from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()


def find_app_dir() -> Path:
    for candidate in (SCRIPT_PATH.parent, *SCRIPT_PATH.parents):
        if (candidate / "configurator.py").is_file():
            return candidate
    raise FileNotFoundError("Could not find configurator.py from packaging script location")


APP_DIR = find_app_dir()
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

DIST_DIR = APP_DIR / "dist" / "IcarusConfigMod"
EXE_WORK_DIR = APP_DIR / "tools" / "exe_build"


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


def ensure_pyinstaller() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        cwd=str(APP_DIR),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode == 0:
        return
    run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_configurator_exe() -> Path:
    ensure_pyinstaller()
    if EXE_WORK_DIR.exists():
        shutil.rmtree(EXE_WORK_DIR)
    EXE_WORK_DIR.mkdir(parents=True)
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            "IcarusConfigMod",
            "--distpath",
            str(EXE_WORK_DIR / "dist"),
            "--workpath",
            str(EXE_WORK_DIR / "work"),
            "--specpath",
            str(EXE_WORK_DIR),
            str(APP_DIR / "configurator.py"),
        ]
    )
    exe = EXE_WORK_DIR / "dist" / "IcarusConfigMod.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"PyInstaller did not produce expected exe: {exe}")
    return exe


def generate_package() -> Path:
    import tkinter as tk
    import configurator

    profile_path = APP_DIR / "profiles" / "Premade_Configuration.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    interp = tk.Tcl()
    app = object.__new__(configurator.Configurator)
    app.app_dir = APP_DIR
    app.builds_dir = APP_DIR / "builds"
    app.backups_dir = APP_DIR / "backups"
    app.runtime_dir = APP_DIR / "runtime_mods"
    app.profiles_dir = APP_DIR / "profiles"
    app.app_log = APP_DIR / "configurator.log"
    app.setting_vars = {spec.key: tk.StringVar(interp, value=configurator.display_multiplier(1)) for spec in configurator.SETTINGS}
    app.direct_vars = {
        spec.key: tk.StringVar(interp, value=configurator.display_multiplier(spec.default) if configurator.is_direct_multiplier(spec) else spec.default)
        for spec in configurator.DIRECT_SETTINGS
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
    package = configurator.Configurator.write_runtime_mod_package(app, APP_DIR / "builds")
    if not (package / "dlls" / "main.dll").is_file():
        raise FileNotFoundError(f"Generated package missing DLL runtime: {package}")
    return package


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def stage_release(package: Path, exe: Path) -> Path:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)
    copy_file(exe, DIST_DIR / "IcarusConfigMod.exe")
    copy_file(APP_DIR / "README.md", DIST_DIR / "README.md")
    copy_file(APP_DIR / "LICENSE", DIST_DIR / "LICENSE")
    shutil.copytree(APP_DIR / "profiles", DIST_DIR / "profiles")
    shutil.copytree(package, DIST_DIR / "builds" / package.name)
    ue4ss_target = DIST_DIR / "tools" / "ue4ss"
    ue4ss_target.mkdir(parents=True, exist_ok=True)
    copy_file(APP_DIR / "tools" / "dll" / "out" / "UE4SS.dll", ue4ss_target / "UE4SS.dll")
    (DIST_DIR / "PLAYER_README.txt").write_text(
        "Run IcarusConfigMod.exe to edit profiles, install the UE4SS runtime mod, or reset installed files.\n"
        "This player package ships a portable configurator and prebuilt UE4SS C++ DLL runtime.\n"
        "No player-side Python install, build step, batch file, or PowerShell script is required.\n",
        encoding="utf-8",
    )
    for cache in DIST_DIR.rglob("__pycache__"):
        shutil.rmtree(cache)
    for generated in (DIST_DIR / "backups",):
        if generated.exists():
            shutil.rmtree(generated)
    return DIST_DIR


def main() -> int:
    try:
        build_dll()
        exe = build_configurator_exe()
        package = generate_package()
        dist = stage_release(package, exe)
        archive = shutil.make_archive(str(dist), "zip", root_dir=dist)
        print(f"Release folder: {dist}")
        print(f"Release zip: {archive}")
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
