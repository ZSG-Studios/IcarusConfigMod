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
