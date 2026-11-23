# Andromic Launcher 2.1b — compatibility and stability update

## CPU compatibility policy

- Pin the bundled PySide6 dependency to 6.9.3 instead of accepting an unbounded
  Qt update. This avoids silently moving packaged builds onto the Qt 6.10 Linux
  CPU baseline while compatibility is being validated.
- Keep Linux native-source compilation on the generic x86-64 baseline; never use
  `-march=native` for distributable builds.
- Audit prebuilt wheels separately: compiler flags applied after installing a
  wheel cannot change the instructions already present in that wheel.
- Add a Linux CI smoke test that imports QtCore under a QEMU CPU model with
  SSE4.2, POPCNT and AVX features masked.

## Existing functionality

This release is based on the complete 2.0 development source tree. It retains
instances, version and loader management, Modrinth content, worlds, backups,
LAN Rooms, diagnostics, customization, screenshots, crash-log analysis,
Prism/MultiMC import, updater, and the existing Mimuix interface.

## Validation status

- Python bytecode compilation: passed in the preparation environment.
- Core unit tests: 35 passed in the preparation environment.
- Native PySide6 import under QEMU, GUI launch, and Windows/macOS/Linux package
  builds have not yet run in the preparation environment; GitHub Actions must
  verify them. The user's Celeron N3050 must also be tested before calling the
  CPU compatibility issue resolved. This source ZIP is
  not a claim that platform binaries have already been built or tested.


## Ely.by authentication integration

- Added direct Ely.by login using the documented Yggdrasil `/auth/authenticate` endpoint.
- Added token refresh through `/auth/refresh`; passwords are not persisted.
- Added optional 2FA code support using Ely.by's documented `password:code` format.
- Added first-run download of the official authlib-injector release with SHA-256 verification when GitHub exposes an asset digest.
- Added Ely.by credentials to the Minecraft launch arguments and `-javaagent:<jar>=ely.by`.
- Kept offline profiles available and skipped the offline resource-pack skin workaround for Ely.by profiles.
- Note: access tokens are stored in the local `config.json`; users should treat that file as sensitive.
