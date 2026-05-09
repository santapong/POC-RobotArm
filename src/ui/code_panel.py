"""Read-only code preview panel for emitted RAPID / KRL / URScript source.

A thin :class:`QPlainTextEdit` subclass with a monospace font and a
:meth:`set_source` setter. Using a plain-text edit (rather than a
syntax-highlighted view) keeps the dependency surface minimal: this is
Phase-1 scope, and the user can switch the preview between RAPID, KRL,
and URScript via the **Run** menu in the main window.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit


class CodePanel(QPlainTextEdit):
    """Monospace, read-only text widget for showing emitted source."""

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont("Monospace")
        font.setStyleHint(QFont.TypeWriter)
        font.setPointSize(10)
        self.setFont(font)
        self.setPlaceholderText(
            "Use the Run menu to emit RAPID, KRL, or URScript for the demo program."
        )

    def set_source(self, text: str) -> None:
        """Replace the panel's contents with ``text``."""
        self.setPlainText(text)


__all__ = ["CodePanel"]
