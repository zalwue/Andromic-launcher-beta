# Andromic Launcher

A lightweight, offline-first Minecraft launcher with a clean HyperOS-inspired interface.
Written in Python with a PySide6 (Qt) interface. Runs on Windows, Linux and macOS.

## Features

- Offline profiles with multiple accounts, avatars and custom skins
  (local PNG or copied from a Mojang nickname)
- Every release from 1.16.5 up to the newest one in the Mojang manifest, plus snapshots
- Vanilla, Fabric, Quilt, Forge, NeoForge and OptiFine
- Automatic Java selection (8, 17, 21, 25) per Minecraft version; the runtime is downloaded
  on demand from Mojang, with Eclipse Temurin as a fallback
- Memory, resolution, render distance, FPS limit, graphics mode and JVM flags
- Modrinth integration: mods, resource packs, shaders and modpacks (`.mrpack`)
- Automatic Fabric API installation
- One-click performance preset (Sodium, Lithium, Iris and friends)
- Separate instances with their own mods, packs and worlds
- Server list with live status (players, latency, version) and one-click join
- World backups and a crash log analyser
- Light and dark themes, English and Russian interface

## Run from source

Requires Python 3.9+.

```bash
pip install -r requirements.txt
python -m andromic
```

## Build a standalone executable

```bash
# Windows
build.bat

# Linux / macOS
./build.sh
```

The result is placed in `dist/`.

## Project layout

```
andromic/
  core/   launcher logic, no GUI dependencies (standard library only)
  ui/     PySide6 interface: theme, widgets, dialogs, pages
  i18n.py translations
main.py   entry point for packaging
```

Launcher data (versions, libraries, instances, runtimes) is stored in:

| OS      | Location                               |
|---------|----------------------------------------|
| Windows | `%APPDATA%\Andromic`                   |
| macOS   | `~/Library/Application Support/Andromic` |
| Linux   | `~/.local/share/andromic`              |

## Notes

- Skins are applied through a generated resource pack that replaces the default player skins.
  They are visible only to you unless the server supports offline skins.
- OptiFine cannot be downloaded automatically. Use *Get OptiFine* in the instance dialog,
  then *Install from jar*.
- Offline accounts cannot join servers running in online mode.

## License

Andromic Launcher is free software released under the GNU General Public License v3.0.
See [LICENSE](LICENSE) for the full text.

```
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.
```
