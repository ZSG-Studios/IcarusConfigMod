# Configuration_Mod UE4SS C++ DLL

This is the developer-only DLL source for the DLL-only runtime mod.

UE4SS requires this installed game mod shape:

```text
Mods/
  Configuration_Mod/
    enabled.txt
    settings.ini
    option_manifest.json
    runtime_config.json
    dlls/main.dll
```

`main.dll` must export UE4SS C++ lifecycle functions:

```text
start_mod
uninstall_mod
```

Do not ship a plain `DllMain` DLL. UE4SS rejects that form with
`Failed to find exported mod lifecycle functions`.

## Build

Run:

```powershell
python tools\scripts\build_dll.py
```

The script clones/updates the official UE4SS C++ template under
`tools\dll\ue4ss_build`, builds the mod with MSVC/Rust, and writes the
ship-ready DLL to:

```text
tools\dll\out\main.dll
```

The release packager ships `main.dll` at the player package root for a clean download layout.
The configurator copies that root `main.dll` into `Configuration_Mod\dlls\main.dll` when installing into the game.

Players do not receive the UE4SS C++ template, build cache, headers, or source.

## Live Bridge

The DLL reads `[live_bridge] enabled = true` from `settings.ini` and starts a lightweight runtime heartbeat when UE4SS loads the mod.

Heartbeat file:

```text
%LOCALAPPDATA%\ZSG Studios\IcarusConfigMod\live_bridge\status.json
```

The configurator uses this file for the Transfer Vault `Connect Live` check. It reports the running process ID, heartbeat age, mod path, and capability flags.

Inventory read/write capability is intentionally reported as guarded in this beta. Do not enable live item moves until the runtime code verifies Unreal inventory object discovery, item identity, open-slot checks, no-overwrite behavior, and lets the game own the save.

## Debug Validation

The DLL reads an opt-in `[debug_validation]` section from `settings.ini`.
With `enabled = true` and `forceAllSupported = true`, supported settings are forced to known test values during runtime validation. Each write captures the default/current value, computes the expected result, writes the value, reads it back, and logs `MATH_CHECK` or `MATH_CHECK_FAIL`.

Local install helper:

```powershell
python tools\scripts\install_runtime.py --debug-validation --debug-log-each
```

Add `--debug-risky-arrays` only when deliberately testing array-clearing behavior such as free craft.

## Runtime Safety Notes

- `skinning_yield` is intentionally applied to carcass processor output counts, not `D_ToolDamage.Skinning_Efficiency`. Touching skinning tool damage can make carcass durability deplete faster instead of producing more loot.
- Generic processor recipe array edits skip carcass recipe rows.
- Free craft clears `Inputs` and `QueryInputs` only. It does not clear `ResourceInputs` because that path can affect live resource consumption.
- Numeric mutation preserves baseline `0` values. This prevents disabled/sentinel timers from being clamped into active one-second timers.
- Stack and container slot mutations are clamped so runtime validation cannot shrink storage below the vanilla baseline.
- Per-container slot overrides use `[container_slots]` and target matching `D_InventoryInfo` rows before broad `slotGroup` range rules. When a per-container override is active for a row, the broad slot group skips that row.

Health, stamina, carry capacity, movement speed, and regen are currently applied through `D_CharacterStartingStats` stat grants. These are table-backed values, not direct live pawn writes, so visible in-game values may depend on when Icarus rebuilds the active character stats.
