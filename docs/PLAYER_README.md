# Icarus Configuration Mod

Portable UE4SS C++ runtime configuration mod for Icarus.

## Install

1. Extract the zip anywhere outside the Icarus install folder.
2. Run `IcarusConfigMod.exe`.
3. Select `Vanilla Defaults`, `Premade_Configuration`, or a saved/imported custom profile.
4. Click the install/apply button.
5. The app creates an automatic player/world save backup before applying.
6. If prompted, select your Icarus folder or `Icarus\Binaries\Win64`.
7. Fully close and restart Icarus.
8. Enter a prospect/session so Icarus loads the runtime tables.

No Python, batch files, PowerShell scripts, Visual Studio, CMake, Rust, Nuitka, or PyInstaller are required for players.

## Included Files

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

`main.dll` is shipped at the package root for a clean download layout. The configurator installs it into the UE4SS-required game layout when applying settings.

Runtime backups, player/world save backups, logs, saved Icarus folder selection, and generated runtime work files are stored under `%LOCALAPPDATA%\ZSG Studios\IcarusConfigMod\`, not in the extracted mod folder.

## Profiles

The app starts on `Vanilla Defaults`. The included premade profile is `Premade_Configuration`.

Saved or imported profiles are copied into `profiles/` and appear in the dropdown without `.json`.

## Validation

After restarting Icarus and entering a session, check the runtime validation log in the configurator.

A clean pass should show:

```text
VALIDATION GreenLight ... GreenLight=YES
Partial=0 Pending=0 Skipped=0 Unsupported=0 MissingFields=0
```

## Reset

Open `IcarusConfigMod.exe` and use `Reset Installed Mod` from the console/actions area.

## Save Backups

Use the `Save Backups` tab to create, list, open, and restore Icarus save backups. The app backs up `Saved\PlayerData`, `Saved\SaveGames`, `Saved\ExtraData`, and `steam_autocloud.vdf` when they exist.

Every apply creates a `before_apply` backup. Restoring a backup creates a `pre_restore` backup first. Close Icarus before creating or restoring backups.

## Safety

The app backs up saves before applying, but manual extra backups are still recommended before using inventory, stack, slot, backpack, free-craft, or recipe-array options. Lowering inventory or container slots below current contents can risk item loss.
