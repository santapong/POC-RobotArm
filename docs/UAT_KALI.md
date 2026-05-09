# UAT on Kali Linux — Setup and Run Guide

A copy-pasteable walkthrough for running the POC-RobotArm UAT on a clean
Kali Linux box. Tested target: **Kali Linux 2024.x or newer** (rolling
release; package names match Debian 12+).

The repo's primary tested platform is Ubuntu 22.04 (`docs/UAT_CHECKLIST.md`),
but Kali is Debian-based, so the path is identical apart from a couple of
package-name details called out below.

## 0. Prerequisites

- Fresh Kali Linux install (at least 4 GB RAM, 5 GB free disk)
- Internet access for `apt` and `pip`
- A user account with `sudo` rights
- Either a desktop session **or** `xvfb` (covered below) for the GUI smoke tests

## 1. System packages

```bash
sudo apt update
sudo apt install -y \
    python3 python3-venv python3-pip python3-dev \
    git build-essential pkg-config \
    libgl1 libglu1-mesa libegl1 \
    libxkbcommon0 libxkbcommon-x11-0 \
    libdbus-1-3 libfontconfig1 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-sync1 \
    libxcb-xfixes0 libxcb-xkb1 \
    xvfb
```

What each group is for:

| Group | Why |
|---|---|
| `python3` + venv + pip + dev | The interpreter, the venv module, headers for any C extension wheel that lacks a Linux binary |
| `git` + build-essential + pkg-config | Cloning + compiling fallback wheels (e.g. some scipy versions) |
| `libgl1` + `libglu1-mesa` + `libegl1` | OpenGL runtime — required by PyBullet's GUI and by Qt's OpenGL widget |
| `libxkbcommon*` + `libxcb-*` + `libdbus-1-3` + `libfontconfig1` | Qt platform plugins — without these, `PySide6` import succeeds but `QApplication([])` fails with `libEGL.so.1: cannot open shared object file` or `xcb` plugin errors |
| `xvfb` | Virtual framebuffer for running PyBullet's GL window on a headless box (CI / SSH-only Kali) |

Verify Python version:

```bash
python3 --version           # expected: 3.10 or 3.11 (Kali ships 3.11+)
```

If you get 3.9 or older, `apt install python3.11` (Kali rolling has 3.11) and
use that explicit binary in the venv step.

## 2. Clone and create the venv

```bash
git clone https://github.com/santapong/POC-RobotArm.git
cd POC-RobotArm
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 3. Install Python extras

Pick the install that matches what you're testing:

```bash
# Headless UAT only (motion IR + posts + drivers + sim, no rtb/CAM/UI)
pip install -e .[sim,dev]

# Headless UAT + FK/IK kinematics (recommended for full make uat coverage)
pip install -e .[sim,rtb,dev]

# Add the CAM toolpath demo (trimesh + ezdxf)
pip install -e .[sim,rtb,cam,dev]

# Add the PySide6 desktop UI demo
pip install -e .[sim,rtb,cam,ui,dev]

# Everything (incl. Ollama, Pillow)
pip install -e .[all,dev]
```

`pip install -e .[sim,rtb,cam,ui,dev]` is the recommended target if you want
to run every UAT story end-to-end.

## 4. Run the headless test suite

```bash
make test                          # ≥ 250 passing (full suite is ~257)
```

You can also run a focused subset:

```bash
python -m pytest tests/ -q --ignore=tests/test_gui_smoke.py --ignore=tests/test_ui_smoke.py
```

Lint check:

```bash
python -m ruff check src tests     # All checks passed!
```

## 5. Run the UAT acceptance harness

```bash
make uat                           # 20/20 stories passed
```

US-19 (CAM toolpath) auto-skips if `trimesh` is not installed.
US-20 (PySide6 UI) auto-skips if `PySide6` is not installed.
With the recommended extras above, both run.

## 6. Run the GUI smoke tests

Two GUI smoke tests need a display surface:

- `tests/test_gui_smoke.py` — opens a real PyBullet window, saves a PNG.
- `tests/test_ui_smoke.py` — instantiates `StationMainWindow` (PySide6).

### On a Kali desktop session

```bash
RUN_GUI_TESTS=1 python -m pytest tests/test_gui_smoke.py tests/test_ui_smoke.py -v
```

The PySide6 test runs under offscreen Qt by default (the test sets
`QT_QPA_PLATFORM=offscreen`); the PyBullet test opens a brief visible window.

### On a headless Kali (SSH-only / VM with no display)

```bash
xvfb-run -a -s "-screen 0 1280x720x24" \
    bash -c 'RUN_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen \
             python -m pytest tests/test_gui_smoke.py tests/test_ui_smoke.py -v'
```

`xvfb-run` provides a virtual display for PyBullet; `QT_QPA_PLATFORM=offscreen`
keeps Qt off the X server (which is faster and doesn't need extra plugins).

## 7. Run the demos

Each demo is fully self-contained and prints its result to stdout.

### `demo_export_rapid.py` — IRB 1200 pick-and-place → RAPID `.mod`

```bash
python examples/demo_export_rapid.py
```

Expected first 3 lines of output:

```
MODULE HelloPickPlace
  ! demo: pick-and-place
  ! target_robot: ABB IRB 1200-5/0.9
```

Followed by `tooldata`, `wobjdata`, `robtarget`, `jointtarget` declarations and
the `PROC main()` body. The script also writes `examples/hello.mod` next to
itself (gitignored).

### `demo_record_playback.py` — record → JSON → replay through a mock Driver

```bash
python examples/demo_record_playback.py
```

Expected: an "=== Mock driver call log ===" block enumerating the recorded
moves; round-trip equality `OK`. Two `UserWarning` lines about IO/Wait
skipping on the mock are expected — they demonstrate the player's graceful
degradation on drivers without those hooks.

### `demo_toolpath_stl.py` — STL → raster path → joint-optimal → RAPID

Requires `[cam]` + `[rtb]`.

```bash
python examples/demo_toolpath_stl.py
```

Expected: "Generated N surface_raster waypoints" and "DP joint trajectory
length: M" (M ≤ N because some raster points are off the IRB 1200's
envelope). Writes `examples/toolpath_demo.mod` (gitignored).

### `demo_station_save_load.py` — build a station, JSON round-trip

```bash
python examples/demo_station_save_load.py
```

Expected: "Built station 'demo_station': 4 frames, 1 robots, ..." and
"Round-trip OK: reloaded == original."

### `demo_station_gui.py` — PySide6 desktop UI

Requires `[ui]`.

```bash
# Desktop session
python examples/demo_station_gui.py

# Headless (SSH only)
xvfb-run -a -s "-screen 0 1280x720x24" python examples/demo_station_gui.py
```

A window opens with the outliner populated and a sample station preloaded.
Close the window to exit. The `Run → Emit RAPID/KRL/URScript` menu items
populate the code panel with vendor source for a hard-coded demo program.

## 8. Manual UAT stories — applicability on Kali

`docs/UAT_CHECKLIST.md` defines six manual stories. Here is which can be done
from a Kali box and which need an external system:

| ID | Story | Doable from Kali alone? | Notes |
|---|---|:---:|---|
| MS-1 | Load `.mod` into RobotStudio Virtual Controller | no | RobotStudio is Windows-only. Use a Windows host or a Windows VM (VMware / VirtualBox / QEMU). Copy `examples/hello.mod` to the Windows side over scp / shared folder. |
| MS-2 | RWS connect to a real or virtual ABB controller | partial | Driver runs on Kali. Controller (Virtual or real) runs elsewhere. Reach it over the LAN (`RWSDriver(host="<ip>", ...)`). |
| MS-3 | PySide6 desktop UI session | yes | Run `robotarm-station` on Kali desktop, or via xvfb + VNC for headless verification. |
| MS-4 | CAM toolpath end-to-end | yes | Pure Python, runs on Kali with `[cam,rtb]`. |
| MS-5 | KUKA KRL on real KRC4 (optional) | partial | Emit KRL on Kali; copy `.src/.dat` to a SmartPad-attached host for syntax check. |
| MS-6 | UR Script on real UR cobot (optional) | partial | Emit URScript on Kali; `nc <ur-host> 30002 < program.script` works directly from Kali. |

In short: MS-3, MS-4, and the emit halves of MS-5/MS-6 are pure Kali. MS-1
needs Windows. MS-2 needs a controller.

## 9. Troubleshooting

### `ImportError: libEGL.so.1: cannot open shared object file`

You skipped (or `apt` failed on) the Qt runtime libs. Re-run the apt
command in §1; `libegl1` is the headline package.

### `xcb: connection error`, `Could not load the Qt platform plugin "xcb"`

Some `libxcb-*` packages are missing. Re-run the apt command. If you only
need offscreen Qt (no actual window), set `QT_QPA_PLATFORM=offscreen`
**before** the `python -m pytest ...` invocation.

### `pybullet.error: GLEW initialization failed` (during a real PyBullet GUI)

You are on headless Kali without `xvfb-run`. Either run on a desktop
session or wrap the command in `xvfb-run -a -s "-screen 0 1280x720x24" ...`.

### `pip` fails to resolve `roboticstoolbox-python` / `scipy` / `spatialmath-python`

These are the heaviest deps in `[rtb]`. Common fixes:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install --use-pep517 -e .[sim,rtb,dev]
```

Some versions of `rtb-data` need `--use-pep517` because their
`setup.py` is legacy. This is not a code change in this repo.

### `make uat` reports `US-2 FAIL — List robots`

Catalog mismatch. The current expected set is
`{"panda", "ur5", "iiwa", "abb_irb1200"}`. If you're on an older branch,
update `scripts/uat_run.py` line 101 to match.

### `make uat` reports `US-19 PASS — skipped: trimesh not installed`

Add `[cam]` to your install: `pip install -e .[sim,rtb,cam,dev]`.

### `make uat` reports `US-20 PASS — skipped: PySide6 not installed`

Add `[ui]` to your install: `pip install -e .[sim,rtb,cam,ui,dev]`.

## 10. Known limitations on Kali

- **No native ABB RobotStudio.** Manual story MS-1 requires Windows.
- **Real-time motion (EGM, Phase 6 candidate) is untested on Kali.** The
  RWS driver is HTTPS digest auth from stdlib — that works fine. EGM is
  UDP + protobuf at 250 Hz and would need either an EGM-licensed
  controller or a custom mock.
- **STEP / IGES CAD intake is not part of `[cam]`.** Adding it would pull
  `pythonocc-core` (~300 MB, conda-preferred); deferred behind a future
  `[cad-step]` extra.

## 11. CI parity check

The repo's CI (`.github/workflows/ci.yml`) runs the equivalent commands on
Ubuntu 22.04. To verify Kali parity locally:

```bash
make test                # matches CI's "test-headless" job
python -m ruff check src tests   # matches CI's "lint" job
make test-rtb            # matches CI's "test-rtb" job (rtb-gated)
make uat                 # the additional UAT gate (CI doesn't run this; it's manual)
```

If all four are green, your Kali install is at parity with the CI baseline.

## 12. Where to record the result

Use `docs/UAT_REPORT_TEMPLATE.md` for the human signoff. Attach:

- `artifacts/uat_run.json` (auto-written by `scripts/uat_run.py`)
- `artifacts/station_smoke.png` (PySide6 UI smoke output)
- `artifacts/smoke_*.png` (PyBullet GUI smoke output)

Submit the filled template plus those artifacts in the PR review.
