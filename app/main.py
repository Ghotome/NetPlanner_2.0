import sys

from PySide6.QtWidgets import QApplication, QMainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Network Planner")
    window.resize(1024, 640)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
