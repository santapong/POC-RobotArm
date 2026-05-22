"""Tests for program executor with IO steps (server/routers/programs.py).

Verifies _execute_io_step, _execute_step_sequence, cancellation, step-order
preservation (iter-2 Fix 6), and IO_NOT_INITIALIZED fast-fail (iter-2 Fix 4).

Stub IoRuntime subclasses avoid real adapters while preserving the actual
runtime code paths.

Skipped if fastapi or httpx are not installed.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, Callable, Iterator

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from server.main import create_app  # noqa: E402
from src.io.errors import IoTimeout, IoUnknownSignal  # noqa: E402
from src.io.types import ConnectionStatusKind, IoEvent, SignalKind, SignalSpec  # noqa: E402
from src.motion.ir import (  # noqa: E402
    Comment,
    IfSignal,
    JointTarget,
    Move,
    MoveKind,
    Procedure,
    Program,
    SetSignal,
    SignalOp,
    SpeedData,
    ToolData,
    WaitSignal,
    WObjData,
    ZoneData,
    ZoneKind,
)

pytestmark = pytest.mark.io


class _SignalState:
    """Holds the current value of a signal, shared between the stub runtime and tests."""

    def __init__(self, initial: bool | int | float = False) -> None:
        self.value: bool | int | float = initial


class _StubConnectionSlot:
    """Minimal slot descriptor used by _StubIoRuntime."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.status = ConnectionStatusKind.OPEN
        self.config = object()
        self.adapter = object()
        self.signals: dict[str, SignalSpec] = {}
        self.watch_task = None
        self.write_lock = asyncio.Lock()
        self.last_error = None
        self.connected_at = time.monotonic()


class _StubIoRuntime:
    """Stub I/O runtime that records calls and uses in-memory signal state.

    Tests can inject signal values via ``set_signal_value(connection, signal, value)``
    and inspect calls via the ``calls`` list.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []  # (operation, connection, signal)
        self._values: dict[str, _SignalState] = {}
        self._slots: dict[str, _StubConnectionSlot] = {}

    def add_slot(self, connection: str, signal: str, kind: SignalKind = SignalKind.DIGITAL_OUT) -> None:
        if connection not in self._slots:
            self._slots[connection] = _StubConnectionSlot(connection)
        spec = SignalSpec(name=signal, kind=kind, address="coil:0")
        self._slots[connection].signals[signal] = spec
        key = f"{connection}.{signal}"
        self._values.setdefault(key, _SignalState())

    def set_signal_value(self, connection: str, signal: str, value: bool | int | float) -> None:
        key = f"{connection}.{signal}"
        if key not in self._values:
            self._values[key] = _SignalState()
        self._values[key].value = value

    def get_signal_value(self, connection: str, signal: str) -> bool | int | float:
        return self._values[f"{connection}.{signal}"].value

    # ---- IoRuntime public API ----

    def list_connections(self):
        return list(self._slots.values())

    def get_connection(self, name: str) -> _StubConnectionSlot:
        if name not in self._slots:
            raise KeyError(name)
        return self._slots[name]

    async def write(self, connection: str, signal: str, value: bool | int | float) -> IoEvent:
        self.calls.append(("write", connection, signal, value))
        # Mimic real IoRuntime behaviour: raise KeyError for unknown connections.
        if connection not in self._slots:
            raise KeyError(connection)
        key = f"{connection}.{signal}"
        if key not in self._values:
            self._values[key] = _SignalState()
        self._values[key].value = value
        return IoEvent(
            connection=connection,
            kind="write_ack",
            signal=signal,
            value=value,
            monotonic_s=time.monotonic(),
        )

    async def read(self, connection: str, signal: str) -> IoEvent:
        self.calls.append(("read", connection, signal, None))
        key = f"{connection}.{signal}"
        state = self._values.get(key)
        if state is None:
            raise IoUnknownSignal(f"Signal {signal!r} not found in {connection!r}")
        return IoEvent(
            connection=connection,
            kind="value_changed",
            signal=signal,
            value=state.value,
            monotonic_s=time.monotonic(),
        )

    async def wait_for_signal(
        self,
        connection: str,
        signal: str,
        predicate: Callable[[bool | int | float], bool],
        timeout_s: float | None = None,
    ) -> IoEvent:
        self.calls.append(("wait", connection, signal, timeout_s))
        key = f"{connection}.{signal}"
        state = self._values.get(key)
        if state is None:
            raise IoUnknownSignal(f"Signal {signal!r} not found")

        async def _poll():
            while True:
                if predicate(state.value):
                    return IoEvent(
                        connection=connection,
                        kind="value_changed",
                        signal=signal,
                        value=state.value,
                        monotonic_s=time.monotonic(),
                    )
                await asyncio.sleep(0.05)

        try:
            if timeout_s is not None:
                return await asyncio.wait_for(_poll(), timeout=timeout_s)
            return await _poll()
        except asyncio.TimeoutError as exc:
            raise IoTimeout(
                f"wait_for_signal({connection!r}, {signal!r}) timed out after {timeout_s} s"
            ) from exc

    def subscribe(self, q: asyncio.Queue) -> None:
        pass

    def unsubscribe(self, q: asyncio.Queue) -> None:
        pass

    async def stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers — program builder helpers
# ---------------------------------------------------------------------------

def _tool():
    return ToolData(
        name="tool0",
        mass_kg=1.0,
        tcp_xyz_m=(0.0, 0.0, 0.1),
        tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )


def _wobj():
    return WObjData(
        name="wobj0",
        base_xyz_m=(0.0, 0.0, 0.0),
        base_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
    )


def _speed():
    return SpeedData(v_tcp_mm_s=100.0)


def _zone_fine():
    return ZoneData(ZoneKind.FINE, 0.0)


def _abs_j(q=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)):
    return Move(
        kind=MoveKind.MOVE_ABS_J,
        target=JointTarget(q_rad=q),
        speed=_speed(),
        zone=_zone_fine(),
        tool=_tool(),
        wobj=_wobj(),
    )


def _make_program(name: str, *steps) -> Program:
    return Program(
        name=name,
        procedures=(Procedure(name="main", body=tuple(steps)),),
    )


# ---------------------------------------------------------------------------
# Fixture: TestClient with a spawned robot
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _app_with_robot() -> Iterator[TestClient]:
    """Create the app, spawn a robot, yield the client."""
    app = create_app()
    with TestClient(app) as c:
        c.post("/api/station/new")
        r = c.post("/api/station/robots", json={"catalog_name": "abb_irb1200"})
        assert r.status_code == 200, f"Spawn failed: {r.text}"
        time.sleep(0.3)  # let sim tick settle
        yield c


def _wait_for_run(c: TestClient, run_id: str, timeout_s: float = 20.0) -> dict:
    """Poll GET /api/programs/runs/{run_id} until terminal."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = c.get(f"/api/programs/runs/{run_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.2)
    raise TimeoutError(f"Run {run_id} did not reach terminal in {timeout_s}s")


@contextlib.contextmanager
def _inject_io_runtime(c: TestClient, stub_runtime: _StubIoRuntime) -> Iterator[None]:
    """Inject the stub IoRuntime into the active session."""
    from server.services.session import get_session
    session = get_session()
    original = session.io_runtime
    session.io_runtime = stub_runtime
    try:
        yield
    finally:
        session.io_runtime = original


# ---------------------------------------------------------------------------
# Helper: register a program in the session's program registry
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _register_program(program: Program) -> Iterator[None]:
    """Add a program to the server's in-memory program registry, remove on exit."""
    from server.services import programs as progs_service
    progs_service._PROGRAMS[program.name] = program
    try:
        yield
    finally:
        progs_service._PROGRAMS.pop(program.name, None)


# ---------------------------------------------------------------------------
# Tests — SetSignal
# ---------------------------------------------------------------------------


def test_set_signal_writes_value():
    """A program with one SetSignal must call runtime.write with the correct args,
    and the run record must reach status=completed."""
    stub = _StubIoRuntime()
    stub.add_slot("mb_floor", "do0", SignalKind.DIGITAL_OUT)

    prog = _make_program("set_signal_prog",
        SetSignal(connection="mb_floor", signal="do0", value=True),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/set_signal_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]
                record = _wait_for_run(c, run_id)

    assert record["status"] == "completed", f"Expected completed, got: {record}"
    write_calls = [(op, conn, sig, val) for op, conn, sig, val in stub.calls if op == "write"]
    assert len(write_calls) >= 1, f"Expected write call, got calls: {stub.calls}"
    last_write = write_calls[-1]
    assert last_write[1] == "mb_floor"
    assert last_write[2] == "do0"
    assert last_write[3] is True


# ---------------------------------------------------------------------------
# Tests — WaitSignal
# ---------------------------------------------------------------------------


def test_wait_signal_succeeds_when_value_matches():
    """WaitSignal completes immediately when the stub already has the target value."""
    stub = _StubIoRuntime()
    stub.add_slot("mb_floor", "di0", SignalKind.DIGITAL_IN)
    stub.set_signal_value("mb_floor", "di0", True)  # pre-set to True

    prog = _make_program("wait_ok_prog",
        WaitSignal(connection="mb_floor", signal="di0", op=SignalOp.EQ, value=True, timeout_s=2.0),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/wait_ok_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]
                record = _wait_for_run(c, run_id, timeout_s=10.0)

    assert record["status"] == "completed", f"Expected completed, got: {record}"


def test_wait_signal_times_out():
    """WaitSignal(timeout_s=0.5) raises IoTimeout → run fails with IO_TIMEOUT error.
    Covers §J risk #15.
    """
    stub = _StubIoRuntime()
    stub.add_slot("mb_floor", "di0", SignalKind.DIGITAL_IN)
    stub.set_signal_value("mb_floor", "di0", False)  # never becomes True

    prog = _make_program("wait_timeout_prog",
        WaitSignal(connection="mb_floor", signal="di0", op=SignalOp.EQ, value=True, timeout_s=0.3),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/wait_timeout_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]
                record = _wait_for_run(c, run_id, timeout_s=10.0)

    assert record["status"] == "failed", f"Expected failed (timeout), got: {record}"
    assert "IO_TIMEOUT" in (record.get("error") or ""), (
        f"Expected IO_TIMEOUT in error, got: {record.get('error')!r}"
    )


# ---------------------------------------------------------------------------
# Tests — IfSignal branching
# ---------------------------------------------------------------------------


def test_if_signal_then_branch():
    """When predicate is True, then_body executes and else_body does not."""
    stub = _StubIoRuntime()
    stub.add_slot("opc_arm", "part_present", SignalKind.DIGITAL_IN)
    stub.set_signal_value("opc_arm", "part_present", True)

    prog = _make_program("if_then_prog",
        IfSignal(
            connection="opc_arm", signal="part_present",
            op=SignalOp.EQ, value=True,
            then_body=(SetSignal(connection="opc_arm", signal="part_present", value=False),),
            else_body=(Comment("no part — this must NOT execute"),),
        ),
    )
    # Inject do_set signal for the SetSignal in then_body
    stub.add_slot("opc_arm", "part_present", SignalKind.DIGITAL_IN)

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/if_then_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]
                record = _wait_for_run(c, run_id, timeout_s=10.0)

    assert record["status"] == "completed", f"Expected completed, got: {record}"
    # then_body: write was called on part_present
    write_calls = [c for c in stub.calls if c[0] == "write"]
    assert len(write_calls) >= 1, "then_body SetSignal must have triggered a write"


def test_if_signal_else_branch():
    """When predicate is False, else_body executes and then_body does not."""
    stub = _StubIoRuntime()
    stub.add_slot("opc_arm", "part_present", SignalKind.DIGITAL_IN)
    stub.set_signal_value("opc_arm", "part_present", False)  # predicate is False

    # Use a distinct signal name for else_body so we can distinguish the calls.
    stub.add_slot("mb_floor", "alarm", SignalKind.DIGITAL_OUT)

    prog = _make_program("if_else_prog",
        IfSignal(
            connection="opc_arm", signal="part_present",
            op=SignalOp.EQ, value=True,
            then_body=(Comment("part present — must NOT execute"),),
            else_body=(SetSignal(connection="mb_floor", signal="alarm", value=True),),
        ),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/if_else_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]
                record = _wait_for_run(c, run_id, timeout_s=10.0)

    assert record["status"] == "completed", f"Expected completed, got: {record}"
    write_calls = [(conn, sig) for op, conn, sig, val in stub.calls if op == "write"]
    # else_body must have written to mb_floor.alarm
    assert ("mb_floor", "alarm") in write_calls, (
        f"else_body must write to mb_floor.alarm; writes: {write_calls}"
    )


def test_if_signal_nested():
    """IfSignal inside IfSignal.then_body: when both predicates true, innermost branch runs."""
    stub = _StubIoRuntime()
    stub.add_slot("c1", "s1", SignalKind.DIGITAL_IN)
    stub.add_slot("c2", "s2", SignalKind.DIGITAL_IN)
    stub.add_slot("mb", "inner_do", SignalKind.DIGITAL_OUT)
    stub.set_signal_value("c1", "s1", True)
    stub.set_signal_value("c2", "s2", True)

    inner_if = IfSignal(
        connection="c2", signal="s2", op=SignalOp.EQ, value=True,
        then_body=(SetSignal(connection="mb", signal="inner_do", value=True),),
    )
    prog = _make_program("nested_if_prog",
        IfSignal(
            connection="c1", signal="s1", op=SignalOp.EQ, value=True,
            then_body=(inner_if,),
        ),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/nested_if_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]
                record = _wait_for_run(c, run_id, timeout_s=10.0)

    assert record["status"] == "completed", f"Expected completed, got: {record}"
    write_calls = [(conn, sig) for op, conn, sig, val in stub.calls if op == "write"]
    assert ("mb", "inner_do") in write_calls, (
        f"Innermost branch must write to mb.inner_do; writes: {write_calls}"
    )


# ---------------------------------------------------------------------------
# Tests — IO_NOT_INITIALIZED fast-fail
# Covers iter-2 Fix 4 and §J risk #15
# ---------------------------------------------------------------------------


def test_planning_failed_marks_io_not_initialized():
    """A program with IO steps but session.io_runtime is None must fail fast
    with IO_NOT_INITIALIZED, not partway through after some moves.
    Covers iter-2 Fix 4.
    """
    prog = _make_program("io_no_runtime_prog",
        SetSignal(connection="mb", signal="do0", value=True),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            # io_runtime is None (no _inject_io_runtime context)
            from server.services.session import get_session
            session = get_session()
            # Confirm io_runtime is not set
            session.io_runtime = None

            r = c.post("/api/programs/io_no_runtime_prog/run", json={"planner": "linear"})
            assert r.status_code == 200
            run_id = r.json()["run_id"]
            record = _wait_for_run(c, run_id, timeout_s=10.0)

    assert record["status"] == "failed", f"Expected failed, got: {record}"
    assert "IO_NOT_INITIALIZED" in (record.get("error") or ""), (
        f"Expected IO_NOT_INITIALIZED in error, got: {record.get('error')!r}"
    )


# ---------------------------------------------------------------------------
# Tests — cancellation
# Covers iter-2 Fix 5 and §J risk #15
# ---------------------------------------------------------------------------


def test_stop_run_cancels_wait_signal():
    """Start a program with WaitSignal(timeout_s=None); stop_run cancels it within 5s.
    The run record must reach status=failed with cancellation indication.
    Covers iter-2 Fix 5.
    """
    stub = _StubIoRuntime()
    stub.add_slot("mb_floor", "di_never", SignalKind.DIGITAL_IN)
    stub.set_signal_value("mb_floor", "di_never", False)  # never becomes True

    prog = _make_program("cancel_prog",
        WaitSignal(connection="mb_floor", signal="di_never", op=SignalOp.EQ, value=True, timeout_s=None),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/cancel_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]

                # Wait until run is in-flight (status=running)
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    rec = c.get(f"/api/programs/runs/{run_id}").json()
                    if rec["status"] == "running":
                        break
                    time.sleep(0.05)

                # Issue stop
                r_stop = c.post(f"/api/programs/runs/{run_id}/stop")
                assert r_stop.status_code == 200

                record = _wait_for_run(c, run_id, timeout_s=5.0)

    assert record["status"] == "failed", f"Expected failed after stop, got: {record}"


# ---------------------------------------------------------------------------
# Tests — motion-only program — backwards compatibility
# Covers §J risk #19
# ---------------------------------------------------------------------------


def test_motion_only_program_byte_identical():
    """A program with only Moves + Comments runs through the linear path unchanged.
    No IO branching is engaged; the run must complete normally.
    Covers §J risk #19 (backwards compatibility).
    """
    prog = _make_program("motion_only_compat",
        _abs_j(),
        Comment("midpoint"),
        _abs_j(q=(0.1, 0.0, 0.0, 0.0, 0.0, 0.0)),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            # No io_runtime needed — motion-only programs must not touch it.
            from server.services.session import get_session
            session = get_session()
            assert session.io_runtime is None  # confirm no runtime injected

            r = c.post("/api/programs/motion_only_compat/run", json={"planner": "linear"})
            assert r.status_code == 200
            run_id = r.json()["run_id"]
            record = _wait_for_run(c, run_id, timeout_s=20.0)

    assert record["status"] == "completed", (
        f"Motion-only program must complete, got: {record['status']}: {record.get('error')}"
    )


# ---------------------------------------------------------------------------
# Tests — step order preserved
# Covers iter-2 Fix 6
# ---------------------------------------------------------------------------


def test_step_order_preserved():
    """Body = [SetSignal X, SetSignal Y]: writes must happen in order X → Y.
    Covers iter-2 Fix 6 (step order inside mixed programs).
    """
    stub = _StubIoRuntime()
    stub.add_slot("mb", "do0", SignalKind.DIGITAL_OUT)
    stub.add_slot("mb", "do1", SignalKind.DIGITAL_OUT)

    prog = _make_program("order_prog",
        SetSignal(connection="mb", signal="do0", value=True),
        SetSignal(connection="mb", signal="do1", value=True),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/order_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]
                record = _wait_for_run(c, run_id, timeout_s=10.0)

    assert record["status"] == "completed"
    write_ops = [(sig) for op, conn, sig, val in stub.calls if op == "write"]
    # do0 must be written before do1
    assert write_ops.index("do0") < write_ops.index("do1"), (
        f"Expected do0 before do1, got order: {write_ops}"
    )


def test_step_order_inside_if_signal_body():
    """IfSignal.then_body = [SetSignal X, SetSignal Y]: writes happen in order.
    Covers iter-2 Fix 6 inside branch bodies.
    """
    stub = _StubIoRuntime()
    stub.add_slot("c", "flag", SignalKind.DIGITAL_IN)
    stub.add_slot("mb", "do0", SignalKind.DIGITAL_OUT)
    stub.add_slot("mb", "do1", SignalKind.DIGITAL_OUT)
    stub.set_signal_value("c", "flag", True)

    prog = _make_program("if_order_prog",
        IfSignal(
            connection="c", signal="flag", op=SignalOp.EQ, value=True,
            then_body=(
                SetSignal(connection="mb", signal="do0", value=True),
                SetSignal(connection="mb", signal="do1", value=True),
            ),
        ),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/if_order_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]
                record = _wait_for_run(c, run_id, timeout_s=10.0)

    assert record["status"] == "completed"
    write_ops = [sig for op, conn, sig, val in stub.calls if op == "write"]
    assert write_ops.index("do0") < write_ops.index("do1"), (
        f"Expected do0 before do1 in then_body, got: {write_ops}"
    )


# ---------------------------------------------------------------------------
# Extra coverage: unknown connection raises IO error in run
# Extra coverage: §J risk #8 (signal-map drift)
# ---------------------------------------------------------------------------

# Extra coverage: writing to an unknown connection → run fails with IO_CONNECTION_UNKNOWN.
def test_unknown_connection_yields_io_error_in_run():
    """SetSignal for a connection not in the runtime fails the run."""
    stub = _StubIoRuntime()
    # Deliberately NOT adding the connection that the program references.

    prog = _make_program("unknown_conn_prog",
        SetSignal(connection="not_registered", signal="do0", value=True),
    )

    with _app_with_robot() as c:
        with _register_program(prog):
            with _inject_io_runtime(c, stub):
                r = c.post("/api/programs/unknown_conn_prog/run", json={"planner": "linear"})
                assert r.status_code == 200
                run_id = r.json()["run_id"]
                record = _wait_for_run(c, run_id, timeout_s=10.0)

    assert record["status"] == "failed"
    assert record.get("error") is not None
