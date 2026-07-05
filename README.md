# Icarus Configuration Mod

Configurable UE4SS C++ runtime mod for Icarus balance settings.

## Player Install

1. Download the release zip.
2. Extract it anywhere outside the Icarus install folder.
3. Run `IcarusConfigMod.exe`.
4. In the configurator, choose `Premade_Configuration` or import/save a custom profile.
5. Click the install/apply button, then fully restart Icarus.

The app starts on `Vanilla Defaults` intentionally. Vanilla is a reset/default state, not an installable modified profile.

## Included Player Profile

The release ships one premade profile:

- `Premade_Configuration`

Saved or imported player profiles are copied into `profiles/` and then appear in the same profile dropdown without the `.json` extension.

## Source Layout

- `app/configurator.py` - Tkinter configuration app and runtime package writer.
- `config/profiles/` - shipped source profile JSON files.
- `docs/RELEASE_CHECKLIST.md` - beta packaging checklist.
- `Dev Setup.bat`, `Build DLL.bat`, `Package Release.bat` - source-only convenience wrappers.
- `tools/scripts/dev_setup.py` - developer environment checker and safe dependency bootstrap.
- `tools/scripts/install_runtime.py` - developer/player setup script retained for source builds.
- `tools/scripts/package_release.py` - developer release packager.
- `tools/scripts/build_dll.py` - developer DLL build helper.
- `tools/dll/src/` - UE4SS C++ runtime source.
- `tools/dll/include/` - runtime headers.

Generated folders such as `builds/`, `dist/`, `backups/`, `recovery/`, `runtime_mods/`, `tools/dll/out/`, and `tools/dll/ue4ss_build/` are ignored for source sharing.

## Developer Setup

Requirements:

- Python 3.13 or compatible Python 3 with Tkinter.
- Visual Studio 2022 Build Tools with MSVC.
- CMake.
- Git.
- Rust toolchain, required by the UE4SS C++ template dependencies.
- PyInstaller, used only for building the portable player exe.

Check the local environment:

```powershell
python tools\scripts\dev_setup.py
```

Install safe missing dependencies where the script can automate it:

```powershell
python tools\scripts\dev_setup.py --install
```

Some system tools may still need manual install if Windows does not already have them:

```powershell
winget install --id Git.Git -e
winget install --id Kitware.CMake -e
winget install --id Microsoft.VisualStudio.2022.BuildTools -e
```

## Developer Build

Build the DLL:

```powershell
python tools\scripts\build_dll.py
```

Package the player release:

```powershell
python tools\scripts\package_release.py
```

Optional source-only batch wrappers are also available at the repo root for developers who prefer double-click or `cmd.exe` workflows: `Dev Setup.bat`, `Build DLL.bat`, and `Package Release.bat`. They are not copied into the player zip.

The player zip is written to:

```text
dist\IcarusConfigMod.zip
```

The player zip is portable and ships `IcarusConfigMod.exe`; no player-side Python install, batch file, PowerShell script, or build step is required.

The player zip layout is intentionally flatter than the source tree:

```text
IcarusConfigMod.exe
UE4SS.dll
Configuration_Mod/
profiles/
README.md
PLAYER_README.txt
LICENSE
```

## Runtime Validation

The DLL writes per-setting validation lines such as `SETTING_STATUS`, `VALIDATION SettingsSummary`, and `VALIDATION GreenLight` to its runtime log after Icarus starts. For a clean beta pass, the latest green-light line should show `GreenLight=YES` with `Partial=0 Pending=0 Skipped=0 Unsupported=0 MissingFields=0`.

## Git Hygiene

Do not commit local game saves, generated packages, logs, backups, UE4SS downloaded binaries, or build trees. The `.gitignore` is set up for this.
