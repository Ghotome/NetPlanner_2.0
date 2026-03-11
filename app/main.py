import os
import sys
from pathlib import Path


def main() -> int:
    if os.environ.get("NETPLANNER_FORCE_XCB") == "1":
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    if os.environ.get("NETPLANNER_SOFTWARE_RENDERING") == "1":
        os.environ.setdefault("QT_OPENGL", "software")
        os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        extra_flags = ["--disable-gpu", "--disable-gpu-compositing"]
        for flag in extra_flags:
            if flag not in flags.split():
                flags = f"{flags} {flag}".strip()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.domain import NetworkProject
    from app.ui.main_window import MainWindow
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    icon_path = Path(__file__).resolve().parents[1] / "app" / "ui" / "icons" / "app_icons" / "app_icon_96_96.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    project = NetworkProject(id="default", name="Новий проєкт")
    window = MainWindow(project)
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
    
