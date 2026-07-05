# Release Checklist

Use this before uploading a beta package.

## Build

- Run `python -m py_compile configurator.py tools\scripts\install_runtime.py tools\scripts\package_release.py tools\scripts\reset.py`.
- Run `python tools\scripts\package_release.py`.
- Confirm `dist\IcarusConfigMod.zip` was updated.

## Package Contents

The player zip should include:

- `Setup.bat`
- `Launch.bat`
- `Reset.bat`
- `configurator.py`
- `PLAYER_README.txt`
- `profiles/Premade_Configuration.json`
- `builds/Configuration_Mod/settings.ini`
- `builds/Configuration_Mod/runtime_config.json`
- `builds/Configuration_Mod/option_manifest.json`
- `builds/Configuration_Mod/dlls/main.dll`
- `tools/scripts/install_runtime.py`
- `tools/scripts/reset.py`
- `tools/ue4ss/UE4SS.dll`

The player zip should not include:

- `recovery/`
- `backups/`
- `configurator.log`
- `__pycache__/`
- `tools/dll/ue4ss_build/`
- local Icarus save files

## In-App Checks

- First app load shows `Vanilla Defaults`.
- Dropdown also shows `Premade_Configuration`.
- Dropdown entries do not show `.json`.
- Clicking install while vanilla is selected shows a clean message instead of a traceback.
- Imported or saved profiles are copied into `profiles/` and appear in the dropdown.

## Runtime Checks

After installing and launching Icarus, inspect the runtime log for:

- `SETTING_STATUS` lines for active settings.
- `VALIDATION SettingsSummary`.
- `VALIDATION GreenLight ... GreenLight=YES`.
- `Partial=0 Pending=0 Skipped=0 Unsupported=0 MissingFields=0`.
- No active settings with `Result=unsupported`.
- No active settings with `Result=partial`, `Result=pending`, or `Result=skipped`.
