"""GUI smoke test for the PySide6 station shell.

Skipped unless ``RUN_GUI_TESTS=1`` is set, mirroring the existing
``tests/test_gui_smoke.py`` pattern. On a headless CI box the test can
still be exercised with::

    RUN_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen pytest tests/test_ui_smoke.py -v

The test instantiates :class:`StationMainWindow` with a small fixture
station, populates the outliner, and grabs a screenshot to
``artifacts/station_smoke.png``.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

if os.environ.get("RUN_GUI_TESTS") != "1":
    pytest.skip(
        "Set RUN_GUI_TESTS=1 to run UI smoke tests.", allow_module_level=True
    )

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.station.scene import (  # noqa: E402
    Frame,
    IOSignal,
    RobotEntry,
    Station,
    ToolEntry,
    WorkpieceEntry,
)
from src.ui.app import StationMainWindow  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "artifacts"


def _identity_quat() -> tuple[float, float, float, float]:
    return (1.0, 0.0, 0.0, 0.0)


def _fixture_station() -> Station:
    return Station(
        name="smoke_station",
        frames=(
            Frame("world", (0.0, 0.0, 0.0), _identity_quat(), parent=None),
            Frame("robot_base", (0.0, 0.0, 0.0), _identity_quat(), parent="world"),
            Frame("table", (0.5, 0.0, 0.0), _identity_quat(), parent="world"),
        ),
        robots=(RobotEntry("arm0", "abb_irb1200", "robot_base"),),
        tools=(
            ToolEntry(
                "gripper",
                "robot_base",
                tcp_xyz_m=(0.0, 0.0, 0.12),
                tcp_quat_wxyz=_identity_quat(),
            ),
        ),
        workpieces=(WorkpieceEntry("part0", "table"),),
        io_signals=(IOSignal("do_grip", "DO", default_value=0),),
    )


@pytest.mark.gui
def test_station_main_window_smoke():
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    app = QApplication.instance() or QApplication([])

    window = StationMainWindow(_fixture_station())
    try:
        window.show()
        # Process a couple of event-loop ticks so layout / paint settle.
        for _ in range(3):
            app.processEvents()

        # Outliner should reflect the fixture station.
        top_count = window.outliner.topLevelItemCount()
        assert top_count == len(window.outliner.GROUPS)

        # Exercise the post-processor previews.
        window.emit_rapid()
        rapid_text = window.code_panel.toPlainText()
        assert rapid_text, "RAPID emit produced empty output"
        window.emit_krl()
        assert window.code_panel.toPlainText(), "KRL emit produced empty output"
        window.emit_urscript()
        assert window.code_panel.toPlainText(), "URScript emit produced empty output"

        for _ in range(3):
            app.processEvents()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = ARTIFACTS_DIR / f"station_smoke_{ts}.png"
        # The default artifact name expected by the spec — keep it stable.
        stable = ARTIFACTS_DIR / "station_smoke.png"
        pixmap = window.grab()
        assert not pixmap.isNull(), "QWidget.grab returned a null pixmap"
        assert pixmap.save(str(out)), f"failed to save {out}"
        assert pixmap.save(str(stable)), f"failed to save {stable}"
        assert stable.stat().st_size > 1024, "smoke artifact looks empty"
        print(f"\nSmoke artifact: {stable} ({pixmap.width()}x{pixmap.height()})")
    finally:
        window.close()
