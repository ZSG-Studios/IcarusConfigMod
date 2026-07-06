# Release Notes

## v0.1.7-beta - Transfer Vault Checked Items

This update adds persistent checked row state to the Transfer Vault item browser and improves player inventory names.

### Added

- Item rows in the Transfer Vault source browser now show checkbox-style `[ ]` / `[x]` state.
- Checked item rows stay checked when switching the inventory dropdown or refreshing the visible list.
- The summary now reports total checked rows and how many checked rows are move-ready JSON items.
- `Move Checked To Vault` uses checked move-ready JSON items; if nothing is checked, the highlighted row still works as a fallback.
- The source browser now works one exposed inventory at a time; the all-inventories working view was removed.
- Internal attachment, ammo-slot, and prospect-manager inventories are hidden from the dropdown.
- Same-name containers are separated with unique suffixes so each dropdown option maps to one actual inventory.

### Fixed

- Player recorder inventories now use prospect/local character names when `PlayerID` and `ChrSlot` can be matched.
- View-only live prospect rows can be checked for tracking, but export refuses them until the binary writer is safe.

## v0.1.6-beta - Transfer Vault Inventory Names

This update improves the Transfer Vault inventory dropdown labels so items are grouped under the inventory they are actually saved in.

### Fixed

- Deployable inventories now prefer `StaticItemDataRowName` names such as `Wood Cupboard`, `Fabricator`, `Concrete Furnace V2`, `Oxite Dissolver`, and similar rows.
- Player recorder inventories are labeled as player inventories instead of generated world container IDs.
- Mount recorder inventories are labeled as mount inventories instead of generated world container IDs.
- Prospect container-manager fallbacks are labeled as `Prospect Inventory` instead of `IcarusGameMode`.
- Generated actor IDs are now used only as a fallback when no better owner name is available.

## v0.1.5-beta - Transfer Vault Inventory Browser

This update makes the Transfer Vault source browser usable as an inventory viewer instead of one long mixed list.

### Added

- Added an inventory dropdown to the Transfer Vault source panel.
- Selecting an inventory filters the item list to that inventory.
- Live prospect blob items now show decoded amounts when available.
- Source rows now use clean item names and simple `x amount` display text.
- Summary now reports detected inventory count, move-ready JSON items, and view-only live items.

## v0.1.4-beta - Transfer Vault Slot Safety

This update adds hard preflight checks before Transfer Vault restore writes.

### Fixed

- Transfer Vault restore now checks known target inventory capacity before writing.
- Restore refuses to continue if the target has fewer open slots than the item restore needs.
- Restore refuses inventories that already contain duplicate explicit slot assignments.
- Restore refuses inventories that already contain out-of-range explicit slot assignments.
- MetaInventory saves with no fixed slot cap are treated as append-only JSON inventories, so the app does not invent fake slot limits.

## v0.1.3-beta - Transfer Vault Item Viewer

This update improves the Transfer Vault scanner so players can see item names stored inside live prospect inventory data.

### Added

- Transfer Vault now decodes `ItemStaticData` rows from compressed `ProspectBlob.BinaryBlob` data.
- Live prospect backpack, world, and container inventory entries are listed with item row names in the source list.
- Prospect blob summaries now report decoded item rows instead of rough text marker hits.

### Limit

- Live prospect blob items are still read-only. Verified JSON-backed meta/loadout items can be moved through the vault, but live backpack, hotbar, belt, equipment, mount cargo, and world container item movement remains disabled until the Unreal property writer is validated.

## v0.1.2-beta - Transfer Vault Beta

This update focuses on runtime safety, validation accuracy, and release packaging cleanup.

### Added

- Added a `Transfer Vault` tab for an offline shared stash across local Icarus player folders.
- Added vault scanning for local SteamID folders, JSON-backed inventories, loadout meta items, active prospects, and prospect members.
- Added exclusive `vault.lock` protection and a transaction ledger at `transfer_vault/ledger.jsonl`.
- Vault export/import creates full save backups first and refuses to move items while Icarus is running.
- Live prospect inventory blobs are detected and reported with item/inventory marker counts.

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

### Transfer Vault Limit

Current beta support moves verified JSON-backed meta/loadout items. Live backpack, hotbar, belt, equipment, mount cargo, and world container items inside `ProspectBlob.BinaryBlob` are scan-only until the Unreal property writer is validated.
