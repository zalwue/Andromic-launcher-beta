# Andromic Launcher 2.2 — development notes

## Visual foundation

- Added a configurable wallpaper image behind the launcher interface.
- Added a softened wallpaper rendering pass to create a frosted-glass backdrop.
- Added translucent glass surfaces for cards and input controls when a wallpaper is active.
- Added independent Frosted Glass toggle in Customization.
- Added wallpaper selection and clear controls in Customization.
- Preserved existing theme presets, accent colour, density, radius, font scaling and sidebar placement.

## Validation

- Python bytecode compilation: passed.
- Core unit tests: passed.
- Native Qt GUI rendering has not yet been run in this environment because PySide6 is not installed here.

### Build pipeline updates
- Added Linux x86_64 AppImage packaging to the GitHub Actions workflow.
- AppImage is uploaded as a build artifact and attached to tagged GitHub Releases.
- Added CI-generated fallback application icons when icon binaries are absent from the source archive.
