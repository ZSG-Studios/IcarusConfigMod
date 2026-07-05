# Icarus Configuration Mod

Configurable UE4SS C++ runtime mod for Icarus balance settings.

## Player Install

1. Download the release zip.
2. Extract it anywhere outside the Icarus install folder.
3. Run `Setup.bat`.
4. Run `Launch.bat`.
5. In the configurator, choose `Premade_Configuration` or import/save a custom profile.
6. Click the install/apply button, then fully restart Icarus.

The app starts on `Vanilla Defaults` intentionally. Vanilla is a reset/default state, not an installable modified profile.

## Included Player Profile

The release ships one premade profile:

- `Premade_Configuration`

Saved or imported player profiles are copied into `profiles/` and then appear in the same profile dropdown without the `.json` extension.

## Source Layout

- `configurator.py` - Tkinter configuration app and runtime package writer.
- `profiles/` - shipped and user-created profile JSON files.
- `tools/scripts/install_runtime.py` - player setup/install script used by `Setup.bat`.
- `tools/scripts/package_release.py` - developer release packager.
- `tools/scripts/build_dll.py` - developer DLL build helper.
- `tools/dll/src/` - UE4SS C++ runtime source.
- `tools/dll/include/` - runtime headers.

Generated folders such as `builds/`, `dist/`, `backups/`, `recovery/`, `runtime_mods/`, `tools/dll/out/`, and `tools/dll/ue4ss_build/` are ignored for source sharing.

## Developer Build

Requirements:

- Python 3.13 or compatible Python 3 with Tkinter.
- Visual Studio 2022 Build Tools with MSVC.
- CMake.
- Git.
- Rust toolchain, required by the UE4SS C++ template dependencies.

Build the DLL:

```powershell
python tools\scripts\build_dll.py
```

Package the player release:

```powershell
python tools\scripts\package_release.py
```

The player zip is written to:

```text
dist\IcarusConfigMod.zip
```

## Runtime Validation

The DLL writes per-setting validation lines such as `SETTING_STATUS`, `VALIDATION SettingsSummary`, and `VALIDATION GreenLight` to its runtime log after Icarus starts. For a clean beta pass, the latest green-light line should show `GreenLight=YES` with `Partial=0 Pending=0 Skipped=0 Unsupported=0 MissingFields=0`.

## Git Hygiene

Do not commit local game saves, generated packages, logs, backups, UE4SS downloaded binaries, or build trees. The `.gitignore` is set up for this.
