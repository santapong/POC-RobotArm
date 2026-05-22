"""Tests for FakeCamera: determinism, shape, and empty-list behaviour."""

from __future__ import annotations

import numpy as np
import pytest

from src.vision.capture import FakeCamera


class TestFakeCameraEmptyPaths:
    """Empty image_paths => generated solid-colour test pattern."""

    def test_produces_frame(self) -> None:
        cam = FakeCamera("test", image_paths=[], width=320, height=240)
        frame = cam.read()
        assert frame is not None

    def test_frame_shape(self) -> None:
        cam = FakeCamera("test", image_paths=[], width=320, height=240)
        frame = cam.read()
        assert frame.shape == (240, 320, 3)

    def test_frame_dtype(self) -> None:
        cam = FakeCamera("test", image_paths=[], width=320, height=240)
        assert cam.read().dtype == np.uint8

    def test_deterministic_single_read(self) -> None:
        """Same test pattern is returned on every read."""
        cam = FakeCamera("test", image_paths=[], width=64, height=64)
        f1 = cam.read()
        f2 = cam.read()
        np.testing.assert_array_equal(f1, f2)

    def test_is_open_before_close(self) -> None:
        cam = FakeCamera("test", image_paths=[])
        assert cam.is_open()

    def test_is_open_after_close(self) -> None:
        cam = FakeCamera("test", image_paths=[])
        cam.close()
        assert not cam.is_open()

    def test_read_after_close_raises(self) -> None:
        cam = FakeCamera("test", image_paths=[])
        cam.close()
        with pytest.raises(RuntimeError, match="closed"):
            cam.read()


class TestFakeCameraSinglePath:
    """Single path => same frame on every call (deterministic)."""

    def test_single_path_determinism(self, tmp_path) -> None:
        cv2 = pytest.importorskip("cv2")
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[100:200, 100:200] = [0, 0, 255]  # red square
        p = str(tmp_path / "frame.png")
        cv2.imwrite(p, img)

        cam = FakeCamera("test", image_paths=[p], width=640, height=480)
        f1 = cam.read()
        f2 = cam.read()
        f3 = cam.read()
        np.testing.assert_array_equal(f1, f2)
        np.testing.assert_array_equal(f2, f3)

    def test_single_path_shape(self, tmp_path) -> None:
        cv2 = pytest.importorskip("cv2")
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        p = str(tmp_path / "frame.png")
        cv2.imwrite(p, img)

        cam = FakeCamera("test", image_paths=[p], width=320, height=240)
        frame = cam.read()
        assert frame.shape == (240, 320, 3)


class TestFakeCameraMultiPath:
    """Multi-path: loop=True cycles, loop=False raises StopIteration."""

    def _make_png(self, tmp_path, name: str, colour: tuple[int, int, int]) -> str:
        cv2 = pytest.importorskip("cv2")
        img = np.full((64, 64, 3), colour, dtype=np.uint8)
        p = str(tmp_path / name)
        cv2.imwrite(p, img)
        return p

    def test_loop_true_cycles(self, tmp_path) -> None:
        p1 = self._make_png(tmp_path, "a.png", (255, 0, 0))
        p2 = self._make_png(tmp_path, "b.png", (0, 255, 0))
        cam = FakeCamera("test", image_paths=[p1, p2], loop=True)
        f1 = cam.read()
        f2 = cam.read()
        f3 = cam.read()  # wraps back to p1
        np.testing.assert_array_equal(f1, f3)
        with pytest.raises(AssertionError):
            np.testing.assert_array_equal(f1, f2)

    def test_loop_false_exhausts(self, tmp_path) -> None:
        p1 = self._make_png(tmp_path, "a.png", (128, 0, 0))
        p2 = self._make_png(tmp_path, "b.png", (0, 128, 0))
        cam = FakeCamera("test", image_paths=[p1, p2], loop=False)
        cam.read()
        cam.read()
        with pytest.raises(StopIteration):
            cam.read()

    def test_context_manager(self, tmp_path) -> None:
        p = self._make_png(tmp_path, "a.png", (50, 50, 50))
        with FakeCamera("test", image_paths=[p]) as cam:
            cam.read()
        assert not cam.is_open()

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            FakeCamera("test", image_paths=["/no/such/file.png"])
