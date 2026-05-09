# UAT Checklist — POC-RobotArm "AI-OS"

Tester: ____________________   Date: ____________________   Build: ____________________

> **Running UAT on Kali Linux?** See [`docs/UAT_KALI.md`](UAT_KALI.md) for the
> apt + pip + xvfb setup walkthrough, then come back here for the story table.
> A `make install-kali` one-shot covers system libs + extras in a single step.

Run each story below and tick the result. Attach `artifacts/smoke_*.png` and the
`scripts/uat_run.py` output to the report.

| ID | Story | How to run | Expected | Pass |
|----|-------|------------|----------|:----:|
| US-1  | **Boot** | `python -m src.main --sim --robot panda` | Window opens in <10s; Panda visible; no traceback. | ☐ |
| US-2  | **List robots** | In the REPL, type `list` (or with `--fake-llm`, ask "list available robots"). | Response names `panda`, `ur5`, `iiwa`, `abb_irb1200`. | ☐ |
| US-3  | **Direct move** | `sim move 0.4 0.0 0.5` | TCP visibly moves; `sim state` reports `ee_position` within 1 cm of `(0.4, 0, 0.5)`. | ☐ |
| US-4  | **LLM move** | With `--fake-llm` (or real Ollama), say *"move to x=0.4 y=0.0 z=0.5"*. | Same outcome as US-3 via tool call. | ☐ |
| US-5  | **Reset** | `sim reset` | All joints return to the catalog home pose within 2 s. | ☐ |
| US-6  | **FK** (rtb installed) | `python examples/demo_fk.py` | Numerical EE pose printed; matplotlib plot opens. | ☐ |
| US-7  | **IK + execute** | Restart with `--robot ur5`, then `sim move 0.5 0.0 0.5`. | IK returns; arm reaches target; no joint-limit error. | ☐ |
| US-8  | **Graceful exit** | Close the PyBullet window. | Process exits in <2 s, exit code 0; no orphaned threads (`ps -L`). | ☐ |
| US-9  | **Bad input** | With `--fake-llm`, ask *"fly the robot to the moon"*. | Polite refusal; no traceback. | ☐ |
| US-10 | **Concurrent commands** | Run `make uat` (concurrent path covered by `test_back_to_back_moves_complete`). | Both moves complete; final pose matches the second target. | ☐ |
| US-11 | **RAPID export** | `python examples/demo_export_rapid.py` | `MODULE HelloPickPlace` written, contains `MoveAbsJ`/`MoveL`, ends with `ENDMODULE`. | ☐ |
| US-12 | **KUKA KRL export** | Run `make uat` (story exercises `KRLPost().emit()`). | Output contains `DEF UATDemo` and `PTP` or `LIN`. | ☐ |
| US-13 | **UR Script export** | Run `make uat` (story exercises `URScriptPost().emit()`). | Output starts with `def main():`, contains `movel`, ends with `main()` call. | ☐ |
| US-14 | **Motion IR round-trip** | Run `make uat` (story dumps + loads a `Program` via `motion.ir.dump`/`load`). | Loaded program equals original (deep equality on frozen dataclasses). | ☐ |
| US-15 | **Record/playback** | Run `make uat` (story builds a Recorder, plays through a mock Driver). | Driver's `move_joint` and `move_linear` invoked in order. | ☐ |
| US-16 | **Station save/load** | `python examples/demo_station_save_load.py` | `tmp_station.json` written, reload equals original; or run `make uat` for the same check. | ☐ |
| US-17 | **Driver Protocol** | Run `make uat` (story confirms `SimDriver` and `RWSDriver` both satisfy the `Driver` Protocol via `runtime_checkable`). | Both pass `isinstance(.., Driver)`. | ☐ |
| US-18 | **RWS endpoint flow** | Run `make uat` (story stubs the HTTP session and runs `RWSDriver.run_program`). | Mastership-request, fileservice-upload, loadmodule, execution-start endpoints all hit. | ☐ |
| US-19 | **CAM surface raster** | Run `make uat` (skipped if `trimesh` not installed; otherwise exercises `surface_raster` on a synthetic STL). | ≥ 4 raster waypoints generated; PoseTargets returned. | ☐ |
| US-20 | **PySide6 UI smoke** | Run `make uat` (skipped if PySide6 not installed; otherwise instantiates `StationMainWindow` under offscreen Qt). | Window title starts with `POC-RobotArm`. | ☐ |

## Manual stories (require external systems — not run by `make uat`)

| ID | Story | How to run | Expected | Pass |
|----|-------|------------|----------|:----:|
| MS-1 | **Load RAPID into RobotStudio Virtual Controller** | `python examples/demo_export_rapid.py`, copy `examples/hello.mod` to a Virtual Controller's HOME, load via FlexPendant. | Module loads with no syntax errors; `main` PROC visible; can step through `MoveAbsJ`/`MoveL` lines. | ☐ |
| MS-2 | **RWS connect to a real or virtual ABB controller** | Set up an ABB Virtual Controller (RobotStudio) with PC Interface; from a Python REPL: `RWSDriver(host="<vc>", username="Default User", password="robotics").connect()`. | `is_connected()` is True; `get_state()` returns plausible joints/pose; `run_program` uploads + starts a small program. | ☐ |
| MS-3 | **PySide6 desktop UI session** | `robotarm-station` (or `python examples/demo_station_gui.py`). | Main window opens; File → Open loads a `.station.json`; Robot menu spawns the existing PyBullet GUI as a side window; Run → Emit RAPID populates the code panel. | ☐ |
| MS-4 | **CAM toolpath end-to-end** | `pip install -e .[sim,rtb,cam,dev]` then `python examples/demo_toolpath_stl.py`. | Demo runs; prints "Generated N waypoints" and "DP joint trajectory length: M"; writes `examples/toolpath_demo.mod` containing `MoveL` for each reachable waypoint. | ☐ |
| MS-5 | **KUKA KRL on real KRC4** (optional) | Run a KRL emit, copy paired `.src`/`.dat` to controller, syntax-check on the SmartPad. | No syntax errors; `PTP/LIN` lines visible; `$VEL.CP`/`$APO.CDIS` set as expected. | ☐ |
| MS-6 | **UR Script on real UR cobot** (optional) | Run a URScript emit; `nc <ur-host> 30002 < program.script` from a workstation. | Robot moves through the planned waypoints; `set_digital_out` toggles match the program. | ☐ |

## Sign-off

- [ ] All 20 automated stories PASS (`make uat` exits 0)
- [ ] `make test` shows ≥ 250 passing tests (full suite is ~257)
- [ ] `RUN_GUI_TESTS=1 pytest tests/test_gui_smoke.py tests/test_ui_smoke.py` produces a non-empty PNG (PyBullet) and a non-empty PNG (PySide6)
- [ ] At least MS-1 and MS-3 from the manual stories signed off (RAPID round-trip and desktop UI session)
- [ ] MS-2 (RWS) signed off if a controller (real or virtual) is available

Tester signature: ____________________

## Real-Ollama signoff (optional — see `docs/UAT_OLLAMA_MANUAL.md`)

- [ ] Ran `python -m src.main --sim` with Ollama and a real model
- [ ] Recorded a 30 s screen capture covering US-1, US-3, US-5, US-8
- [ ] Attached recording to the UAT report
