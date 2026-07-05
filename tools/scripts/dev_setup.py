from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()


def find_repo_root() -> Path:
    for candidate in (SCRIPT_PATH.parent, *SCRIPT_PATH.parents):
        if (candidate / "app" / "configurator.py").is_file():
            return candidate
    raise FileNotFoundError("Could not find app/configurator.py from dev setup script location")


REPO_ROOT = find_repo_root()


def run(arguments: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, cwd=str(REPO_ROOT), text=True, capture_output=True, check=check)


def command_version(command: str, *args: str) -> str | None:
    if shutil.which(command) is None:
        return None
    completed = run([command, *args])
    text = (completed.stdout or completed.stderr).strip()
    return text.splitlines()[0] if text else "found"


def python_module_available(module: str) -> bool:
    completed = run([sys.executable, "-c", f"import {module}"])
    return completed.returncode == 0


def visual_studio_build_tools_found() -> bool:
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if vswhere.is_file():
        completed = run([
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
        ])
        if completed.stdout.strip():
            return True
    return any(
        path.is_dir()
        for path in (
            Path(r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC"),
            Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC"),
            Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC"),
        )
    )


def install_pyinstaller() -> None:
    print("Installing PyInstaller with pip...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], cwd=str(REPO_ROOT), check=True)


def install_rust() -> None:
    if shutil.which("winget") is None:
        print("winget is not available; install Rust from https://rustup.rs/")
        return
    print("Installing Rustup with winget...")
    subprocess.run(
        [
            "winget",
            "install",
            "--id",
            "Rustlang.Rustup",
            "-e",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
        cwd=str(REPO_ROOT),
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check and prepare the Icarus Configuration Mod developer environment.")
    parser.add_argument("--install", action="store_true", help="Install safe missing developer dependencies where possible.")
    args = parser.parse_args()

    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python", True, sys.version.split()[0]))
    checks.append(("Tkinter", python_module_available("tkinter"), "bundled with most Windows Python installs"))
    checks.append(("Git", command_version("git", "--version") is not None, command_version("git", "--version") or "missing"))
    checks.append(("CMake", command_version("cmake", "--version") is not None, command_version("cmake", "--version") or "missing"))
    checks.append(("Rust", command_version("rustc", "--version") is not None, command_version("rustc", "--version") or "missing"))
    checks.append(("Visual Studio C++ Build Tools", visual_studio_build_tools_found(), "MSVC toolchain"))
    checks.append(("PyInstaller", python_module_available("PyInstaller"), "Python exe packager"))

    missing = [name for name, ok, _detail in checks if not ok]
    if args.install:
        if "PyInstaller" in missing:
            install_pyinstaller()
        if "Rust" in missing:
            install_rust()
        return main_without_install()

    print(f"Repo root: {REPO_ROOT}")
    print("\nDeveloper dependency check:")
    for name, ok, detail in checks:
        status = "OK" if ok else "MISSING"
        print(f"  {status:7} {name}: {detail}")

    if missing:
        print("\nMissing requirements:")
        for name in missing:
            print(f"  - {name}")
        print("\nInstall what can be automated:")
        print("  python tools\\scripts\\dev_setup.py --install")
        print("\nManual installs if still missing:")
        print("  winget install --id Git.Git -e")
        print("  winget install --id Kitware.CMake -e")
        print("  winget install --id Microsoft.VisualStudio.2022.BuildTools -e")
        return 1

    print("\nEnvironment is ready.")
    print("Build DLL:      python tools\\scripts\\build_dll.py")
    print("Package release: python tools\\scripts\\package_release.py")
    return 0


def main_without_install() -> int:
    original_argv = sys.argv[:]
    try:
        sys.argv = [sys.argv[0]]
        return main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
