"""Busy / saving indicators for long UI operations."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QProgressDialog, QPushButton, QWidget


@contextmanager
def saving_indicator(
    parent: QWidget,
    button: QPushButton,
    *,
    message: str = "Saving…",
    title: str = "Save",
) -> Iterator[None]:
    """Show wait cursor, progress dialog, and temporarily disable the action button."""
    btn_label = button.text()
    progress = QProgressDialog(message, None, 0, 0, parent)
    progress.setWindowTitle(title)
    progress.setCancelButton(None)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)
    progress.show()
    button.setEnabled(False)
    button.setText("Saving…")
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    QApplication.processEvents()
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()
        progress.close()
        button.setEnabled(True)
        button.setText(btn_label)
