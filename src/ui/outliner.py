"""Qt tree widget showing the contents of a :class:`Station`.

This module is meant to be imported from inside :mod:`src.ui.app` only.
PySide6 is imported at module scope here because anything pulling
``src.ui.outliner`` already depends on Qt; the rest of the codebase
(headless tests, station scene-graph) never imports this module.
"""

from __future__ import annotations

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from src.station.scene import Station


class StationOutliner(QTreeWidget):
    """Tree view of a :class:`Station`'s entities.

    The widget exposes a single :meth:`populate` entry-point that rebuilds
    the tree from the given station, plus :meth:`clear_station` to drop
    all rows. Group headers (Frames / Robots / Tools / Workpieces /
    Fixtures / IO) are always present, even when the corresponding
    collection is empty, so the user always sees the same structure.
    """

    GROUPS: tuple[str, ...] = (
        "Frames",
        "Robots",
        "Tools",
        "Workpieces",
        "Fixtures",
        "IO",
    )

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderLabels(["Name", "Detail"])
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear_station(self) -> None:
        """Remove every row in the tree."""
        self.clear()

    def populate(self, station: Station) -> None:
        """Rebuild the tree from ``station``."""
        self.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for label in self.GROUPS:
            top = QTreeWidgetItem([label, ""])
            self.addTopLevelItem(top)
            groups[label] = top

        for fr in station.frames:
            parent = fr.parent if fr.parent is not None else "<world>"
            xyz = ", ".join(f"{v:.3f}" for v in fr.xyz_m)
            QTreeWidgetItem(groups["Frames"], [fr.name, f"parent={parent}  xyz=({xyz})"])

        for r in station.robots:
            QTreeWidgetItem(
                groups["Robots"],
                [r.name, f"catalog={r.robot_catalog_name}  base={r.base_frame}"],
            )

        for t in station.tools:
            mesh = t.mesh_path or "(none)"
            QTreeWidgetItem(
                groups["Tools"],
                [t.name, f"parent={t.parent_frame}  mesh={mesh}"],
            )

        for w in station.workpieces:
            mesh = w.mesh_path or "(none)"
            QTreeWidgetItem(
                groups["Workpieces"],
                [w.name, f"parent={w.parent_frame}  mesh={mesh}"],
            )

        for fx in station.fixtures:
            mesh = fx.mesh_path or "(none)"
            QTreeWidgetItem(
                groups["Fixtures"],
                [fx.name, f"parent={fx.parent_frame}  mesh={mesh}"],
            )

        for sig in station.io_signals:
            QTreeWidgetItem(
                groups["IO"],
                [sig.name, f"{sig.kind}  default={sig.default_value}"],
            )

        for top in groups.values():
            top.setExpanded(True)


__all__ = ["StationOutliner"]
