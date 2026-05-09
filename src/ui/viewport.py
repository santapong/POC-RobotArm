"""Placeholder viewport widget for the station shell.

The 3D viewport in this Phase-1 slice is intentionally **not** an
embedded PyBullet OpenGL context: embedding the PyBullet GL window inside
Qt is brittle on Linux and adds complexity that does not pay back at
this stage. Instead, this widget shows a static label telling the user
that the PyBullet sim should be launched separately (the **Robot →
Launch sim** action in :class:`src.ui.app.StationMainWindow`
subprocess-spawns the existing ``python -m src.simulation.gui`` window).

A future phase can swap this widget out for a real GL context (e.g.
``QOpenGLWidget`` driving an external scene graph) without disturbing
the surrounding shell.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

VIEWPORT_PLACEHOLDER_TEXT = (
    "Viewport: launch the PyBullet sim from the Robot menu"
)


class StationViewport(QWidget):
    """Phase-1 placeholder host for the 3D viewport."""

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._label = QLabel(VIEWPORT_PLACEHOLDER_TEXT, self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

    def set_status(self, text: str) -> None:
        """Update the placeholder text (used to surface sim launch errors)."""
        self._label.setText(text)


__all__ = ["StationViewport", "VIEWPORT_PLACEHOLDER_TEXT"]
