"""Tests for server/services/errors.py — IO_* branches of map_exception.

Exercises every IoError subclass → (http_status, error_code) mapping per §K,
plus the import-guard robustness when src.io.errors is unavailable.

No heavy [io] extra needed — src.io.errors is stdlib-only.
"""

from __future__ import annotations

import sys
import types

import pytest

from server.services.errors import map_exception
from src.io.errors import (
    IoConnectionError,
    IoNotConnected,
    IoProtocolError,
    IoSignalKindMismatch,
    IoTimeout,
    IoUnavailable,
    IoUnknownSignal,
)

pytestmark = pytest.mark.io

# IoConfigError is not in the public __all__ from src.io.errors;
# the master plan §K lists it but looking at the implementation it maps
# IoUnavailable → IO_UNAVAILABLE and the error class named in §K as
# "IoConfigError" is not present in the current src/io/errors.py.
# We test the 7 classes that ARE present: IoUnavailable, IoConnectionError,
# IoNotConnected, IoProtocolError, IoSignalKindMismatch, IoTimeout, IoUnknownSignal.


# ---------------------------------------------------------------------------
# Parametrised round-trip for each IO_* code
# ---------------------------------------------------------------------------

# (exception_class, expected_http_status, expected_error_code)
_IO_CASES = [
    (IoUnavailable,         422, "IO_UNAVAILABLE"),
    (IoConnectionError,     503, "IO_CONNECTION_FAILED"),
    (IoNotConnected,        503, "IO_NOT_CONNECTED"),
    (IoProtocolError,       502, "IO_PROTOCOL_ERROR"),
    (IoSignalKindMismatch,  422, "IO_SIGNAL_KIND_MISMATCH"),
    (IoTimeout,             504, "IO_TIMEOUT"),
    (IoUnknownSignal,       404, "IO_SIGNAL_UNKNOWN"),
]


@pytest.mark.parametrize("exc_cls,expected_status,expected_code", _IO_CASES)
def test_map_exception_io_error(exc_cls, expected_status, expected_code):
    """map_exception(IoXxx('msg')) → (expected_status, ErrorResponse(code=expected_code))."""
    exc = exc_cls("test message")
    status, response = map_exception(exc)
    assert status == expected_status, (
        f"{exc_cls.__name__}: expected HTTP {expected_status}, got {status}"
    )
    assert response.code == expected_code, (
        f"{exc_cls.__name__}: expected code {expected_code!r}, got {response.code!r}"
    )


def test_map_exception_io_unavailable_hint():
    """IoUnavailable response must include a [io] install hint."""
    _, response = map_exception(IoUnavailable("missing lib"))
    assert response.hint is not None
    # The hint must mention the [io] extra
    assert "io" in (response.hint or "").lower()


def test_map_exception_io_error_detail_propagated():
    """The exception message must appear in the detail field."""
    exc = IoTimeout("Timed out after 5 s")
    _, response = map_exception(exc)
    assert "Timed out after 5 s" in response.detail


# ---------------------------------------------------------------------------
# Unknown signal — checks IoUnknownSignal maps to 404 IO_SIGNAL_UNKNOWN
# ---------------------------------------------------------------------------

def test_map_exception_unknown_signal_is_404():
    """IoUnknownSignal is the iter-2 safety net; must map to 404 IO_SIGNAL_UNKNOWN."""
    exc = IoUnknownSignal("Signal 'foo' not found")
    status, response = map_exception(exc)
    assert status == 404
    assert response.code == "IO_SIGNAL_UNKNOWN"


# ---------------------------------------------------------------------------
# Fallthrough behaviour — non-IO exceptions still resolve correctly
# ---------------------------------------------------------------------------

def test_map_exception_non_io_value_error():
    """A plain ValueError must not crash the mapper; returns 422 VALIDATION_ERROR."""
    status, response = map_exception(ValueError("bad input"))
    assert status == 422
    assert response.code == "VALIDATION_ERROR"


def test_map_exception_non_io_runtime_error():
    """A plain RuntimeError not matching 'not initialized' → 500 INTERNAL_ERROR."""
    status, response = map_exception(RuntimeError("something unexpected"))
    assert status == 500
    assert response.code == "INTERNAL_ERROR"


def test_map_exception_non_io_key_error():
    """A plain KeyError → 404 ROBOT_UNKNOWN (pre-IO fallback branch)."""
    status, response = map_exception(KeyError("abb_irb1200"))
    assert status == 404
    assert response.code == "ROBOT_UNKNOWN"


# ---------------------------------------------------------------------------
# Import-guard robustness — simulate the [io] extra missing
# ---------------------------------------------------------------------------

def test_map_exception_survives_io_errors_import_failure(monkeypatch):
    """When src.io.errors cannot be imported, map_exception must not crash.

    We simulate the ImportError by temporarily removing the module from
    sys.modules and poisoning the import so the lazy-import block sets all
    IO_* classes to None.  A subsequent call with any non-IO exception must
    still return a valid (status, response) pair.
    """
    # Remove src.io.errors from the module cache so the lazy import inside
    # map_exception re-executes.
    original_module = sys.modules.get("src.io.errors")
    # Inject a broken importer
    broken = types.ModuleType("src.io.errors")
    # Overwrite the module with one that has no IoError subclasses — simulating
    # ImportError by removing the names that map_exception imports lazily.
    monkeypatch.setitem(sys.modules, "src.io.errors", broken)
    try:
        # With the broken module, a generic ValueError should still resolve.
        status, response = map_exception(ValueError("fallback check"))
        assert status == 422
        assert response.code == "VALIDATION_ERROR"
    finally:
        # Restore the real module
        if original_module is not None:
            sys.modules["src.io.errors"] = original_module
        else:
            sys.modules.pop("src.io.errors", None)


# ---------------------------------------------------------------------------
# Extra coverage: each IoError subclass has a usable __str__
# Extra coverage: IoError hierarchy
# ---------------------------------------------------------------------------

# Extra coverage: all IoError subclasses inherit from RuntimeError via IoError.
def test_io_errors_are_runtime_errors():
    """All IoError subclasses inherit from RuntimeError (per §B design note)."""
    for cls in (IoUnavailable, IoConnectionError, IoNotConnected,
                IoProtocolError, IoSignalKindMismatch, IoTimeout, IoUnknownSignal):
        exc = cls("test")
        assert isinstance(exc, RuntimeError), f"{cls.__name__} must be a RuntimeError"


# Extra coverage: str(exc) returns the message.
def test_io_error_str_returns_message():
    """str(exc) must return the message, not an unhelpful repr."""
    for cls in (IoUnavailable, IoConnectionError, IoNotConnected,
                IoProtocolError, IoSignalKindMismatch, IoTimeout, IoUnknownSignal):
        msg = f"test message for {cls.__name__}"
        exc = cls(msg)
        assert msg in str(exc), f"{cls.__name__}.__str__() did not include the message"


# Extra coverage: map_exception is idempotent — calling it twice with the same exc
# returns the same (status, code) pair.
def test_map_exception_idempotent():
    exc = IoTimeout("timeout")
    r1 = map_exception(exc)
    r2 = map_exception(exc)
    assert r1[0] == r2[0]
    assert r1[1].code == r2[1].code
