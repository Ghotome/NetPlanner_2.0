Vendored AppImage tooling lives in this directory.

Expected files:
- `appimagetool.AppImage` and `appimagetool.AppImage.sha256`: default tool used for `x86_64`.
- `appimagetool-aarch64.AppImage` and `appimagetool-aarch64.AppImage.sha256`: optional tool that enables `aarch64` AppImage builds in GitHub Actions.

The Linux workflows skip the `aarch64` AppImage job when the architecture-specific binary or checksum file is missing.
