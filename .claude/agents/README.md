# Multi-agent setup for POC-RobotArm

Nine reusable Claude Code sub-agents in this directory. The pattern is called
**orchestrator-workers**: one orchestrator (the `project-manager`) plans the
work and dispatches specialized workers; the workers stay focused on one job
each.

## Roster

| Agent | Role | Read | Write | Run | Web | Model |
|---|---|:---:|:---:|:---:|:---:|---|
| `project-manager` | Surveys, plans, dispatches workers, verifies, commits | yes | no | yes | no | **opus** |
| `architect` | Designs the implementation: paths, signatures, edge cases, test strategy | yes | no | read-only | no | **opus** |
| `reviewer` | Audits the implementer's diff: correctness, security, style, threading | yes | no | read-only | no | **opus** |
| `researcher` | Read-only deep-dive on existing code or external libs/APIs | yes | no | read-only | yes | sonnet |
| `motion-planner` | Domain specialist: trajectories, limits, TCP/RTCP frames, singularity. Designs **and** writes code in this domain. | yes | yes (motion / kinematics only) | yes | no | **opus** |
| `implementer` | Writes code from the architect's design. Runs ruff. | yes | yes | yes | no | sonnet |
| `tester` | Writes and runs pytest. Reports failures honestly. | yes | yes (tests only) | yes | no | sonnet |
| `devops` | Edits pyproject / Makefile / CI / .gitignore / console scripts | yes | yes (config only) | yes | no | sonnet |
| `documenter` | README, docs/, INSTALL, public docstrings | yes | yes (docs only) | yes | no | sonnet |

## Flow (when the full pipeline is in play)

```
user
 └─> project-manager
      ├─> researcher       (optional, if there's an unknown)
      ├─> architect        (design)
      ├─> implementer      (code)
      ├─> reviewer         (optional; for security / threading / new APIs)
      ├─> tester           (tests + run)              ← PM iterates impl⇄test up to 2x
      ├─> devops           (optional; new dep / script / CI)
      └─> documenter       (optional; end-of-phase polish)
```

The PM **picks the team per task** rather than running every worker every time:

| Task shape | Team |
|---|---|
| Typo fix, lint cleanup, single-file edit | (none — direct edit) |
| Docs-only update | `documenter` |
| New CI gate, new pyproject extra | `devops` |
| Small new module with a clear API | `architect` → `implementer` → `tester` |
| Module touching auth / network / file I/O | + `reviewer` between implementer and tester |
| Module against an unfamiliar vendor API | + `researcher` before architect |
| New dep + README update | + `devops` and `documenter` at end |
| Trajectory / limits / TCP / RTCP / manipulability work | `motion-planner` (replaces architect + implementer) → `tester` → `reviewer` |

## How to invoke

In a future Claude Code session opened in this repo:

```
"Use the project-manager agent to plan and ship STEP/IGES CAD support behind a [cad-step] extra."
```

The PM does its survey, picks a team, dispatches workers in turn, verifies, and commits. You don't address the workers directly.

You can call individual workers for narrow asks:

```
"Use the researcher to summarize how src/drivers/abb/rws_client.py handles digest auth."
"Use the architect to design how src/llm/tools.py should expose the toolpath generator."
"Use the documenter to add a Quickstart section for the RWS driver to README.md."
```

## Why this shape

- **PM separated from execution.** The PM has no `Write` / `Edit` tools. It cannot half-implement a feature; its only output is plans and dispatches. This is the orchestrator-workers contract.
- **Architect separated from implementer.** Forcing an explicit design pass surfaces ambiguity before any code is written.
- **Reviewer separated from tester.** A reviewer reads code with security / style / threading lenses; a tester reads code through "what would break this". Different jobs, different mental models.
- **Devops and documenter as their own roles.** Config and prose live in different files than `src/`; isolating them keeps source-code agents from drifting into "while I'm here, let me also tweak the README".
- **Researcher is optional.** Most phases don't need one. Adding it for every phase would be theatre.
- **Motion-planner is a domain specialist that fuses architect + implementer.** Trajectory and frame math is subtle enough (quaternion order, frame inversion, RTCP semantics, singularity thresholds) that a generic implementer translating a generic architect's spec leaks errors. The motion-planner reads, designs, *and* writes code in one pass for kinematics work, so the design and code never drift.

## Model choices

The rule: **opus where judgment dominates, sonnet where the work is execution against a clear spec.**

- `opus` (4 agents): PM, architect, reviewer, motion-planner.
  - PM plans the team and resolves contradictions between phases.
  - Architect enumerates edge cases and shapes APIs that the rest of the team will hit one-to-one.
  - Reviewer catches what the implementer missed — necessarily a judgment call.
  - Motion-planner does both judgment-heavy design and judgment-heavy implementation in the kinematics domain.
- `sonnet` (5 agents): researcher, implementer, tester, devops, documenter.
  - Researcher summarizes and cites.
  - Implementer follows the architect's design top-to-bottom.
  - Tester translates the architect's test strategy into pytest functions.
  - Devops edits config files to a clear list.
  - Documenter writes prose for a known audience.

This balance assumes the architect's design is solid — when it is, the implementer and tester are doing translation, not invention. If you find sonnet output weak on this repo specifically (quaternions, threading, IR invariants are subtle), flip `model: sonnet` to `model: opus` in `implementer.md` and `tester.md`. The cost increase is roughly 5x on those calls.

## When NOT to use this workflow

- Single-file edits, typo fixes, lint-only changes — the PM-workers round-trip costs more than it saves.
- Pure read questions ("how does X work?") — answer directly from a survey; no workers needed.
- Emergencies — short-circuit to a direct fix and explain what you skipped.
