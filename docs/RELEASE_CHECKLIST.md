# Release Checklist

Use this before uploading a beta package.

## Build

- Run `python tools\scripts\dev_setup.py`.
- Run `python -m py_compile app\configurator.py tools\scripts\install_runtime.py tools\scripts\package_release.py tools\scripts\reset.py`.
- Run `python tools\scripts\package_release.py`.
- Confirm `dist\IcarusConfigMod.zip` was updated.
- Confirm `docs\RELEASE_NOTES.md`, `README.md`, `docs\PLAYER_README.md`, and `docs\NEXUS_DESCRIPTION.bbcode` describe the current runtime behavior.
- Confirm the player zip contains no `.bat`, `.ps1`, or player-side `.py` launch scripts.
- Confirm the player zip does not contain PyInstaller `*.pkg`, `*.spec`, `_MEI*`, or `pyi-*` artifacts.
- Confirm the staged player folder does not contain generated `backups`, `builds`, `runtime_mods`, `tools`, `configurator.log`, `user_settings.json`, or `Configuration_Mod/dlls`.
- Source-only root `.bat` wrappers are allowed in Git, but must not appear in `dist`.

## Package Contents

The player zip should include:

- `IcarusConfigMod.exe`
- `UE4SS.dll`
- `main.dll`
- `PLAYER_README.txt`
- `README.md` copied from `docs/PLAYER_README.md`
- `RELEASE_NOTES.txt` copied from `docs/RELEASE_NOTES.md`
- `profiles/Premade_Configuration.json`
- `Configuration_Mod/settings.ini`
- `Configuration_Mod/runtime_config.json`
- `Configuration_Mod/option_manifest.json`
- standalone app runtime DLL/PYD files required by Nuitka

The player zip should not include:

- `recovery/`
- `backups/`
- `configurator.log`
- `user_settings.json`
- `__pycache__/`
- `tools/dll/ue4ss_build/`
- `Setup.bat`
- `Launch.bat`
- `Reset.bat`
- `configurator.py`
- `builds/`
- `runtime_mods/`
- `tools/`
- `Configuration_Mod/dlls/`
- `tools/scripts/`
- `tools/ue4ss/`
- `Configuration_Mod/dlls/`
- local Icarus save files

## In-App Checks

- First app load shows `Vanilla Defaults`.
- Dropdown also shows `Premade_Configuration`.
- Dropdown entries do not show `.json`.
- Live Vault tab reports the UE4SS DLL heartbeat from `%LOCALAPPDATA%\ZSG Studios\IcarusConfigMod\live_bridge\status.json`.
- Live Vault tab reports bridge version, inventory candidate count, and `%LOCALAPPDATA%\ZSG Studios\IcarusConfigMod\live_bridge\snapshot.json` when the runtime writes a read-only snapshot.
- Live Vault docs clearly state inventory write/move is guarded until the runtime object writer is validated.
- Offline save-vault export/import is not exposed as the player workflow.
- Clicking install while vanilla is selected shows a clean message instead of a traceback.
- If Icarus is not found automatically, clicking install prompts for the Icarus folder or `Icarus\Binaries\Win64`.
- Imported or saved profiles are copied into `profiles/` and appear in the dropdown.

## Runtime Checks

After installing and launching Icarus, inspect the runtime log for:

- `SETTING_STATUS` lines for active settings.
- `VALIDATION SettingsSummary`.
- `VALIDATION GreenLight ... GreenLight=YES`.
- `Partial=0 Pending=0 Skipped=0 Unsupported=0 MissingFields=0`.
- No active settings with `Result=unsupported`.
- No active settings with `Result=partial`, `Result=pending`, or `Result=skipped`.
- For carcass testing, confirm killed animals remain harvestable and `skinning_yield` applies through carcass output counts rather than `D_ToolDamage.Skinning_Efficiency`.
- For health/speed testing, remember these are table-backed stat grants and may require session load, spawn, respawn, healing, or game stat refresh before the visible HUD/current pawn reflects the changed base values.
- For live bridge testing, confirm `LIVE_BRIDGE Started`, `LIVE_BRIDGE HeartbeatLoopStarted`, `LIVE_BRIDGE Snapshot`, a fresh `status.json` heartbeat, and `snapshot.json` while Icarus is running.
