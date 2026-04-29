# UAT Report — POC-RobotArm "AI-OS"

| Field | Value |
|-------|-------|
| Tester | _________________________ |
| Date | _________________________ |
| Build / commit SHA | _________________________ |
| OS | Ubuntu 22.04 / other: ____________ |
| Python version | _________________________ |
| rtb installed? | yes / no |
| Ollama installed? | yes / no |

## Automated harness (`make uat`)

| ID | Story | Result | Notes |
|----|-------|:------:|-------|
| US-1  | Boot | ☐ PASS / ☐ FAIL | |
| US-2  | List robots | ☐ PASS / ☐ FAIL | |
| US-3  | Direct move | ☐ PASS / ☐ FAIL | |
| US-4  | LLM move (fake) | ☐ PASS / ☐ FAIL | |
| US-5  | Reset | ☐ PASS / ☐ FAIL | |
| US-6  | FK (rtb) | ☐ PASS / ☐ N/A — rtb missing | |
| US-7  | UR5 IK + execute | ☐ PASS / ☐ FAIL | |
| US-8  | Graceful exit | ☐ PASS / ☐ FAIL | |
| US-9  | Bad input | ☐ PASS / ☐ FAIL | |
| US-10 | Concurrent commands | ☐ PASS / ☐ FAIL | |

`scripts/uat_run.py` exit code: ____   Total time: ____ s

## Manual checklist (`docs/UAT_CHECKLIST.md`)

Attach completed checklist (or paste below).

## Test suite

- `make test` — passing tests: ___ / ___ ; time: ____ s
- `make test-rtb` (if rtb installed) — passing: ___ / ___
- `RUN_GUI_TESTS=1 pytest tests/test_gui_smoke.py` — artifact: `artifacts/smoke_____.png`

## Real-Ollama signoff (optional)

See `docs/UAT_OLLAMA_MANUAL.md`. Attach the screen recording.

## Defects observed

| ID | Severity | Description | Repro steps | Workaround |
|----|----------|-------------|-------------|------------|
|    |          |             |             |            |

## Sign-off

- [ ] All blocking defects resolved
- [ ] Automated UAT (`make uat`) returns 0
- [ ] Manual checklist 10/10 PASS
- [ ] Artifacts attached: `artifacts/uat_run.json`, `artifacts/smoke_*.png`, screen recording (if applicable)

Tester signature: __________________________________  Date: __________
