# Installation Guide

## Supported environments

- **Ubuntu 22.04** (primary UAT target)
- Python **3.10** or **3.11**
- A real desktop / X11 / Wayland display for the GUI (optional — headless mode works for CI and the UAT harness)

macOS and Windows are out of scope for this UAT cycle.

## Five-minute install

```bash
git clone https://github.com/santapong/POC-RobotArm.git
cd POC-RobotArm
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e .[sim,dev]
```

Verify:

```bash
make test                # 31 tests pass
make uat                 # 10/10 stories pass, exit code 0
```

## Optional extras

```bash
pip install -e .[rtb]    # FK/IK + matplotlib visualization
pip install -e .[llm]    # Ollama client (you also need the daemon)
pip install -e .[gui]    # Pillow (only needed for GUI smoke PNG capture)
pip install -e .[all]    # everything above
```

## Running the GUI smoke test

Requires a real display:

```bash
RUN_GUI_TESTS=1 pytest tests/test_gui_smoke.py -v
ls artifacts/smoke_*.png
```

The PNG is one frame from the PyBullet window with the Panda at IK target (0.4, 0, 0.5).

## Running the real-Ollama path

See `docs/UAT_OLLAMA_MANUAL.md` for the step-by-step manual checklist. tl;dr:

```bash
ollama serve
ollama pull llama3.1
python -m src.main --sim --robot panda
```

## Common gotchas

- **`pybullet.error: Cannot connect to GUI`** — running on a headless box. Use `RobotArmSim(use_gui=False)` from Python, or `make uat` (headless) instead of `make sim`.
- **roboticstoolbox install is slow / fails** — it pulls scipy, matplotlib, spatialmath. Skip the `[rtb]` extra unless you need FK/IK; the simulator path doesn't require it.
- **Old `setup.py` still around** — the project now uses `pyproject.toml`. `setup.py` remains for backwards-compatible `python setup.py install` invocations but `pip install -e .` is preferred.
- **GUI hangs after closing the window** — make sure you're on a build that includes M2 (lifecycle hardening). The branch `claude/robot-arm-simulation-7xMCu` has it.

## Verifying a clean install

The UAT-ready definition of done is:

```bash
git clean -xfd                                   # nuke any state
python -m venv .venv && source .venv/bin/activate
pip install -e .[sim,dev]
make test                                        # 31 passed, ≤2 skipped
make uat                                         # 10/10 PASS, exit 0
```

If both commands succeed in <90 s on a fresh Ubuntu 22.04 VM, you're ready for UAT.
