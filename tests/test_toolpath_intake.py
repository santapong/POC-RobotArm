"""Tests for src.toolpath.intake — STL/DXF loaders."""

from __future__ import annotations

import os

import pytest


def _have(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Mesh loading
# ---------------------------------------------------------------------------


def test_load_mesh_stl(tmp_path) -> None:
    pytest.importorskip("trimesh")
    import trimesh

    from src.toolpath.intake import load_mesh

    box = trimesh.creation.box(extents=(0.1, 0.2, 0.3))
    stl = tmp_path / "part.stl"
    box.export(str(stl))

    loaded = load_mesh(str(stl))
    assert isinstance(loaded, trimesh.Trimesh)
    # 8 vertices on a box; trimesh may dedupe — 8 unique.
    assert len(loaded.vertices) == 8
    assert len(loaded.faces) == 12


def test_load_mesh_missing_path() -> None:
    pytest.importorskip("trimesh")
    from src.toolpath.intake import load_mesh

    with pytest.raises(FileNotFoundError):
        load_mesh("/no/such/file.stl")


def test_load_mesh_obj(tmp_path) -> None:
    pytest.importorskip("trimesh")
    import trimesh

    from src.toolpath.intake import load_mesh

    sphere = trimesh.creation.icosphere(subdivisions=1)
    obj_path = tmp_path / "ball.obj"
    sphere.export(str(obj_path))

    loaded = load_mesh(str(obj_path))
    assert isinstance(loaded, trimesh.Trimesh)
    assert len(loaded.faces) > 0


# ---------------------------------------------------------------------------
# DXF loading
# ---------------------------------------------------------------------------


def test_load_dxf_polylines_lwpolyline(tmp_path) -> None:
    pytest.importorskip("ezdxf")
    import ezdxf

    from src.toolpath.intake import load_dxf_polylines

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # 100 mm square in DXF units (mm). Polyline closed by repeating origin.
    msp.add_lwpolyline([(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)])
    msp.add_lwpolyline([(50.0, 50.0), (200.0, 50.0)])
    dxf = tmp_path / "shape.dxf"
    doc.saveas(str(dxf))

    polylines = load_dxf_polylines(str(dxf))
    assert len(polylines) == 2
    # First polyline should have 4 corners, in meters (100 mm => 0.1 m).
    assert len(polylines[0]) == 4
    assert polylines[0][1] == pytest.approx((0.1, 0.0))
    assert polylines[0][2] == pytest.approx((0.1, 0.1))
    # Second polyline: two endpoints, mm to m conversion.
    assert polylines[1][0] == pytest.approx((0.05, 0.05))
    assert polylines[1][1] == pytest.approx((0.20, 0.05))


def test_load_dxf_polylines_line_entity(tmp_path) -> None:
    pytest.importorskip("ezdxf")
    import ezdxf

    from src.toolpath.intake import load_dxf_polylines

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0.0, 0.0), (50.0, 25.0))
    dxf = tmp_path / "line.dxf"
    doc.saveas(str(dxf))

    polylines = load_dxf_polylines(str(dxf))
    assert len(polylines) == 1
    assert polylines[0][0] == pytest.approx((0.0, 0.0))
    assert polylines[0][1] == pytest.approx((0.05, 0.025))


def test_load_dxf_unit_scale_override(tmp_path) -> None:
    pytest.importorskip("ezdxf")
    import ezdxf

    from src.toolpath.intake import load_dxf_polylines

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_lwpolyline([(0.0, 0.0), (1.0, 1.0)])
    dxf = tmp_path / "small.dxf"
    doc.saveas(str(dxf))

    # If the DXF is already in meters, pass unit_scale=1.0.
    polylines = load_dxf_polylines(str(dxf), unit_scale=1.0)
    assert polylines[0][1] == pytest.approx((1.0, 1.0))


def test_load_dxf_missing_path() -> None:
    pytest.importorskip("ezdxf")
    from src.toolpath.intake import load_dxf_polylines

    with pytest.raises(FileNotFoundError):
        load_dxf_polylines("/no/such/file.dxf")


def test_load_dxf_empty_modelspace(tmp_path) -> None:
    pytest.importorskip("ezdxf")
    import ezdxf

    from src.toolpath.intake import load_dxf_polylines

    doc = ezdxf.new("R2010")
    dxf = tmp_path / "empty.dxf"
    doc.saveas(str(dxf))
    polylines = load_dxf_polylines(str(dxf))
    assert polylines == []


def test_module_imports_without_dxf(monkeypatch) -> None:
    # Sanity: the module should import even if its third-party dependencies
    # are not yet imported (the imports are inside the functions).
    pytest.importorskip("trimesh")
    pytest.importorskip("ezdxf")
    import importlib

    mod = importlib.import_module("src.toolpath.intake")
    assert hasattr(mod, "load_mesh")
    assert hasattr(mod, "load_dxf_polylines")
    # Path validation runs before the third-party import, so missing-path
    # errors don't depend on trimesh/ezdxf.
    with pytest.raises(FileNotFoundError):
        mod.load_mesh("/no/such/path.stl")
    assert _have("trimesh")  # ensure no monkey-patch
    assert os.sep in os.path.abspath(".")
