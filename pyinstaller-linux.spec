# Linux onedir build used for AppImage and DEB packaging.

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

QT_HIDDENIMPORTS = collect_submodules("PySide6")

datas = []
datas += collect_data_files("PySide6")
datas += collect_data_files("PySide6.QtWebEngineCore")
datas += collect_data_files("PySide6.QtWebEngineWidgets")
datas += [("app/web", "app/web")]
datas += [("app/ui/icons", "app/ui/icons")]
datas += [("app/icon.svg", "app/icon.svg")]

binaries = []
binaries += collect_dynamic_libs("PySide6")
binaries += collect_dynamic_libs("PySide6.QtWebEngineCore")
binaries += collect_dynamic_libs("PySide6.QtWebEngineWidgets")

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=QT_HIDDENIMPORTS,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NetPlanner_2.0",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="NetPlanner_2.0",
)
