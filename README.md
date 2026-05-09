# POC-RobotArm

A virtual robot station + CAM toolpath planner + multi-vendor program export, built around PyBullet and a vendor-neutral motion IR. Think of it as a small open-source slice of RobotStudio + Robotmaster, all running as a desktop program (no website).

## What you can do

- Run a 3D PyBullet simulator for **Panda**, **UR5**, **KUKA IIWA**, or **ABB IRB 1200**, controlled by sliders or by the LLM
- Solve forward / inverse kinematics from Python or the CLI
- Talk to the arm in natural language (real Ollama or the bundled deterministic fake)
- Build a virtual **station** with frames, tools, workpieces, fixtures, IO; import CAD (STL/OBJ/DXF); save/load to JSON
- Generate **CAM-style toolpaths** from CAD (raster, polyline-follow, curve-on-surface) with redundancy-DP joint optimization and PyBullet collision checks
- Build a vendor-neutral motion program and **export ABB RAPID, KUKA KRL, or Universal Robots URScript**
- Drive a real **ABB controller online via RWS** (HTTPS digest auth, IRC5 / OmniCore — no extra deps)
- **Record** any sequence of moves and **replay** them through the same `Driver` Protocol that talks to the sim or to a real robot
- Launch the **PySide6 desktop UI** (`robotarm-station`) to manage stations, preview emitted code, and spawn the PyBullet viewport
- Run the full UAT acceptance harness: `make uat`

## Install

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

Tested on Ubuntu 22.04 with Python 3.10 / 3.11. Other Linux distros should work; macOS / Windows are not part of the UAT scope (see `docs/UAT_CHECKLIST.md`).

## Quickstart

```bash
make sim                                 # interactive simulator (Panda)
python -m src.simulation --robot ur5     # UR5 instead
python -m src.simulation --robot iiwa    # KUKA IIWA

make uat                                 # automated UAT harness (10 stories)
make test                                # 31 headless tests
RUN_GUI_TESTS=1 pytest tests/test_gui_smoke.py     # opens GUI, saves PNG
```

## Talk to the arm

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

## Architecture

```
src/
├── robots/                   # Robot catalog + DH builders
│   ├── catalog.py            # rtb-free URDF specs (panda, ur5, iiwa, abb_irb1200)
│   ├── predefined.py         # rtb robot models (lazy import)
│   └── custom.py             # DH-parameter robot factory
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
├── motion/                   # Vendor-neutral motion IR + record/playback
│   ├── ir.py                 # Move, Tool, WObj, Speed, Zone, Program (+JSON I/O)
│   ├── recorder.py           # Capture jog actions into IR steps
│   └── player.py             # Replay an IR Program through any Driver
├── drivers/                  # Vendor-neutral robot interface
│   ├── base.py               # Driver Protocol + RobotState
│   ├── sim/sim_driver.py     # SimBridge adapter
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
└── ui/                       # PySide6 desktop UI
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
otherwise.

### Generate a toolpath from CAD

```bash
python examples/demo_toolpath_stl.py        # STL -> raster -> joint-optimal -> RAPID
```

`src/toolpath/operations.py` produces `list[PoseTarget]` from CAD geometry;
`optimizer.py` runs forward DP over per-waypoint IK candidates with cost
`||Δq|| + λ/manipulability`, filtering by joint limits and Yoshikawa
manipulability. `src/collision/checker.py` runs a headless PyBullet client
to reject colliding configurations.

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

## UAT readiness

This branch is the UAT-readiness sprint. Status:

- ✅ M1 — Robot/URDF coherence (Panda + UR5 + IIWA all load)
- ✅ M2 — Lifecycle hardening (clean exit on window close)
- ✅ M3 — Fake LLM client + integration tests
- ✅ M4 — GUI smoke test + checklist
- ✅ M5 — pyproject.toml + Makefile + GitHub Actions CI
- ✅ M6 — `scripts/uat_run.py` + report template + Ollama manual
- ✅ M7 — README + INSTALL

See `docs/UAT_CHECKLIST.md` for the tester checklist and `docs/UAT_REPORT_TEMPLATE.md` for the signoff form.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: roboticstoolbox` | rtb extra not installed | `pip install -e .[rtb]` |
| `pybullet.error: Cannot connect to GUI` | Headless box, no display | Run `python -m src.simulation` on a desktop |
| GUI opens, REPL hangs after window close | Old build (pre-M2) | Rebuild from current commit |
| `IK_UNREACHABLE` for an obviously-reachable point | URDF override pointing at a model whose EE link doesn't match catalog | Use `--robot <name>` instead of `--urdf` |
| LLM ignores tool calls | Model lacks tool-calling support | Use `llama3.1` or another tool-capable model |

## License

See `assets/LICENSES.md` for asset provenance. Code is provided as-is for proof-of-concept use.
