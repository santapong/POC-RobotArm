# UAT Checklist — POC-RobotArm "AI-OS"

Tester: ____________________   Date: ____________________   Build: ____________________

Run each story below and tick the result. Attach `artifacts/smoke_*.png` and the
`scripts/uat_run.py` output to the report.

| ID | Story | How to run | Expected | Pass |
|----|-------|------------|----------|:----:|
| US-1  | **Boot** | `python -m src.main --sim --robot panda` | Window opens in <10s; Panda visible; no traceback. | ☐ |
| US-2  | **List robots** | In the REPL, type `list` (or with `--fake-llm`, ask "list available robots"). | Response names `panda`, `ur5`, `iiwa`. | ☐ |
| US-3  | **Direct move** | `sim move 0.4 0.0 0.5` | TCP visibly moves; `sim state` reports `ee_position` within 1 cm of `(0.4, 0, 0.5)`. | ☐ |
| US-4  | **LLM move** | With `--fake-llm` (or real Ollama), say *"move to x=0.4 y=0.0 z=0.5"*. | Same outcome as US-3 via tool call. | ☐ |
| US-5  | **Reset** | `sim reset` | All joints return to the catalog home pose within 2 s. | ☐ |
| US-6  | **FK** (rtb installed) | `python examples/demo_fk.py` | Numerical EE pose printed; matplotlib plot opens. | ☐ |
| US-7  | **IK + execute** | Restart with `--robot ur5`, then `sim move 0.5 0.0 0.5`. | IK returns; arm reaches target; no joint-limit error. | ☐ |
| US-8  | **Graceful exit** | Close the PyBullet window. | Process exits in <2 s, exit code 0; no orphaned threads (`ps -L`). | ☐ |
| US-9  | **Bad input** | With `--fake-llm`, ask *"fly the robot to the moon"*. | Polite refusal; no traceback. | ☐ |
| US-10 | **Concurrent commands** | Run `make uat` (concurrent path covered by `test_back_to_back_moves_complete`). | Both moves complete; final pose matches the second target. | ☐ |

## Sign-off

- [ ] All 10 stories PASS
- [ ] `make test` shows ≥ 30 passing tests (≥ 33 with rtb extras)
- [ ] `RUN_GUI_TESTS=1 pytest tests/test_gui_smoke.py` produces a non-empty PNG
- [ ] `python scripts/uat_run.py` exit code is 0

Tester signature: ____________________

## Real-Ollama signoff (optional — see `docs/UAT_OLLAMA_MANUAL.md`)

- [ ] Ran `python -m src.main --sim` with Ollama and a real model
- [ ] Recorded a 30 s screen capture covering US-1, US-3, US-5, US-8
- [ ] Attached recording to the UAT report
