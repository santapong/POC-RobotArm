"""End-to-end demo: drive the live PyBullet simulator via sim_* tools.

This bypasses Ollama and calls the same ``execute_tool`` entry point the LLM
agent uses, so you can see the bridge work without needing a local LLM
running. Watch the PyBullet window — the arm will sweep through several IK
targets and a small joint-space trajectory.

Run:
    python examples/demo_llm_sim.py
"""

from __future__ import annotations

import json
import threading
import time

from src.llm.tools import execute_tool
from src.simulation.bridge import SimBridge
from src.simulation.engine import RobotArmSim
from src.simulation.gui import run as run_gui


def _print(label: str, raw: str) -> None:
    payload = json.loads(raw)
    print(f"[{label}] {json.dumps(payload, indent=2)}")


def _scenario(stop_event: threading.Event) -> None:
    # Give the GUI a moment to render before we start commanding.
    time.sleep(1.0)

    _print("state", execute_tool("sim_get_state", {}))

    targets = [
        (0.4, 0.0, 0.6),
        (0.5, 0.2, 0.5),
        (0.3, -0.3, 0.7),
        (0.5, 0.0, 0.4),
    ]
    for x, y, z in targets:
        if stop_event.is_set():
            return
        _print(
            f"move_to_xyz({x},{y},{z})",
            execute_tool("sim_move_to_xyz", {"x": x, "y": y, "z": z}),
        )
        time.sleep(1.5)

    _print(
        "set_joint(idx=1, -45deg)",
        execute_tool("sim_set_joint", {"idx": 1, "angle_deg": -45.0}),
    )
    time.sleep(1.0)

    waypoints = [
        [0.0] * 7,
        [0.5, -0.3, 0.0, -1.5, 0.0, 1.0, 0.0],
        [-0.5, 0.3, 0.0, -1.0, 0.0, 0.5, 0.0],
        [0.0] * 7,
    ]
    _print(
        "play_trajectory",
        execute_tool(
            "sim_play_trajectory", {"waypoints": waypoints, "dwell_s": 0.6}
        ),
    )

    # Let the trajectory finish.
    time.sleep(len(waypoints) * 0.7 + 1.0)
    _print("state", execute_tool("sim_get_state", {}))

    # Leave the GUI open so the user can play with sliders. Stop on Ctrl+C.
    print("\nDemo complete. Use the GUI sliders to keep exploring, or Ctrl+C to quit.")


def main() -> None:
    sim = RobotArmSim(use_gui=True)
    bridge = SimBridge.initialize(sim)
    stop_event = threading.Event()

    worker = threading.Thread(
        target=_scenario, args=(stop_event,), name="sim-demo", daemon=True
    )
    worker.start()

    try:
        run_gui(bridge=bridge, stop_event=stop_event)
    finally:
        stop_event.set()
        SimBridge.shutdown()
        sim.disconnect()


if __name__ == "__main__":
    main()
