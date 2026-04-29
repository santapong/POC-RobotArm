# POC-RobotArm

Robotics kinematics solver + 3D simulator + optional natural-language interface, all running as a desktop program (no website).

## What you can do

- Run a 3D PyBullet simulator for **Panda**, **UR5**, or **KUKA IIWA**, controlled by sliders or by the LLM
- Solve forward / inverse kinematics from Python or the CLI
- Talk to the arm in natural language (real Ollama or the bundled deterministic fake)
- Run the full UAT acceptance harness: `make uat`

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .[sim,dev]                # minimum — simulator + tests
pip install -e .[sim,rtb,dev]            # add the FK/IK kinematics stack
pip install -e .[all,dev]                # everything (incl. Ollama, Pillow)
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
├── robots/
│   ├── catalog.py        # rtb-free URDF catalog (panda, ur5, iiwa)
│   ├── predefined.py     # rtb robot models (lazy import)
│   └── custom.py
├── kinematics/           # FK/IK solvers (rtb)
├── visualization/        # matplotlib plots
├── simulation/
│   ├── engine.py         # PyBullet wrapper (RobotArmSim)
│   ├── bridge.py         # Thread-safe Queue+Future bridge for the LLM
│   ├── gui.py            # PyBullet GUI loop with debug sliders
│   └── __main__.py
└── llm/
    ├── agent.py          # RobotArmAgent — accepts injected client
    ├── tools.py          # FK/IK + sim_* tools the LLM can call
    ├── ollama_client.py  # Real Ollama client
    └── fake_client.py    # Deterministic stand-in (UAT, CI)

assets/urdf/ur5/          # Hand-written UR5 URDF (primitive shapes)
docs/                     # UAT checklist, report template, Ollama manual
scripts/uat_run.py        # Automated UAT harness
.github/workflows/ci.yml  # Headless tests + lint + rtb-extras job
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
