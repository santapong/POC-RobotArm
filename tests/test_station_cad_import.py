"""Tests for the CAD importers (src.station.cad_import).

The imports of :mod:`trimesh` and :mod:`ezdxf` are deferred inside the
production module, so the tests below ``importorskip`` them — boxes
without those CAD libraries simply skip these tests instead of failing.
"""

from __future__ import annotations

import os

import pytest


def test_load_mesh_rejects_unknown_extension(tmp_path):
    from src.station.cad_import import load_mesh

    bad = tmp_path / "thing.iges"
    bad.write_text("not a real iges")
    with pytest.raises(ValueError, match="Unsupported mesh extension"):
        load_mesh(str(bad))


def test_load_mesh_missing_file_raises(tmp_path):
    from src.station.cad_import import load_mesh

    with pytest.raises(FileNotFoundError):
        load_mesh(str(tmp_path / "no_such.stl"))


def test_load_mesh_reads_generated_stl(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    from src.station.cad_import import load_mesh

    box = trimesh.creation.box(extents=(0.1, 0.2, 0.05))
    out = tmp_path / "box.stl"
    box.export(str(out))

    mesh = load_mesh(str(out))
    assert isinstance(mesh, trimesh.Trimesh)
    # A box has 8 unique vertices and 12 triangular faces; STL writes them
    # face-by-face so vertex count post-load is 8 (after merge) or 36 (raw).
    assert len(mesh.faces) == 12
    assert mesh.is_watertight  # generated box is closed


def test_load_mesh_reads_generated_obj(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    from src.station.cad_import import load_mesh

    box = trimesh.creation.box(extents=(0.1, 0.1, 0.1))
    out = tmp_path / "box.obj"
    box.export(str(out))

    mesh = load_mesh(str(out))
    assert isinstance(mesh, trimesh.Trimesh)
    assert len(mesh.faces) == 12


def test_load_dxf_returns_polylines(tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    from src.station.cad_import import load_dxf

    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()
    # A LWPOLYLINE square in millimetres (default DXF unit).
    msp.add_lwpolyline(
        [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)],
        close=True,
    )
    # A second open polyline.
    msp.add_lwpolyline([(0.0, 0.0), (10.0, 10.0), (20.0, 5.0)], close=False)
    # A simple LINE.
    msp.add_line((0.0, 0.0), (1000.0, 0.0))

    out = tmp_path / "shapes.dxf"
    doc.saveas(str(out))

    polylines = load_dxf(str(out))
    assert len(polylines) == 3

    # The closed square should have 5 vertices (4 corners + closing point).
    closed = [pl for pl in polylines if len(pl) == 5]
    assert len(closed) == 1
    # Conversion from mm to metres: original (100, 0) becomes (0.1, 0.0).
    assert closed[0][1] == pytest.approx((0.1, 0.0))

    # The plain LINE should have produced a 2-point polyline.
    two_pt = [pl for pl in polylines if len(pl) == 2]
    assert len(two_pt) == 1
    assert two_pt[0][0] == pytest.approx((0.0, 0.0))
    assert two_pt[0][1] == pytest.approx((1.0, 0.0))


def test_load_dxf_missing_file_raises(tmp_path):
    pytest.importorskip("ezdxf")
    from src.station.cad_import import load_dxf

    with pytest.raises(FileNotFoundError):
        load_dxf(os.path.join(str(tmp_path), "no_such.dxf"))
