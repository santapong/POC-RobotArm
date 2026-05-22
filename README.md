# POC-RobotArm

Hybrid monorepo for a virtual robot station, with motion / sim / vision / planning extensions and a web-based 3D operator UI.

## Architecture at a glance

The project is organised as three siblings that share a single Python process at runtime.

```
src/      Python library (motion IR, sim, drivers, post-processors)
server/   FastAPI app exposing the library to the web UI
web/      React + Vite + R3F frontend (replacing the legacy PySide6 desktop)
```

## Phased roadmap

- **Phase 0 — Foundation** (this commit): Python 3.12 floor, FastAPI skeleton (`GET /health`, `WebSocket /ws/telemetry` stub), Vite + React + R3F scaffold with placeholder canvas, Makefile targets `make server` / `make web`, README rewrite.
- **Phase 1 — Web parity**: FastAPI session state, WebSocket telemetry, REST endpoints; React 3D viewport with URDF loader, outliner, code-preview, and jog panel. (planned)
- **Phase 2 — Vision pipeline**: `src/vision/` with OpenCV capture, YOLOv11 detection, hand-eye calibration; MJPEG stream endpoint; web camera panel. (planned)
- **Phase 3 — Advanced planning**: `src/planning/` with OMPL / pyroboplan, Ruckig, ToppRA; plan service in FastAPI; web plan-preview panel. (planned)
- **Phase 4 — I/O signals** ✅: `src/io/` with Modbus TCP/RTU, OPC-UA, MQTT adapters behind a common `IoAdapter` ABC; FastAPI REST + WebSocket stream; React I/O tab with signal map editor; IR step types `SetSignal` / `WaitSignal` / `IfSignal` integrated with the program executor.
- **Phase 5 — SO-101 driver + LeRobot + Docker**: SO-101 FeetechMotorsBus driver, MuJoCo backend for RL, web jog/teleop panel, first Docker image. (planned)
- **Phase 6 — RL research track**: `src/learning/` with Stable-Baselines3 baseline and LeRobot ACT/Diffusion Policy; HF dataset adapter; inference endpoint. (planned)

Full plan: `.claude/plans/can-you-create-an-sparkling-garden.md`.

## Run the app

### Server

```bash
pip install -e .[server,dev]
make server     # FastAPI on http://127.0.0.1:8000
curl http://127.0.0.1:8000/health   # -> {"status":"ok"}
```

### Web

Requires Node 20 and pnpm 10.

```bash
cd web
pnpm install
make web        # Vite on http://localhost:5173
```

## Python install matrix

```bash
python -m venv .venv && source .venv/bin/activate

# Minimum (motion IR + post-processors are stdlib-only)
pip install -e .[dev]

# Add the simulator + FK/IK kinematics
pip install -e .[sim,rtb,dev]

# Add the CAM pipeline (trimesh + ezdxf)
pip install -e .[sim,rtb,cam,dev]

# Add the desktop UI (PySide6)
pip install -e .[sim,rtb,cam,ui,dev]

# Everything (incl. Ollama, Pillow)
pip install -e .[all,dev]
```

Tested on Ubuntu 22.04 with Python 3.12. Other Linux distros should work; macOS / Windows are not part of the UAT scope (see `docs/UAT_CHECKLIST.md`).

## Core Python Library

### What you can do

- Run a 3D PyBullet simulator for **Panda**, **UR5**, **KUKA IIWA**, or **ABB IRB 1200**, controlled by sliders or by the LLM
- Solve forward / inverse kinematics from Python or the CLI
- Talk to the arm in natural language (real Ollama or the bundled deterministic fake)
- Build a virtual **station** with frames, tools, workpieces, fixtures, IO; import CAD (STL/OBJ/DXF); save/load to JSON
- Generate **CAM-style toolpaths** from CAD (raster, polyline-follow, curve-on-surface) with redundancy-DP joint optimization and PyBullet collision checks
- Build a vendor-neutral motion program and **export ABB RAPID, KUKA KRL, or Universal Robots URScript**
- Compute **time-parameterised trajectories** from any program (trapezoidal velocity profile, IK-seeded continuity, MOVE_J / MOVE_L / MOVE_C) with per-sample joint-velocity, TCP-velocity, and singularity checks
- Replay interpolated trajectories through the PyBullet bridge via **`SimSampledPathDriver`**, a drop-in proxy for the standard sim driver
- Drive a real **ABB controller online via RWS** (HTTPS digest auth, IRC5 / OmniCore — no extra deps)
- **Record** any sequence of moves and **replay** them through the same `Driver` Protocol that talks to the sim or to a real robot
- Launch the **PySide6 desktop UI** (`robotarm-station`) to manage stations, preview emitted code, and spawn the PyBullet viewport
- Run the full UAT acceptance harness: `make uat`

### Install

See the [Python install matrix](#python-install-matrix) above.

### Quickstart

```bash
make sim                                 # interactive simulator (Panda)
python -m src.simulation --robot ur5     # UR5 instead
python -m src.simulation --robot iiwa    # KUKA IIWA

make uat                                 # automated UAT harness (10 stories)
make test                                # 31 headless tests
RUN_GUI_TESTS=1 pytest tests/test_gui_smoke.py     # opens GUI, saves PNG
```

### Talk to the arm

```bash
python -m src.main --sim                 # real Ollama + 3D simulator
python -m src.main --sim --fake-llm      # deterministic fake LLM (no network)
python -m src.main --sim --no-llm        # direct text commands only
```

Direct commands available in `--no-llm` mode:

```
list                          List FK/IK robots
info <robot>                  Robot details
fk <robot> <angles...>        Forward kinematics
ik <robot> <x> <y> <z>        Inverse kinematics
plot <robot> <angles...>      Matplotlib visualization
sim state                     Live simulator state
sim move <x> <y> <z>          IK move + place a target marker
sim joint <idx> <deg>         Drive a single joint
sim reset                     Return to the catalog home pose
```

### Architecture

```
src/
├── robots/                   # Robot catalog + DH builders
│   ├── catalog.py            # rtb-free URDF specs (panda, ur5, iiwa, abb_irb1200)
│   ├── predefined.py         # rtb robot models (lazy import); includes hand-built KUKA iiwa 14 DHRobot
│   ├── custom.py             # DH-parameter robot factory
│   └── limits.py             # Per-robot velocity/acceleration JointLimits dataclass (Panda, UR5, IIWA, IRB1200)
├── kinematics/               # FK/IK solvers (rtb)
├── visualization/            # matplotlib plots
├── simulation/               # PyBullet desktop simulator
│   ├── engine.py             # RobotArmSim wrapper
│   ├── bridge.py             # Thread-safe Queue+Future bridge
│   ├── gui.py                # PyBullet GUI loop with debug sliders
│   └── __main__.py
├── llm/                      # Ollama agent + tools
│   ├── agent.py
│   ├── tools.py              # FK/IK + sim_* tools the LLM can call
│   ├── ollama_client.py
│   └── fake_client.py        # Deterministic stand-in (UAT, CI)
├── motion/                   # Vendor-neutral motion IR + record/playback + path interpolation
│   ├── ir.py                 # Move, Tool, WObj, Speed, Zone, Program (+JSON I/O)
│   ├── recorder.py           # Capture jog actions into IR steps
│   ├── player.py             # Replay an IR Program through any Driver
│   ├── frames.py             # TCP/RTCP pose composition + scene-graph frame walk (resolve_pose_to_base, forward_resolve, derive_frame_mode, resolve_frame_to_root)
│   ├── limits.py             # Limit validation + structured errors (validate_move, LimitViolation, LimitsExceeded, assert_no_violations)
│   ├── manipulability.py     # Yoshikawa manipulability index + singularity guard (yoshikawa, is_singular)
│   └── path.py               # Time-parameterised trajectory interpolator (Sample, SampledPath, interpolate_program, interpolate_move, _trapezoidal_profile, _arc_fit_3pt, _slerp_quat, _slerp_via)
├── drivers/                  # Vendor-neutral robot interface
│   ├── base.py               # Driver Protocol + RobotState
│   ├── sim/sim_driver.py     # SimBridge adapter
│   ├── sim/sim_sampled_path.py  # Limits-aware sim driver proxy (SimSampledPathDriver)
│   └── abb/rws_client.py     # ABB Robot Web Services online driver (stdlib HTTPS+digest)
├── post/                     # Vendor program emission
│   ├── base.py               # Post Protocol
│   ├── abb_rapid.py          # ABB RAPID .mod
│   ├── kuka_krl.py           # KUKA KRL .src + .dat
│   └── ur_script.py          # Universal Robots URScript .script
├── toolpath/                 # CAM (Robotmaster-style)
│   ├── intake.py             # STL/OBJ via trimesh; DXF via ezdxf
│   ├── operations.py         # polyline_follow, curve_on_surface, surface_raster
│   └── optimizer.py          # DP trellis for redundancy resolution
├── collision/
│   └── checker.py            # PyBullet DIRECT-client collision queries
├── station/                  # Virtual station scene graph
│   ├── scene.py              # Frame/Tool/Workpiece/Fixture/IO + JSON I/O
│   └── cad_import.py         # trimesh + ezdxf wrappers
└── ui/                       # PySide6 desktop UI (deprecated — kept until web parity, then removed)
    ├── app.py                # StationMainWindow (File/Robot/Run menus)
    ├── outliner.py           # QTreeWidget showing scene contents
    ├── code_panel.py         # Emitted-code preview
    └── viewport.py           # Stub; spawns the PyBullet GUI alongside

assets/urdf/{ur5, abb_irb1200}/        # Hand-written URDFs (primitive shapes)
examples/                              # End-to-end demos (pure Python, runnable)
  demo_export_rapid.py                 # ABB IRB 1200 pick-and-place -> .mod
  demo_record_playback.py              # Record moves, save to JSON, replay
  demo_toolpath_stl.py                 # STL -> raster -> joint-optimal -> RAPID
  demo_station_save_load.py            # Build a station, dump/load JSON
  demo_station_gui.py                  # Launch the PySide6 desktop UI
  demo_path_calculation.py            # Build a MOVE_L program, interpolate, replay via SimSampledPathDriver
docs/                                  # UAT checklist, report template
scripts/uat_run.py                     # Automated UAT harness
.github/workflows/ci.yml               # Headless tests + lint + rtb-extras job
```

### Export ABB RAPID, KUKA KRL, or UR Script

```bash
python examples/demo_export_rapid.py        # ABB IRB 1200 pick-and-place .mod
```

The emitters live under `src/post/`. They share one Protocol and read the same
vendor-neutral `Program`. Unit conversions (metres → mm, radians → degrees,
quaternion → RAPID `wxyz` / KRL ZYX-Euler / URScript rotation-vector) happen
at the boundary; predefined RAPID/KRL names like `fine`/`z10`/`v100` are
reused when IR values match exactly, custom `speeddata`/`zonedata` declared
otherwise. When `SpeedData.a_tcp_mm_s2` or `a_ori_deg_s2` is set, the emitters
inject vendor acceleration instructions: RAPID emits `AccSet acc%, 100;` before
the move; KRL emits `$ACC.CP` (m/s²) and `$ACC.ORI1` (deg/s²); URScript passes
`a=<m/s²>` (linear moves) or `a=<rad/s²>` (joint moves) directly on the motion
call.

### Generate a toolpath from CAD

```bash
python examples/demo_toolpath_stl.py        # STL -> raster -> joint-optimal -> RAPID
```

`src/toolpath/operations.py` produces `list[PoseTarget]` from CAD geometry;
`optimizer.py` runs forward DP over per-waypoint IK candidates with cost
`||Δq|| + λ/manipulability`, filtering by joint limits and Yoshikawa
manipulability. `src/collision/checker.py` runs a headless PyBullet client
to reject colliding configurations.

### Time-parameterised path interpolation

`interpolate_program` converts any `Program` into a `SampledPath` — a timestamped sequence of joint positions and TCP poses, checked against the robot's velocity and acceleration limits at every sample.

```python
from src.motion.path import interpolate_program, SampledPath
from src.motion.limits import LimitsExceeded

try:
    path: SampledPath = interpolate_program(prog, robot, dt_s=0.02)
except LimitsExceeded as exc:
    for v in exc.violations:
        print(v.error_code, v.joint_index, v.requested, v.allowed)
```

The same call handles MOVE_J (joint-space ramp), MOVE_L (Cartesian linear with time-synchronised linear/angular axes), and MOVE_C (circular arc fit through the via-point with piecewise SLERP orientation). `ToolData.robhold` selects the composition direction: `robhold=True` is standard TCP mode; `robhold=False` activates RTCP mode where the workobject is robot-held and the tool is world-fixed.

`LimitsExceeded` carries a `.violations` list; each entry has `error_code` (`JOINT_VELOCITY`, `JOINT_ACCEL`, `TCP_VELOCITY`, `TCP_ANGULAR_VELOCITY`, `SINGULARITY`, or `JOINT_POSITION`), `joint_index`, `requested`, and `allowed`.

To replay through the simulator without touching higher-level driver code, wrap the existing sim driver:

```python
from src.drivers.sim.sim_sampled_path import SimSampledPathDriver

driver = SimSampledPathDriver(inner_sim_driver, robot, dt_s=0.02)
path = driver.play_program(prog)   # returns the SampledPath after replay
```

Run the full demo:

```bash
python examples/demo_path_calculation.py
```

### Drive a real ABB controller (online RWS)

```python
from src.drivers.abb import RWSDriver
from src.post import RAPIDPost
from examples.demo_export_rapid import build_hello_program

driver = RWSDriver(host="192.168.0.10", username="Default User", password="robotics")
driver.connect()
driver.run_program(RAPIDPost().emit(build_hello_program()), name="Hello")
driver.disconnect()
```

`RWSDriver` speaks RWS 1.0 (IRC5 / RobotWare 5–6) and 2.0 (OmniCore /
RobotWare 7) via stdlib only — no `requests` dependency. Real-time
streaming (EGM, 250 Hz) is left for a future phase.

### Record and replay

```python
from src.motion.recorder import Recorder
from src.motion.player import Player
from src.motion.ir import dump, load

rec = Recorder(default_tool=tool0, default_wobj=wobj0)
rec.record_move_joint(home_q)
rec.record_move_linear(xyz, quat)
dump(rec.as_program("hello"), "hello.json")

prog = load("hello.json")
Player(driver).play_program(prog)
```

The same `Driver` Protocol fronts the PyBullet sim and the real ABB
controller, so the replay code is identical for both.

### Launch the desktop UI

```bash
robotarm-station                           # PySide6 main window
# or
python examples/demo_station_gui.py        # same, with a sample station preloaded
```

### How the LLM drives the simulator

PyBullet is thread-bound to the thread that called `p.connect`, so the GUI loop owns it. The LLM REPL runs on a worker thread; its `sim_*` tool calls go through `SimBridge` — a `queue.Queue[Command]` drained on every GUI tick. Results flow back via `concurrent.futures.Future`. A read-only state snapshot is updated each tick so `sim_get_state` never blocks.

Errors come back as JSON with a code and message:
- `IK_UNREACHABLE` — IK couldn't reach the target within tolerance
- `JOINT_LIMIT_CLAMPED` — requested angle was clamped
- `SIM_DISCONNECTED` — simulator not running
- `SIM_TIMEOUT` — GUI loop didn't drain in time
- `INVALID_ARG` — bad joint index or wrong DOF count

### UAT readiness

This branch is the UAT-readiness sprint. Status:

- ✅ M1 — Robot/URDF coherence (Panda + UR5 + IIWA all load)
- ✅ M2 — Lifecycle hardening (clean exit on window close)
- ✅ M3 — Fake LLM client + integration tests
- ✅ M4 — GUI smoke test + checklist
- ✅ M5 — pyproject.toml + Makefile + GitHub Actions CI
- ✅ M6 — `scripts/uat_run.py` + report template + Ollama manual
- ✅ M7 — README + INSTALL
- 🔄 M8 — Path interpolation foundations: limits data model (`JointLimits`), TCP/RTCP frame composition, Yoshikawa manipulability extraction (PRs #4, #5 — not yet merged to main)
- 🔄 M9 — Path interpolator + `SimSampledPathDriver` + post-processor acceleration emission (PRs #4, #5 — not yet merged to main)

See `docs/UAT_CHECKLIST.md` for the tester checklist and `docs/UAT_REPORT_TEMPLATE.md` for the signoff form.

## Industrial I/O (Phase 4)

The `src/io/` package connects programs running in the executor to physical hardware over four protocols: Modbus TCP, Modbus RTU, OPC-UA, and MQTT. All four share a single async `IoAdapter` ABC, so the rest of the server treats them identically. See [`docs/IO.md`](docs/IO.md) for the full reference.

### Install the `[io]` extra

```bash
pip install -e .[io,dev]
```

This pulls `pymodbus`, `asyncua`, and `aiomqtt`. The core library (`src/io/types.py`, `src/io/adapter.py`) is stdlib-only and always importable; only the concrete adapters require the extra.

### Supported protocols

| Protocol | Library | Default port | Signal kinds |
|----------|---------|--------------|--------------|
| Modbus TCP | `pymodbus` | 502 | digital, analog (holding registers) |
| Modbus RTU | `pymodbus` | serial device | digital, analog (holding registers) |
| OPC-UA | `asyncua` | 4840 | digital, analog (monitored items) |
| MQTT | `aiomqtt` | 1883 | digital, analog (topic publish/subscribe) |

Quick config samples:

```python
from src.io.types import ModbusTcpConfig, OpcUaConfig, MqttConfig

ModbusTcpConfig(host="192.168.1.10", port=502, unit_id=1)
OpcUaConfig(url="opc.tcp://plc.local:4840/", namespace=2)
MqttConfig(host="broker.local", port=1883, qos=1)
```

### REST endpoints

All routes are under `/api/io/`. Full request/response shapes are in [`docs/IO.md`](docs/IO.md#rest-endpoints).

- **Connection management** — `POST /connections`, `GET /connections`, `GET /connections/{name}`, `DELETE /connections/{name}`, `POST /connections/{name}/reconnect`, `PUT /connections/{name}/signals`
- **Signal I/O** — `POST /connections/{name}/signals/{signal}/read` (live read), `POST /connections/{name}/signals/{signal}/write`
- **Cached values** — `GET /values` (all connections), `GET /connections/{name}/values`

### WebSocket stream

Connect to `ws://localhost:8000/ws/io/stream` to receive every `IoEvent` in real time. To filter to one connection, send:

```json
{"subscribe": "connection/<name>"}
```

Send `{"subscribe": ""}` to revert to all connections. Each frame carries `type`, `connection`, `signal`, `value`, `status`, and `monotonic_s` fields.

### IR program steps

`SetSignal`, `WaitSignal`, and `IfSignal` extend the program IR (`src/motion/ir.py`) so that motion programs can interact with hardware signals without leaving the executor:

```python
from src.motion.ir import (
    SetSignal, WaitSignal, IfSignal, SignalOp,
    Procedure, Program,
)

Program(
    name="pick",
    procedures=(
        Procedure(name="main", body=(
            # Block until the start button is pressed (10 s timeout).
            WaitSignal(connection="plc", signal="start_btn", op=SignalOp.EQ,
                       value=True, timeout_s=10.0),
            # Branch: pick if a part is present, skip otherwise.
            IfSignal(connection="plc", signal="part_present", op=SignalOp.EQ,
                     value=True,
                     then_body=(move_pick, move_drop),
                     else_body=()),
            # Acknowledge completion.
            SetSignal(connection="plc", signal="done_lamp", value=True),
        )),
    ),
)
```

The executor calls `IoRuntime.write` for `SetSignal`, `IoRuntime.wait_for_signal` for `WaitSignal`, and `IoRuntime.read` + branch dispatch for `IfSignal`. If `io_runtime` is `None` when an I/O step is reached, the run fails immediately with `IO_NOT_INITIALIZED`.

### Run the demo

The Phase 4 exit gate (`tests/test_io_e2e_demo.py::test_io_e2e_full_scenario`) starts in-process Modbus TCP and OPC-UA simulators plus a real `mosquitto` broker, registers three connections, runs an I/O-bearing program, and asserts the WebSocket stream carries `connection_changed` and `write_ack` frames.

```bash
# Prerequisites: pip install -e .[io,dev] && which mosquitto
IO_E2E=1 pytest tests/test_io_e2e_demo.py -v
```

The test is opt-in and is not run by `make test` or `make uat` by default.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: roboticstoolbox` | rtb extra not installed | `pip install -e .[rtb]` |
| `pybullet.error: Cannot connect to GUI` | Headless box, no display | Run `python -m src.simulation` on a desktop |
| GUI opens, REPL hangs after window close | Old build (pre-M2) | Rebuild from current commit |
| `IK_UNREACHABLE` for an obviously-reachable point | URDF override pointing at a model whose EE link doesn't match catalog | Use `--robot <name>` instead of `--urdf` |
| LLM ignores tool calls | Model lacks tool-calling support | Use `llama3.1` or another tool-capable model |
| `LimitsExceeded` raised on `sim_move` or `play_program` | Speed or acceleration on the requested move exceeds catalog limits for that robot | Inspect `exc.violations` to see which joint or axis tripped; reduce `SpeedData` fields or choose a robot with higher limits |
| `Unknown robot 'iiwa'` (older clones) | The `iiwa` hand-built DHRobot was not wired into the rtb factory before PR-B | Pull the latest branch — `get_robot("iiwa")` ships with the path-calculation work. |

## License

See `assets/LICENSES.md` for asset provenance. Code is provided as-is for proof-of-concept use.
