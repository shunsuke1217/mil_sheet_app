"""ミルシート読み取り: 画面の起動。"""
import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from millsheet.applog import setup_logging


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("ミルシート読み取り")
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
