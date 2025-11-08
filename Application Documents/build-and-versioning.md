# Build & Versioning (EN)

## Version
- Current: `1.5.0 Alpha`.
- Version file: `version-1.5.0-alpha.txt` (metadata for the executable).

## Build with PyInstaller
- Spec file: `CodemindEditor.spec`.
- Build command: `pyinstaller CodemindEditor.spec`.
- Icon and resources: `assets/` folder.

## Dependencies
- Install: `pip install -r requirements.txt`.
- Confirm PyQt/PySide versions for your environment.

## Notes
- Ensure `CodemindEditor.spec` points to the correct version file.
- Test the executable after build to validate windows and panels.