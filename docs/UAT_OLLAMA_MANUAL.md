# Real-Ollama UAT — Manual Checklist

The automated `make uat` harness uses a deterministic fake LLM. This
manual pass exercises the same flow against an actual local model so we
can verify the tool-calling loop end-to-end with real natural language.

Run this **once per release** on a real desktop, capture a screen
recording, and attach it to the UAT report.

## Prerequisites

1. Install Ollama: <https://ollama.com/download>
2. Start the daemon: `ollama serve` (usually starts automatically)
3. Pull a model with tool-calling support:
   ```bash
   ollama pull llama3.1
   ```
4. Verify: `ollama list` shows `llama3.1`.

## Steps

1. **Launch** the simulator + LLM together:
   ```bash
   python -m src.main --sim --robot panda
   ```
   Expected: `LLM mode active (model: llama3.1)` followed by the PyBullet
   window opening with the Panda visible.

2. **Ask** these three prompts in order (paste verbatim). Record the
   model's response and the arm's behaviour:
   - **P1.** *"What's the current end-effector position?"*
     Expected: a number triple matching what `sim state` shows.
   - **P2.** *"Move the arm to x=0.4, y=0.0, z=0.5."*
     Expected: arm visibly moves; reply mentions the `sim_move_to_xyz`
     tool or describes the action.
   - **P3.** *"Reset the arm."*
     Expected: arm returns to the home pose within ~2 s.

3. **Close** the PyBullet window. The shell prompt should return to your
   terminal within ~1 s. Type `exit` if the REPL is still active.

## Pass criteria

- [ ] All three prompts produced sensible responses (not "tool error", not
      gibberish, not silence).
- [ ] Each move was visible in the GUI.
- [ ] Closing the window terminated the process cleanly.
- [ ] Recording captured at least 30 seconds of the session.

## Failure modes & quick fixes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `LLM not available. Falling back to direct command mode.` | Ollama not running, or model not pulled | `ollama serve` then `ollama pull llama3.1` |
| Model replies in plain text without calling tools | Model lacks tool-calling support | Use `--model llama3.1` or another tool-capable model |
| GUI window closes but REPL keeps the terminal | Old build before M2 lifecycle fix | Rebuild from current branch |
| `IK_UNREACHABLE` for a target you expect to work | Pose is outside the arm's workspace | Try x ≤ 0.7, z ≤ 0.9 for Panda |

Tester sign-off: __________________________________   Date: __________
