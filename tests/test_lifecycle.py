"""Lifecycle tests: REPL stdin polling exits cleanly on stop_event/EOF.

These tests don't open a real GUI; they exercise the ``_repl`` and
``_read_line_with_stop`` functions directly with piped stdin so we can
assert the REPL terminates within ~1 second when the simulator signals
shutdown — preventing the "GUI window closed but the prompt is still
hanging" failure mode flagged in the UAT plan.
"""

from __future__ import annotations

import io
import sys
import threading
import time

import pytest


@pytest.fixture
def fake_stdin(monkeypatch):
    """Replace sys.stdin with a pipe-backed file we can write to from a test."""
    import os

    r_fd, w_fd = os.pipe()
    reader = os.fdopen(r_fd, "r", buffering=1)
    writer = os.fdopen(w_fd, "w", buffering=1)
    monkeypatch.setattr(sys, "stdin", reader)
    yield writer
    try:
        writer.close()
    except Exception:
        pass
    try:
        reader.close()
    except Exception:
        pass


def test_read_line_returns_none_when_stop_event_set(fake_stdin):
    from src.main import _read_line_with_stop

    stop = threading.Event()
    result_holder: dict = {}

    def reader():
        result_holder["value"] = _read_line_with_stop(stop, prompt="")

    t = threading.Thread(target=reader)
    t.start()
    time.sleep(0.1)
    stop.set()
    t.join(timeout=2.0)

    assert not t.is_alive(), "reader did not exit after stop_event was set"
    assert result_holder["value"] is None


def test_read_line_returns_input_when_typed(fake_stdin):
    from src.main import _read_line_with_stop

    stop = threading.Event()
    result_holder: dict = {}

    def reader():
        result_holder["value"] = _read_line_with_stop(stop, prompt="")

    t = threading.Thread(target=reader)
    t.start()
    time.sleep(0.05)
    fake_stdin.write("hello\n")
    fake_stdin.flush()
    t.join(timeout=2.0)

    assert not t.is_alive()
    assert result_holder["value"] == "hello"


def test_repl_quits_on_stop_event(fake_stdin):
    """Simulating GUI window close: stop_event is set; REPL should exit."""
    from src.main import _repl

    class _DummyAgent:
        ollama_client = None

        def process(self, _):
            return "ok"

    stop = threading.Event()
    t = threading.Thread(target=_repl, args=(_DummyAgent(), stop))
    t.start()
    time.sleep(0.1)
    stop.set()
    t.join(timeout=2.0)

    assert not t.is_alive(), "REPL did not exit within 2 s of stop_event"


def test_repl_quits_on_quit_command(fake_stdin):
    from src.main import _repl

    class _DummyAgent:
        ollama_client = None

        def process(self, _):
            return "ok"

    stop = threading.Event()
    t = threading.Thread(target=_repl, args=(_DummyAgent(), stop))
    t.start()
    time.sleep(0.05)
    fake_stdin.write("quit\n")
    fake_stdin.flush()
    t.join(timeout=2.0)

    assert not t.is_alive()
    assert stop.is_set()
