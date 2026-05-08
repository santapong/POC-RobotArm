# Multi-agent setup for POC-RobotArm

Four reusable Claude Code sub-agents, defined as markdown files in this directory:

| Agent | Role | Tools | Model |
|---|---|---|---|
| `project-manager` | Surveys the project, plans phased work, dispatches workers, verifies, commits, reports | Read + Bash + TodoWrite + Agent (no Write/Edit) | opus |
| `architect` | Designs the implementation: file paths, API signatures, edge cases, test strategy. Read-only. | Read + Bash (read-only) | opus |
| `implementer` | Writes the code from the architect's design. Runs ruff. No tests. | Read + Write + Edit + Bash | opus |
| `tester` | Writes and runs pytest tests. Reports pass/fail. Does not modify implementation. | Read + Write + Edit + Bash | opus |

## How they fit together

```
user
 └─> project-manager
      ├─> architect     (design)        ──┐
      ├─> implementer   (code)          ──┤  one phase
      └─> tester        (tests + run)   ──┘  (PM may iterate impl→test up to 2x)
```

Each phase is design → implement → test. The PM drives this pipeline once per phase. Multiple phases can have their **architect** stages run in parallel if file scopes don't overlap; **implementers** must serialize on shared files.

## How to invoke

In any future session, ask:

> "Use the project-manager agent to plan and ship a feature that adds STEP/IGES CAD support behind a `[cad-step]` extra."

Claude will dispatch the `project-manager` sub-agent. The PM does its survey, plans, and dispatches the workers itself — you don't need to address them directly.

You can also invoke the workers individually for narrow tasks:

- "Use the architect to design how `src/llm/tools.py` should expose the new toolpath generator."
- "Use the implementer to build the file the architect just spec'd."
- "Use the tester to write tests for `src/foo/bar.py` and run them."

## Why these specific roles

- **PM separates planning from execution.** The PM never edits code, so it can never be tempted to half-implement a feature. Its only output is plans and dispatches.
- **Architect separates design from implementation.** Forcing an explicit design pass surfaces ambiguity early, before any code is written, and produces a self-contained spec the implementer can follow without thinking.
- **Implementer separates code from tests.** Test-first or test-after both work; what matters is that the test author isn't biased by knowing the implementation's branch structure. Splitting them keeps the tester honest.
- **Tester separates verification from authoring.** A tester that wrote the implementation will tend to write tests that exercise only the paths it remembers. A fresh tester reads the API surface and the architect's edge cases, and tests those.

The cost is a longer round-trip (3 hand-offs per phase). Use this workflow only when:

- The change spans ≥2 files
- The change has non-trivial public API
- You want a trail of design + implementation + tests as separate artifacts

For typo fixes, single-file edits, lint-only changes, just ask Claude directly.
