#!/usr/bin/env python3
"""Measure the optimize_joints cost-scaling / branch-consistency fix.

Loads the pre-fix implementation straight out of git history and runs it beside
the current one over identical waypoints, so the comparison is a live
measurement rather than remembered numbers. Regenerates
``docs/experiments/optimizer-cost-scaling.png``.

    python scripts/experiment_optimizer_cost.py [<before-commit-ish>]

The default compares against the parent of the fix commit. Pass another
commit-ish to compare against a different baseline.

Requires matplotlib and roboticstoolbox, both already project dependencies.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.motion.ir import PoseTarget  # noqa: E402
from src.robots.predefined import get_ur5  # noqa: E402
from src.toolpath.optimizer import optimize_joints as opt_new  # noqa: E402

# Parent of "Fix two defects in optimize_joints" — the last commit with the
# unbounded 1/m penalty and the unaligned candidate rows.
DEFAULT_BEFORE = "55fc0f1^"

TOOL_DOWN = (0.0, 1.0, 0.0, 0.0)
OUT = ROOT / "docs" / "experiments" / "optimizer-cost-scaling.png"
OLD_C, NEW_C = "#c0392b", "#1a7f5a"


def load_before(commitish: str):
    """Import src/toolpath/optimizer.py as it stood at ``commitish``."""
    blob = subprocess.run(
        ["git", "show", f"{commitish}:src/toolpath/optimizer.py"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    tmp = Path(tempfile.mkdtemp()) / "optimizer_before.py"
    tmp.write_text(blob)
    spec = importlib.util.spec_from_file_location("optimizer_before", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["optimizer_before"] = mod
    spec.loader.exec_module(mod)
    return mod.optimize_joints


def straight_line(n: int = 14, x: float = 0.40) -> list[PoseTarget]:
    """A straight line across the UR5 workspace, 20 mm steps, tool down."""
    return [PoseTarget(xyz_m=(x, -0.13 + 0.02 * i, 0.30), quat_wxyz=TOOL_DOWN)
            for i in range(n)]


def run(fn, wps):
    return np.asarray(fn(get_ur5(), wps, phi_step_deg=30.0,
                         manipulability_min=1e-6))


def steps(qs):
    return np.linalg.norm(np.diff(qs, axis=0), axis=1)


def main() -> int:
    before_ref = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BEFORE
    opt_old = load_before(before_ref)

    wps = straight_line()
    q_old, q_new = run(opt_old, wps), run(opt_new, wps)
    s_old, s_new = steps(q_old), steps(q_new)
    robot = get_ur5()
    m_old = [robot.manipulability(q) for q in q_old]
    m_new = [robot.manipulability(q) for q in q_new]

    print(f"before ({before_ref}): travel={s_old.sum():.3f} rad  "
          f"max step={s_old.max():.3f}  mean manip={np.mean(m_old):.4f}")
    print(f"after:                 travel={s_new.sum():.3f} rad  "
          f"max step={s_new.max():.3f}  mean manip={np.mean(m_new):.4f}")
    print(f"  -> travel {100*(1-s_new.sum()/s_old.sum()):.0f}% lower, "
          f"worst step {s_old.max()/s_new.max():.1f}x smaller, "
          f"manipulability {100*(np.mean(m_new)/np.mean(m_old)-1):+.1f}%")

    plt.rcParams.update({
        "figure.facecolor": "white", "axes.grid": True, "grid.alpha": 0.25,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
    })
    fig = plt.figure(figsize=(11, 7.2))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.35, 1, 1], hspace=0.55, wspace=0.22)

    for col, (qs, name, colour) in enumerate(
            ((q_old, "before", OLD_C), (q_new, "after", NEW_C))):
        ax = fig.add_subplot(gs[0, col])
        for j in range(qs.shape[1]):
            ax.plot(qs[:, j], lw=1.4, alpha=0.85, label=f"q{j+1}")
        ax.set_title(f"Joint trajectories — {name}", fontweight="bold", color=colour)
        ax.set_xlabel("waypoint")
        ax.set_ylabel("angle (rad)")
        if col == 1:
            ax.legend(ncol=3, fontsize=7, frameon=False, loc="upper right")

    ax = fig.add_subplot(gs[1, :])
    x = np.arange(1, len(s_old) + 1)
    ax.bar(x - 0.2, s_old, width=0.4, color=OLD_C,
           label=f"before (total {s_old.sum():.2f} rad)")
    ax.bar(x + 0.2, s_new, width=0.4, color=NEW_C,
           label=f"after (total {s_new.sum():.2f} rad)")
    ax.set_title("Per-step joint travel — the spike is the IK branch flip",
                 fontweight="bold")
    ax.set_xlabel("step between waypoints")
    ax.set_ylabel("norm dq (rad)")
    ax.legend(frameon=False, fontsize=8)

    ax = fig.add_subplot(gs[2, 0])
    ax.plot(m_old, color=OLD_C, lw=1.6, marker="o", ms=3, label="before")
    ax.plot(m_new, color=NEW_C, lw=1.6, marker="o", ms=3, label="after")
    ax.set_title("Manipulability — the fix trades a little of this away",
                 fontweight="bold", fontsize=9)
    ax.set_xlabel("waypoint")
    ax.set_ylabel("m")
    ax.legend(frameon=False, fontsize=8)

    ax = fig.add_subplot(gs[2, 1])
    vals = [float(np.mean(s_new)), 1.0 / float(np.mean(m_new)), 0.0]
    ax.bar(["norm dq\n(typical step)", "lambda/m\n(old penalty)",
            "penalty\n(new, median-ref)"], vals, color=["#555", OLD_C, NEW_C])
    ax.set_yscale("symlog", linthresh=0.01)
    ax.set_title("Why the cost was broken: terms had no common scale",
                 fontweight="bold", fontsize=8.5)
    ax.set_ylabel("cost contribution (symlog)")
    for i, v in enumerate(vals):
        ax.text(i, v, f" {v:.2f}", ha="center", va="bottom", fontsize=8)

    fig.suptitle(
        "POC-RobotArm optimize_joints — cost-scaling and branch-consistency fix\n"
        "UR5, 14 waypoints 20 mm apart, tool down",
        fontweight="bold", fontsize=11, y=0.98)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=150, bbox_inches="tight")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
