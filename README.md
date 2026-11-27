
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
- Streaming downloader: `.part` files, SHA-1 + size verification, atomic rename, retries,
  cancellation, real speed + ETA, and concurrency modes
  (Economy 2 / Balanced 4 / Fast 8 / Maximum 12 / Manual; default Fast)
  applied to Minecraft, Java Runtime, libraries, assets, mods and modpacks
- Memory, resolution, render distance, FPS limit, graphics mode and JVM flags
- Modrinth integration: rich project cards, detailed view, mods, resource packs,
  shaders and modpacks (`.mrpack`); installed content on a separate «Installed» tab
- Automatic Fabric API installation
- One-click performance preset (Sodium, Lithium, Iris and friends)
- Separate instances with their own mods, packs and worlds
- Server list with live status (players, latency, version), recommended servers,
  custom server add/edit/remove (`host:port`, default port 25565) and one-click join
- World manager: rename, duplicate, export and import worlds, with safe NBT metadata editing
- Backup manager: world or full-instance archives, manifests, verification, restore and retention
- Per-instance screenshot gallery and crash log analyser with conservative one-click fixes
- Diagnostics page: environment, folders, Java, configuration, backups and latest-log checks,
  report export and safe repairs
- Local co-op rooms with shareable invite codes and LAN discovery
- Customization presets: accent colour, density, corner radius, font scale, animations and background
- Prism Launcher / MultiMC ZIP import and Modrinth `.mrpack` import (drag and drop supported)
- GitHub Releases update checks at startup and one-click download for the current OS
- Custom MIUIX / HyperOS accent colour (Liquid Glass)
- Light and dark themes, English and Russian interface


<img width="1366" height="768" alt="Снимок экрана_2026-11-23_22-43-54" src="https://github.com/user-attachments/assets/2b1725df-6b9d-4e14-bfe7-83680b0e87da" />




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

## Tests

```bash
python -m unittest discover -s tests -v
# or
python -m pytest tests
```

The suite covers diagnostics, the world manager and NBT round-tripping, backups and
safe restore, rooms and invite codes, appearance customisation, cross-platform path
handling and a simulated source release ZIP.

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
| Linux   | `~/.local/share/Andromic`              |

## Notes

- The importer supports Prism Launcher and MultiMC exported ZIP archives.
- The updater downloads the matching release asset; installation/replacement is manual to avoid replacing a running executable unsafely.
- Microsoft OAuth is not configured in this build: it requires a registered Microsoft application client ID and redirect configuration.

- Skins are applied through a generated resource pack that replaces the default player skins.
  They are visible only to you unless the server supports offline skins.
- OptiFine cannot be downloaded automatically. Use *Get OptiFine* in the instance dialog,
  then *Install from jar*.
- Offline accounts cannot join servers running in online mode.

## Community & Updates

Follow development news, sneak peeks, and new releases on our official Telegram channel:

- **Telegram:** - [Our official channel](https://t.me/andromichannel)








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


## Platform compatibility notes

- Java runtime caches are separated by operating system and CPU architecture so switching
  between native Apple Silicon and Intel/Rosetta environments cannot silently reuse an
  incompatible runtime.
- Apple Silicon detection uses the native hardware capability reported by macOS, including
  when the launcher itself is running through Rosetta.
- Minecraft starts with macOS-specific first-thread and Dock JVM options; the Dock icon is
  included only when the packaged icon asset is available.
- Qt Widgets use Qt's built-in high-DPI handling. The launcher avoids capturing and
  compositing full-window screenshots during every navigation change to reduce UI work,
  especially on Retina displays.


## Linux compatibility

- The Linux build script uses baseline x86-64 compiler flags for native extensions
  built from source. This avoids accidentally targeting the build machine with
  `-march=native`; it does not change prebuilt binary wheels.
- For wider glibc compatibility, build Linux releases on the oldest supported
  distribution (Ubuntu 22.04 is the current compatibility target) rather than a
  newer host. PyInstaller bundles Python packages but does not bundle glibc.
- If a target machine reports `Illegal instruction`, inspect the executable and
  bundled native libraries for unsupported CPU instructions. Compiler flags set
  after installing prebuilt wheels cannot repair those already-compiled binaries.


## Andromic 2.1b CPU compatibility policy

- PySide6 is pinned to 6.9.3 for reproducible builds while the Qt 6.10 Linux
  CPU-baseline change is being avoided and validated.
- Linux CI builds on Ubuntu 22.04 and runs a QtCore import smoke test under
  QEMU with SSE4.2 and POPCNT masked. This is a compatibility regression check,
  not a substitute for testing on the actual target computer.
- Distributable native code must not be compiled with `-march=native` or other
  host-CPU auto-detection. The generic x86-64 baseline is the default target.
- Compiler flags do not alter prebuilt wheels. Every bundled native wheel must
  be pinned and audited independently.


## Ely.by accounts

Andromic supports direct Ely.by Yggdrasil login using the official `POST /auth/authenticate` and `POST /auth/refresh` endpoints. The password is used only for the sign-in request and is not stored. The returned access token and client token are saved in the local launcher configuration so the game can be launched without a separate Andromic account or server. The first Ely.by launch downloads the official authlib-injector release from GitHub and starts Minecraft with `-javaagent:<path>=ely.by`.

The local `config.json` contains the Ely.by access token. Treat this file as sensitive and do not share it. Removing the Ely.by profile from Andromic does not sign out or revoke the token at Ely.by; revoke it from your Ely.by account if needed.
