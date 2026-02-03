import sys

from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.domain import NetworkProject
from app.ui.main_window import MainWindow


def main() -> int:
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
