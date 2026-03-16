from PySide6.QtWidgets import QApplication

from app.ui_window import MainWindow


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
