"""PySide6 main window for the RobotStudio-style station shell.

This module owns the top-level :class:`StationMainWindow`, which wires up:

* a menu bar for File / Robot / Run / Help operations,
* a central :class:`QSplitter` hosting the Outliner on the left and the
  CodePanel + Viewport stacked on the right,
* a status bar showing the current station file path.

The Robot menu builds itself from :func:`src.robots.catalog.list_names`,
so adding a new URDF to the catalog automatically surfaces a *Spawn …*
entry. The Run menu's *Emit RAPID / KRL / URScript* items call the
existing post-processors against a small fixed demo program; they are
deliberately placeholders in this Phase-1 slice.

The 3D viewport is not embedded — see :mod:`src.ui.viewport` for the
reasoning and the *Robot → Launch sim* action below for how the
PyBullet window is launched as a side-by-side subprocess instead.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.motion.ir import (
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    Program,
    SpeedData,
    ToolData,
    WObjData,
    ZoneData,
)
from src.post import KRLPost, RAPIDPost, URScriptPost
from src.robots.catalog import list_names
from src.station import scene as scene_io
from src.station.scene import Frame, RobotEntry, Station
from src.ui.code_panel import CodePanel
from src.ui.outliner import StationOutliner
from src.ui.viewport import StationViewport

WINDOW_TITLE = "POC-RobotArm Station"
DEFAULT_STATION_NAME = "untitled_station"


def _empty_station(name: str = DEFAULT_STATION_NAME) -> Station:
    """Build a minimal station containing only a world frame."""
    return Station(
        name=name,
        frames=(Frame("world", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent=None),),
    )


def _demo_program() -> Program:
    """Tiny IR program used by the Run menu to exercise the post-processors."""
    tool = ToolData(
        name="tool0",
        mass_kg=0.5,
        tcp_xyz_m=(0.0, 0.0, 0.12),
        tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    wobj = WObjData(
        name="wobj0",
        base_xyz_m=(0.5, 0.0, 0.0),
        base_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    home = JointTarget((0.0,) * 6)
    quat_down = (0.0, 0.0, 1.0, 0.0)
    above = PoseTarget((0.40, 0.10, 0.30), quat_down)
    pick = PoseTarget((0.40, 0.10, 0.10), quat_down)
    v200 = SpeedData(200.0)
    v50 = SpeedData(50.0)
    z10 = ZoneData(ZoneData.RADIUS, 10.0)
    fine = ZoneData.fine()
    return Program(
        name="StationDemo",
        modules_metadata={"author": "POC-RobotArm Station UI"},
        tools=[tool],
        wobjs=[wobj],
        procedures=[
            Procedure(
                "main",
                [],
                [
                    Move(MoveKind.MOVE_ABS_J, home, v200, fine, tool, wobj),
                    Move(MoveKind.MOVE_J, above, v200, z10, tool, wobj),
                    Move(MoveKind.MOVE_L, pick, v50, fine, tool, wobj),
                    Move(MoveKind.MOVE_L, above, v50, z10, tool, wobj),
                    Move(MoveKind.MOVE_ABS_J, home, v200, fine, tool, wobj),
                ],
            ),
        ],
    )


class StationMainWindow(QMainWindow):
    """Top-level window for the station shell.

    The window owns a :class:`Station` instance (``self.station``) and a
    Qt widget tree built around a horizontal :class:`QSplitter`.
    Operations (new / open / save / import / spawn) all go through
    public methods so they're callable from tests as well as the menu.
    """

    def __init__(
        self,
        station: Optional[Station] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)

        self.station: Station = station if station is not None else _empty_station()
        self._station_path: Optional[str] = None

        # ----- central widget: splitter Outliner | (CodePanel / Viewport)
        self.outliner = StationOutliner(self)
        self.code_panel = CodePanel(self)
        self.viewport = StationViewport(self)

        right_host = QWidget(self)
        right_layout = QVBoxLayout(right_host)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_splitter = QSplitter(Qt.Vertical, right_host)
        right_splitter.addWidget(self.code_panel)
        right_splitter.addWidget(self.viewport)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 3)
        right_layout.addWidget(right_splitter)

        main_splitter = QSplitter(Qt.Horizontal, self)
        main_splitter.addWidget(self.outliner)
        main_splitter.addWidget(right_host)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)
        self.setCentralWidget(main_splitter)

        # ----- status bar
        self.setStatusBar(QStatusBar(self))
        self._refresh_status_bar()

        # ----- menu bar
        self._build_menus()
        self._refresh_outliner()
        self.resize(1200, 720)

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        # File menu --------------------------------------------------------
        file_menu = menubar.addMenu("&File")

        act_new = QAction("&New Station", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(self.new_station)
        file_menu.addAction(act_new)

        act_open = QAction("&Open Station...", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.open_station)
        file_menu.addAction(act_open)

        act_save = QAction("&Save Station", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self.save_station)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save &As...", self)
        act_save_as.setShortcut("Ctrl+Shift+S")
        act_save_as.triggered.connect(self.save_station_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_import = QAction("&Import CAD...", self)
        act_import.triggered.connect(self.import_cad)
        file_menu.addAction(act_import)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # Robot menu -------------------------------------------------------
        robot_menu = menubar.addMenu("&Robot")
        for catalog_name in list_names():
            action = QAction(f"Spawn {catalog_name}", self)
            action.triggered.connect(
                lambda _checked=False, n=catalog_name: self.spawn_robot(n)
            )
            robot_menu.addAction(action)

        robot_menu.addSeparator()

        act_launch_sim = QAction("Launch sim (PyBullet)", self)
        act_launch_sim.triggered.connect(self.launch_sim)
        robot_menu.addAction(act_launch_sim)

        # Run menu ---------------------------------------------------------
        run_menu = menubar.addMenu("R&un")

        act_rapid = QAction("Emit &RAPID", self)
        act_rapid.triggered.connect(self.emit_rapid)
        run_menu.addAction(act_rapid)

        act_krl = QAction("Emit &KRL", self)
        act_krl.triggered.connect(self.emit_krl)
        run_menu.addAction(act_krl)

        act_urscript = QAction("Emit &URScript", self)
        act_urscript.triggered.connect(self.emit_urscript)
        run_menu.addAction(act_urscript)

        # Help menu --------------------------------------------------------
        help_menu = menubar.addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self.show_about)
        help_menu.addAction(act_about)

    # ------------------------------------------------------------------
    # Public API: station management
    # ------------------------------------------------------------------

    def set_station(self, station: Station, path: Optional[str] = None) -> None:
        """Replace the currently displayed station."""
        self.station = station
        self._station_path = path
        self._refresh_outliner()
        self._refresh_status_bar()

    def new_station(self) -> None:
        """Reset the window to an empty station."""
        self.set_station(_empty_station(), path=None)

    def open_station(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Station", "", "Station JSON (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            station = scene_io.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "Open Station failed", f"Could not load {path}:\n{exc}"
            )
            return
        self.set_station(station, path=path)

    def save_station(self) -> None:
        """Save to the current path, falling back to *Save As* if unset."""
        if self._station_path is None:
            self.save_station_as()
            return
        try:
            scene_io.dump(self.station, self._station_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "Save Station failed",
                f"Could not save {self._station_path}:\n{exc}",
            )
            return
        self._refresh_status_bar()

    def save_station_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Station As", "", "Station JSON (*.json);;All files (*)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path = f"{path}.json"
        self._station_path = path
        self.save_station()

    def import_cad(self) -> None:
        """Pick a mesh / DXF file and surface its summary in the code panel."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import CAD",
            "",
            "Mesh / DXF (*.stl *.obj *.ply *.dxf);;All files (*)",
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            from src.station.cad_import import load_dxf, load_mesh

            if ext == ".dxf":
                polylines = load_dxf(path)
                summary = (
                    f"# Imported DXF: {path}\n"
                    f"# polylines: {len(polylines)}\n"
                    f"# total vertices: {sum(len(pl) for pl in polylines)}\n"
                )
            elif ext in (".stl", ".obj", ".ply"):
                mesh = load_mesh(path)
                summary = (
                    f"# Imported mesh: {path}\n"
                    f"# vertices: {len(mesh.vertices)}\n"
                    f"# faces: {len(mesh.faces)}\n"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Unsupported file",
                    f"Cannot import {path}: unsupported extension {ext!r}.",
                )
                return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "Import CAD failed", f"Could not import {path}:\n{exc}"
            )
            return
        self.code_panel.set_source(summary)

    # ------------------------------------------------------------------
    # Public API: robot / sim
    # ------------------------------------------------------------------

    def spawn_robot(self, catalog_name: str) -> None:
        """Add a :class:`RobotEntry` to the station for ``catalog_name``."""
        # Reuse / create a parent frame for this robot.
        frame_name = f"{catalog_name}_base"
        frames = list(self.station.frames)
        if not any(f.name == frame_name for f in frames):
            frames.append(
                Frame(frame_name, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent="world")
                if any(f.name == "world" for f in frames)
                else Frame(frame_name, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent=None)
            )

        # Pick a unique RobotEntry name.
        existing_names = {r.name for r in self.station.robots}
        base_name = catalog_name
        candidate = base_name
        idx = 1
        while candidate in existing_names:
            idx += 1
            candidate = f"{base_name}_{idx}"

        robots = list(self.station.robots) + [
            RobotEntry(
                name=candidate,
                robot_catalog_name=catalog_name,
                base_frame=frame_name,
            )
        ]
        new_station = Station(
            name=self.station.name,
            frames=tuple(frames),
            robots=tuple(robots),
            tools=self.station.tools,
            workpieces=self.station.workpieces,
            fixtures=self.station.fixtures,
            io_signals=self.station.io_signals,
        )
        self.set_station(new_station, path=self._station_path)

    def launch_sim(self) -> None:
        """Subprocess-spawn the existing PyBullet GUI for the first robot."""
        if not self.station.robots:
            self.viewport.set_status(
                "No robot in the station. Use Robot → Spawn ... first."
            )
            return
        first = self.station.robots[0]
        try:
            subprocess.Popen(
                [sys.executable, "-m", "src.simulation.gui",
                 "--robot", first.robot_catalog_name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.viewport.set_status(
                f"Launched PyBullet sim for {first.robot_catalog_name} "
                f"in a separate window."
            )
        except Exception as exc:  # noqa: BLE001
            self.viewport.set_status(f"Failed to launch sim: {exc}")

    # ------------------------------------------------------------------
    # Public API: post-processors
    # ------------------------------------------------------------------

    def emit_rapid(self) -> None:
        self.code_panel.set_source(RAPIDPost().emit(_demo_program()))

    def emit_krl(self) -> None:
        self.code_panel.set_source(KRLPost().emit(_demo_program()))

    def emit_urscript(self) -> None:
        self.code_panel.set_source(URScriptPost().emit(_demo_program()))

    # ------------------------------------------------------------------
    # Public API: misc
    # ------------------------------------------------------------------

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "About POC-RobotArm Station",
            (
                "POC-RobotArm Station — Phase 1 desktop shell.\n\n"
                "Edit a flat scene-graph (frames / robots / tools / workpieces / "
                "fixtures / IO), save and load it as JSON, import CAD meshes, "
                "and emit RAPID / KRL / URScript previews of a fixed demo program."
            ),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _refresh_outliner(self) -> None:
        self.outliner.populate(self.station)

    def _refresh_status_bar(self) -> None:
        path_text = self._station_path or "(unsaved)"
        bar = self.statusBar()
        if bar is not None:
            bar.showMessage(f"Station: {self.station.name}    File: {path_text}")


def _build_demo_station() -> Station:
    """Sample station preloaded by ``examples/demo_station_gui.py``."""
    return Station(
        name="demo_station",
        frames=(
            Frame("world", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent=None),
            Frame("robot_base", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent="world"),
            Frame("table", (0.5, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent="world"),
        ),
        robots=(
            RobotEntry("arm0", "abb_irb1200", "robot_base"),
        ),
    )


def _ensure_qapp():
    """Get-or-create the singleton :class:`QApplication`."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def main() -> int:  # pragma: no cover (manual entry point)
    app = _ensure_qapp()
    window = StationMainWindow(_build_demo_station())
    window.show()
    return app.exec()


__all__ = [
    "DEFAULT_STATION_NAME",
    "StationMainWindow",
    "WINDOW_TITLE",
    "_build_demo_station",
    "main",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
