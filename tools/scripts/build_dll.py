from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()


def find_app_dir() -> Path:
    for candidate in (SCRIPT_PATH.parent, *SCRIPT_PATH.parents):
        if (candidate / "app" / "configurator.py").is_file():
            return candidate
    raise FileNotFoundError("Could not find app/configurator.py from DLL build script location")


APP_DIR = find_app_dir()
DLL_DIR = APP_DIR / "tools" / "dll"
WORK_DIR = DLL_DIR / "ue4ss_build"
TEMPLATE_DIR = WORK_DIR / "UE4SSCPPTemplate"
MOD_DIR = TEMPLATE_DIR / "MyCPPMods" / "ConfigurationModRuntime"
OUT_DIR = DLL_DIR / "out"
CONFIG = "Game__Shipping__Win64"


def run(arguments: list[str], cwd: Path | None = None) -> None:
    print("> " + subprocess.list2cmdline(arguments))
    env = os.environ.copy()
    env["PATH"] = str(Path.home() / ".cargo" / "bin") + os.pathsep + env.get("PATH", "")
    completed = subprocess.run(arguments, cwd=str(cwd) if cwd else None, env=env, text=True)
    if completed.returncode:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}")


def ensure_rust() -> None:
    if shutil.which("rustc") or (Path.home() / ".cargo" / "bin" / "rustc.exe").is_file():
        return
    if not shutil.which("winget"):
        raise RuntimeError("Rust is required to build UE4SS C++ mods. Install Rustup or winget first.")
    run([
        "winget", "install", "--id", "Rustlang.Rustup", "-e", "--silent",
        "--accept-package-agreements", "--accept-source-agreements",
    ])


def ensure_template() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if not (TEMPLATE_DIR / ".git").is_dir():
        if TEMPLATE_DIR.exists():
            shutil.rmtree(TEMPLATE_DIR)
        run(["git", "clone", "--depth", "1", "https://github.com/UE4SS-RE/UE4SSCPPTemplate.git", str(TEMPLATE_DIR)])
    run([
        "git",
        "-c", "url.https://github.com/.insteadOf=git@github.com:",
        "-C", str(TEMPLATE_DIR),
        "submodule", "update", "--init", "--recursive", "--depth", "1",
    ])


def copy_mod_sources() -> None:
    if MOD_DIR.exists():
        shutil.rmtree(MOD_DIR)
    (MOD_DIR / "src").mkdir(parents=True)
    (MOD_DIR / "include").mkdir(parents=True)

    for source in (DLL_DIR / "src").glob("*.cpp"):
        shutil.copy2(source, MOD_DIR / "src" / source.name)
    for header in (DLL_DIR / "include").glob("*.hpp"):
        shutil.copy2(header, MOD_DIR / "include" / header.name)

    (MOD_DIR / "CMakeLists.txt").write_text(
        """cmake_minimum_required(VERSION 3.22)

set(TARGET ConfigurationModRuntime)
project(${TARGET})

add_library(${TARGET} SHARED
    "src/main.cpp"
    "src/IniConfig.cpp"
    "src/Manifest.cpp"
)
target_include_directories(${TARGET} PRIVATE "include")
target_link_libraries(${TARGET} PRIVATE UE4SS)
set_target_properties(${TARGET} PROPERTIES OUTPUT_NAME "main")
""",
        encoding="utf-8",
    )

    mods_cmake = TEMPLATE_DIR / "MyCPPMods" / "CMakeLists.txt"
    mods_cmake.write_text("add_subdirectory(ConfigurationModRuntime)\n", encoding="utf-8")


def configure_and_build() -> Path:
    build_dir = TEMPLATE_DIR / "build"
    run(["cmake", "-S", str(TEMPLATE_DIR), "-B", str(build_dir), "-DUE4SS_VERSION_CHECK=OFF"])
    run(["cmake", "--build", str(build_dir), "--config", CONFIG, "--target", "ConfigurationModRuntime", "-j", "4"])
    dll = build_dir / "MyCPPMods" / "ConfigurationModRuntime" / CONFIG / "main.dll"
    ue4ss_dll = build_dir / CONFIG / "bin" / "UE4SS.dll"
    if not dll.is_file():
        raise FileNotFoundError(f"Built DLL missing: {dll}")
    if not ue4ss_dll.is_file():
        raise FileNotFoundError(f"Built UE4SS runtime missing: {ue4ss_dll}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / "main.dll"
    shutil.copy2(dll, target)
    shutil.copy2(ue4ss_dll, OUT_DIR / "UE4SS.dll")
    return target


def main() -> int:
    try:
        ensure_rust()
        ensure_template()
        copy_mod_sources()
        dll = configure_and_build()
        print(f"Built DLL: {dll}")
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
