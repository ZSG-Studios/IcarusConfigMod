# Icarus Configuration Mod

UE4SS C++ runtime configuration mod for Icarus balance settings.

Open source: https://github.com/ZSG-Studios/IcarusConfigMod

## Player Install

1. Download `IcarusConfigMod.zip` from the release.
2. Extract it anywhere outside the Icarus install folder.
3. Run `IcarusConfigMod.exe`.
4. Select `Vanilla Defaults`, `Premade_Configuration`, or a saved/imported custom profile.
5. Click the install/apply button in the configurator.
6. The configurator creates an automatic player/world save backup before applying.
7. Fully close and restart Icarus.
8. Enter a prospect/session so Icarus loads the runtime tables.
9. Check the runtime validation log from the configurator if you want to confirm a clean pass.

The release is portable for players. It does not require Python, PowerShell scripts, batch files, Visual Studio, CMake, Rust, Nuitka, or PyInstaller on the player's system.

If Icarus is not found automatically, the configurator prompts the player to select the Icarus folder or `Icarus\Binaries\Win64` and saves that path under `%LOCALAPPDATA%\ZSG Studios\IcarusConfigMod\user_settings.json`.

Runtime backups, player/world save backups, logs, and generated runtime work files are stored under `%LOCALAPPDATA%\ZSG Studios\IcarusConfigMod\` instead of beside the portable exe or inside the extracted program folder.

The configurator also includes a `Transfer Vault` tab. It scans all local Icarus player folders, detects active prospect members, decodes live prospect inventory item names from `ProspectBlob.BinaryBlob`, and provides a locked shared stash for verified JSON-backed items such as `MetaInventory.json` and loadout meta items. Live backpack/world/container items from the compressed Unreal property blob are shown read-only until the binary inventory writer is verified.

## Player Package Layout

The player zip keeps the mod files at the root. The configurator is built as a portable Nuitka standalone app bundle instead of a PyInstaller one-file archive to reduce generic AV false positives:

```text
IcarusConfigMod.exe
UE4SS.dll
main.dll
Configuration_Mod/
profiles/
*.dll / *.pyd runtime files required by the portable app
README.md
PLAYER_README.txt
LICENSE
```

`main.dll` is shipped at the package root for a clean download layout. When the player applies settings, the configurator installs it into the UE4SS-required game layout: `Configuration_Mod\dlls\main.dll`.

The player zip must not contain `.bat`, `.ps1`, `.py` launch scripts, PyInstaller artifacts, `tools/`, `builds/`, `runtime_mods/`, `backups/`, `configurator.log`, or `Configuration_Mod/dlls/`.

## Profiles

The release ships with:

- `Vanilla Defaults`
- `Premade_Configuration`

`Vanilla Defaults` is intentionally selected on first launch. Saved or imported player profiles are copied into `profiles/` and then appear in the same profile dropdown without the `.json` extension.

## Runtime Validation

The DLL writes validation lines such as `SETTING_STATUS`, `VALIDATION SettingsSummary`, and `VALIDATION GreenLight` after Icarus starts.

For a clean beta pass, the latest green-light line should show:

```text
VALIDATION GreenLight ... GreenLight=YES
Partial=0 Pending=0 Skipped=0 Unsupported=0 MissingFields=0
```

If `GreenLight=NO`, check nearby `SETTING_STATUS` lines to see which active setting needs attention.

### Debug Validation

Developer builds support an opt-in `[debug_validation]` section in `settings.ini`. Normal generated configs leave it disabled. When enabled with `forceAllSupported = true`, the DLL forces supported settings to non-vanilla test values, captures the default/current value before each mutation, computes the expected value, writes it, reads it back, and fails validation if the result does not match.

Install a local full-validation runtime:

```powershell
python tools\scripts\install_runtime.py --debug-validation --debug-log-each
```

Use `--debug-risky-arrays` only when intentionally testing free-craft style array clearing. The runtime log will include `VALIDATION DebugConfig`, `MATH_CHECK`, `MATH_CHECK_FAIL`, `SETTING_STATUS`, and `VALIDATION GreenLight` lines.

## Current Beta Notes

See [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md) for the latest beta fix notes.

Recent runtime fixes in `v0.1.4-beta`:

- Skinning yield now increases carcass recipe output counts instead of touching `D_ToolDamage.Skinning_Efficiency`, which could make carcasses deplete too quickly.
- Baseline `0` values now remain `0` during multiplier math, preventing disabled/sentinel timers from becoming one-second timers.
- Free-craft no longer clears `ResourceInputs`, avoiding live resource drain behavior.
- Generic recipe/material/free-craft array edits skip carcass processor rows.
- Stack and container slot runtime mutation is clamped so it cannot shrink below the vanilla baseline.
- Transfer Vault now decodes and lists live prospect inventory item row names read-only, including items stored in compressed prospect/container inventory data.
- Transfer Vault restore now performs slot safety checks before writing: no overwrite, no duplicate explicit slots, no out-of-range slots, and no restore when known capacity has no open slot.

Some settings are table-backed rather than direct live-player writes. Health, stamina, carry capacity, movement speed, and regen mutate `D_CharacterStartingStats` grants, so the game may recalculate visible values only after session load, spawn, respawn, healing, or other stat refresh behavior. Air control is applied directly to loaded movement components and should be more immediately visible.

## Save Backups

The configurator has a `Save Backups` tab for Icarus player/world saves. It backs up these save components when present:

- `%LOCALAPPDATA%\Icarus\Saved\PlayerData`
- `%LOCALAPPDATA%\Icarus\Saved\SaveGames`
- `%LOCALAPPDATA%\Icarus\Saved\ExtraData`
- `%LOCALAPPDATA%\Icarus\Saved\steam_autocloud.vdf`

Every apply creates a `before_apply` backup first. Players can also create manual backups, open the backup folder, refresh the backup list, and restore a selected backup from the UI. Backup restore creates a `pre_restore` backup before replacing matching save components.

Backup and restore refuse to run while Icarus is open so the app does not copy or replace live save files.

## Transfer Vault

The `Transfer Vault` tab is an offline shared stash for local players and worlds.

- Scans all local `%LOCALAPPDATA%\Icarus\Saved\PlayerData\<SteamID>` folders.
- Detects prospect members from prospect save metadata.
- Detects compressed live-world prospect inventory blobs and lists decoded item row names read-only.
- Moves verified JSON-backed items into `%LOCALAPPDATA%\ZSG Studios\IcarusConfigMod\transfer_vault\vault.json`.
- Uses an exclusive `vault.lock` file so two vault operations cannot run at the same time.
- Writes a transaction ledger to `transfer_vault\ledger.jsonl`.
- Creates a full save backup before every vault export/import.
- Refuses to run item moves while Icarus is open.
- Checks known target slot capacity before restore and refuses to write if no open slot is available.

Current beta support is intentionally conservative: JSON-backed meta/loadout items can be moved; live backpack/hotbar/container items inside the prospect binary blob are listed read-only until the Unreal property writer is fully validated.

## Source Layout

- `app/configurator.py` - Tkinter configurator and runtime installer.
- `config/profiles/` - source profile JSON files.
- `docs/NEXUS_DESCRIPTION.bbcode` - Nexus-ready BBCode description.
- `docs/PLAYER_README.md` - player-only README copied into the release zip.
- `docs/RELEASE_CHECKLIST.md` - beta packaging checklist.
- `Dev Setup.bat`, `Build DLL.bat`, `Package Release.bat` - source-only convenience wrappers.
- `tools/scripts/dev_setup.py` - developer environment checker.
- `tools/scripts/package_release.py` - release packager.
- `tools/scripts/build_dll.py` - UE4SS C++ DLL build helper.
- `tools/dll/src/` - UE4SS C++ runtime source.
- `tools/dll/include/` - runtime headers.

Generated folders such as `dist/`, `builds/`, `backups/`, `recovery/`, `runtime_mods/`, `save_backups/`, `tools/dll/out/`, `tools/dll/ue4ss_build/`, `tools/exe_build/`, and `tools/package_work/` are ignored for source sharing. Player-side mutable state is written to `%LOCALAPPDATA%\ZSG Studios\IcarusConfigMod\`.

## Developer Setup

Requirements:

- Python 3.13 or compatible Python 3 with Tkinter.
- Visual Studio 2022 Build Tools with MSVC.
- CMake.
- Git.
- Rust toolchain, required by UE4SS C++ template dependencies.
- Nuitka, used only for building the portable player app bundle.

Check the local environment:

```powershell
python tools\scripts\dev_setup.py
```

Install safe missing dependencies where the script can automate it:

```powershell
python tools\scripts\dev_setup.py --install
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

Source-only root batch wrappers are available for convenience:

```text
Dev Setup.bat
Build DLL.bat
Package Release.bat
```

These wrappers are for source developers only and are not copied into the player zip.

## Third-Party Credits

Built with UE4SS / RE-UE4SS and the UE4SS C++ Mod Template. UE4SS uses third-party dependencies including ImGui, glfw, glad, Zydis, PolyHook 2, asmjit, fmt, Tracy, and glaze. The configurator uses Python and Tkinter. All third-party tools and libraries remain credited to their respective authors and maintainers.

## Git Hygiene

Do not commit local game saves, generated packages, logs, backups, downloaded UE4SS files, build trees, or local `user_settings.json`.
