"""PySide6-based desktop shell for the RobotStudio-style station.

The :class:`StationMainWindow` (in :mod:`src.ui.app`) hosts an Outliner
tree, a code-preview panel for emitted RAPID / KRL / URScript, and a
viewport placeholder. The 3D viewport in this Phase-1 slice is delegated
to the existing PyBullet GUI launched as a subprocess; embedding the
PyBullet GL window inside Qt is brittle on Linux and is deliberately out
of scope here.

Importing this package pulls Qt, so headless paths should keep using
:mod:`src.station.scene` (which is Qt-free) directly.
"""

from .app import StationMainWindow

__all__ = ["StationMainWindow"]
