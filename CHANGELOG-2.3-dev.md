# Andromic Launcher 2.3-dev — Stage 3

## Downloader
- Streaming chunked downloads (nothing loaded fully into memory)
- Temporary `.part`, SHA-1 + exact size verification, atomic rename, cleanup on error/cancel
- Retries on temporary network errors (no retry on permanent 4xx; retry 408/429/5xx)
- Cancellation (`CancelToken`) wired into Minecraft/Java/libraries/assets/mods/modpacks + Play page button
- Real progress: bytes done/total, live speed (B/s), ETA; current-file speed, not just finished files
- Concurrency modes: Economy 2 / Balanced 4 / Fast 8 (default) / Maximum 12 / Manual (1..32), persisted in config
- Applied to Minecraft, Java Runtime, libraries, assets, mods and modpacks; bounded pools
- `Reporter.download` realtime callback; `net.download`/`download_many` backwards compatible

## Minecraft Servers
- Recommended servers on first open / when no custom servers; recommendations kept in source
- Custom servers: name + `host:port`, default port 25565, strict validation, persistence, edit, delete, re-show recommendations
- Status, Minecraft version, player count, latency when available
- Double-click or «Играть» to join via existing launch logic

## MIUIX branding
- MIUIX branding in code, UI, themes, presets, README, docs, i18n

## Typography
- Modern sans (Inter preferred, then system sans); antialiasing; DPI/HiDPI scaling; no unnecessary text shadows/outlines; sensible sizes/weights

## Liquid Glass
- Real translucency + real backdrop blur for panels; per-layer opacity (window/panel/border) + blur radius
- Native backdrop attempt (Windows 11 DWM / macOS / KDE X11) with clean fallback; honest capability reporting
- Works independent of background image; optional background image; Frosted Glass toggle retained

## Mods
- Richer Modrinth cards; detailed project view; install status; scrollable; no invented metadata
- Separate «Установленные» tab; enable/disable; delete; open mods folder; resource packs/shaders/modpacks retained
- Search shows only installable projects; installed not duplicated as a separate list

## Compatibility
- Windows/Linux/macOS; no required AVX/AVX2; platform-specific calls feature-detected + guarded

## Testing
- New tests: `tests/test_stage3_downloader.py`, `tests/test_stage3_servers.py`
