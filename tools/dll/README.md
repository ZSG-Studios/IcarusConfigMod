# Configuration_Mod UE4SS C++ DLL

This is the developer-only DLL source for the DLL-only player mod.

The player package installs this shape:

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

The release packager copies only the compiled DLL into `builds` and `dist`.
Players do not receive the UE4SS C++ template, build cache, headers, or source.
