"""Start the POS desktop app."""

import sys

from PySide6.QtWidgets import QApplication

from app.infrastructure.database.session import init_db
from app.ui.main_window import MainWindow
from app.ui.theme import build_stylesheet


def main() -> None:
    init_db()
    app = QApplication(sys.argv)
    app.setApplicationName("POS")
    app.setStyleSheet(build_stylesheet("light"))
    window = MainWindow()
    window.set_theme("light")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
