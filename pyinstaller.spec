# Portable build for Ubuntu (PyInstaller)
# Build: pyinstaller -y pyinstaller.spec

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

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

hiddenimports = []
hiddenimports += collect_submodules("PySide6")
hiddenimports += collect_submodules("PySide6.QtWebEngineCore")
hiddenimports += collect_submodules("PySide6.QtWebEngineWidgets")

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.zipfiles,
    a.datas,
    name="NetPlanner",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
