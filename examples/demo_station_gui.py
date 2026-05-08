"""Launch the PySide6 station shell with a sample station preloaded.

Run from the repo root::

    python examples/demo_station_gui.py

This is the end-to-end visual smoke test for the Phase-1 desktop shell:
it opens the main window with a small ``demo_station`` already built,
so the Outliner has rows to display and the user can immediately try
*Run → Emit RAPID*, *Robot → Spawn ...*, etc.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from src.ui.app import StationMainWindow, _build_demo_station


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = StationMainWindow(_build_demo_station())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
