# Release Notes

## Beta Runtime Fix Update

This update focuses on runtime safety, validation accuracy, and release packaging cleanup.

### Fixed

- Fixed carcasses disappearing too quickly after kills.
- Fixed skinning yield targeting the wrong runtime path. Skinning yield now increases carcass recipe output counts instead of changing `D_ToolDamage.Skinning_Efficiency`, which could make carcasses deplete faster.
- Fixed zero-value runtime math. Baseline `0` values now stay `0` instead of being clamped to `1`, preventing disabled or sentinel timers from becoming one-second timers.
- Fixed free-craft debug/runtime mutation so it does not clear `ResourceInputs`, which can drive live resource/item drain.
- Added safety handling so stack and container slot settings do not shrink below vanilla baseline during runtime mutation.
- Added carcass recipe safety handling so generic processing/material/free-craft array edits do not mutate carcass processor rows.

### Validation

- Debug validation can force supported settings to test values and log before/expected/actual math checks.
- Runtime validation now avoids fake green passes by reporting missing fields, partial application, skipped targets, unsupported targets, and math failures.
- Body diagnostics were added for carcass-related tables when debug validation is enabled.

### Known Behavior

- Some settings are table-backed rather than direct live-player writes. Health, stamina, carry capacity, movement speed, and regen mutate `D_CharacterStartingStats` grants. The game may cache current pawn values, combine them with armor/talents/buffs, or recalculate them only after session load, spawn, respawn, or healing.
- Air control is applied as a direct runtime scan of loaded movement components and should be more immediately visible.
- A clean validation log proves the table/runtime target changed as expected, but the in-game HUD may not always display a simple visible `old value * multiplier` result for derived stats.

### Packaging

- Player releases use `IcarusConfigMod.exe` as the only required launcher.
- Players do not need Python, PowerShell scripts, batch files, Visual Studio, CMake, Rust, Nuitka, or PyInstaller.
- Runtime state, logs, generated work files, and save backups are stored under `%LOCALAPPDATA%\ZSG Studios\IcarusConfigMod\`.
- The player zip should not include source tools, build folders, `.bat`, `.ps1`, or player-side `.py` launch scripts.
