from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()


def find_app_dir() -> Path:
    for candidate in (SCRIPT_PATH.parent, *SCRIPT_PATH.parents):
        if (candidate / "app" / "configurator.py").is_file():
            return candidate
    raise FileNotFoundError("Could not find app/configurator.py from reset script location")


APP_DIR = find_app_dir()


def user_state_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ZSG Studios" / "IcarusConfigMod"
    return Path.home() / "AppData" / "Local" / "ZSG Studios" / "IcarusConfigMod"


APP_STATE_DIR = user_state_dir()
MOD_NAMES = ("Configuration_Mod",)
UE4SS_SAMPLE_MOD_NAMES = (
    "ActorDumperMod",
    "BPML_GenericFunctions",
    "BPModLoaderMod",
    "CheatManagerEnablerMod",
    "ConsoleCommandsMod",
    "ConsoleEnablerMod",
    "jsbLuaProfilerMod",
    "LineTraceMod",
    "SplitScreenMod",
)
OLD_RUNTIME_MOD_NAMES = (
    "ZSG_Balance_w235_Runtime",
    "ZSG_Balance",
    "ZSG_Balance_Runtime",
    "ConfigurationMod",
    "Configuration_Mod_Runtime",
)
GAME_MOD_NAMES_TO_REMOVE = MOD_NAMES + UE4SS_SAMPLE_MOD_NAMES + OLD_RUNTIME_MOD_NAMES


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
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    print(f"Removed {path}")


def clean_local() -> None:
    for relative in (r"tools\ue4ss",):
        remove_path(APP_DIR / relative)
    for relative in ("backups", "builds", "runtime_mods", "configurator.log", "user_settings.json"):
        remove_path(APP_STATE_DIR / relative)
    for cache in APP_DIR.rglob("__pycache__"):
        remove_path(cache)
    (APP_DIR / "config" / "profiles").mkdir(parents=True, exist_ok=True)


def clean_game() -> None:
    win64 = find_icarus_win64()
    if win64 is None:
        print("Icarus Win64 folder not found; skipped game cleanup.")
        return
    mods_roots = [win64 / "Mods", win64 / "ue4ss" / "Mods"]
    for mod_name in GAME_MOD_NAMES_TO_REMOVE:
        for root in mods_roots:
            remove_path(root / mod_name)
    for root in mods_roots:
        mods_txt = root / "mods.txt"
        if not mods_txt.is_file():
            continue
        lines = mods_txt.read_text(encoding="utf-8", errors="ignore").splitlines()
        filtered = [
            line for line in lines
            if not any(line.strip().casefold().startswith(f"{name.casefold()} :") for name in GAME_MOD_NAMES_TO_REMOVE)
        ]
        if filtered:
            mods_txt.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")
            print(f"Cleaned {mods_txt}")
        else:
            remove_path(mods_txt)
    remove_path(win64 / "UE4SS.log")


def main() -> int:
    try:
        clean_local()
        clean_game()
        print("Reset complete. Run the configurator or package_release.py for a fresh install/package.")
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
