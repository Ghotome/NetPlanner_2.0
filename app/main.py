import os
import sys
from pathlib import Path


def _should_use_software_rendering() -> bool:
    if os.environ.get("NETPLANNER_HARDWARE_RENDERING") == "1":
        return False
    if os.environ.get("NETPLANNER_SOFTWARE_RENDERING") == "1":
        return True
    return os.environ.get("NETPLANNER_RENDERER_MODE") == "software"


def _configure_runtime_environment() -> bool:
    if os.environ.get("NETPLANNER_FORCE_XCB") == "1":
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    use_software_rendering = _should_use_software_rendering()
    if use_software_rendering:
        os.environ.setdefault("QT_OPENGL", "software")
        os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        extra_flags = ["--disable-gpu", "--disable-gpu-compositing"]
        for flag in extra_flags:
            if flag not in flags.split():
                flags = f"{flags} {flag}".strip()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
    return use_software_rendering


def _mark_startup_ready() -> None:
    marker = os.environ.get("NETPLANNER_STARTUP_MARKER")
    if not marker:
        return
    try:
        marker_path = Path(marker)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("ready\n", encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    use_software_rendering = _configure_runtime_environment()
    from PySide6.QtCore import QCoreApplication, Qt, QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.domain import NetworkProject
    from app.ui.main_window import MainWindow
    if use_software_rendering:
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL)
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
    QTimer.singleShot(0, _mark_startup_ready)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
    
