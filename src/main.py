"""CLI entry point for the Robot Arm Kinematics Solver."""

import argparse
import select
import sys
import threading

from src.llm.agent import RobotArmAgent


BANNER = """
╔══════════════════════════════════════════════════╗
║    POC-RobotArm: Kinematics Solver with LLM     ║
║                                                  ║
║  Forward & Inverse Kinematics for Robot Arms     ║
║  Powered by Local LLM (Ollama)                   ║
╚══════════════════════════════════════════════════╝

Type your question or command. Examples:
  "What is the end-effector position of the Panda at joint angles all zeros?"
  "Find joint angles to reach position (0.5, 0.0, 0.5) with the UR5"
  "List available robots"
  "Plot the Panda at joint angles 0 -0.3 0 -2.2 0 2.0 0.79"

Type 'quit' or 'exit' to leave. Type 'reset' to clear conversation.
"""


def _build_agent(args) -> RobotArmAgent:
    if args.no_llm:
        agent = RobotArmAgent.__new__(RobotArmAgent)
        agent.model = args.model
        agent.ollama_client = None
        agent._llm_available = False
        print("Running in direct command mode (--no-llm).")
        print("Commands: fk, ik, list, info, plot, sim, help\n")
        return agent

    if args.fake_llm:
        from src.llm.fake_client import FakeOllamaClient
        agent = RobotArmAgent(model=args.model, client=FakeOllamaClient())
        print("Fake LLM mode active (deterministic, no network).\n")
        return agent

    agent = RobotArmAgent(model=args.model)
    if agent.is_llm_mode:
        print(f"LLM mode active (model: {args.model})\n")
    else:
        print("Falling back to direct command mode.\n")
    return agent


def _read_line_with_stop(stop_event: threading.Event, prompt: str = "You > ") -> str | None:
    """Read a line from stdin, polling ``stop_event`` between waits.

    Returns the typed line, or ``None`` if ``stop_event`` was set first or
    stdin closed. Uses ``select`` so a closed GUI window can wake the REPL
    without requiring the user to press Enter.
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()
    while not stop_event.is_set():
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0.25)
        except (ValueError, OSError):
            # stdin was closed (e.g. piped input ended)
            return None
        if ready:
            line = sys.stdin.readline()
            if line == "":
                return None  # EOF
            return line.rstrip("\n")
    return None


def _repl(agent: RobotArmAgent, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            user_input = _read_line_with_stop(stop_event)
        except KeyboardInterrupt:
            print("\nGoodbye!")
            stop_event.set()
            return
        if user_input is None:
            # stop_event tripped, EOF, or stdin closed.
            stop_event.set()
            return
        user_input = user_input.strip()

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            stop_event.set()
            return
        if user_input.lower() == "reset":
            if agent.ollama_client:
                agent.ollama_client.reset()
            print("Conversation reset.\n")
            continue

        response = agent.process(user_input)
        print(f"\nAssistant > {response}\n")


def _run_with_sim(args) -> None:
    """Launch the simulator on the main thread and the REPL on a worker."""
    from src.simulation.bridge import SimBridge
    from src.simulation.engine import RobotArmSim
    from src.simulation.gui import run as run_gui

    print(BANNER)
    print(f"Starting 3D simulator ({args.robot}) and REPL together...\n")

    if args.urdf:
        sim = RobotArmSim(urdf_path=args.urdf, use_gui=True)
    else:
        sim = RobotArmSim(robot_name=args.robot, use_gui=True)
    bridge = SimBridge.initialize(sim)
    agent = _build_agent(args)

    stop_event = threading.Event()
    repl_thread = threading.Thread(
        target=_repl, args=(agent, stop_event), name="llm-repl", daemon=True
    )
    repl_thread.start()

    try:
        run_gui(bridge=bridge, stop_event=stop_event, hz=args.hz)
    finally:
        stop_event.set()
        # Give the REPL up to ~1s to notice the stop_event and exit cleanly.
        repl_thread.join(timeout=1.0)
        SimBridge.shutdown()
        sim.disconnect()


def _run_repl_only(args) -> None:
    print(BANNER)
    agent = _build_agent(args)
    stop_event = threading.Event()
    _repl(agent, stop_event)


def main():
    parser = argparse.ArgumentParser(description="Robot Arm Kinematics Solver with LLM")
    parser.add_argument(
        "--model", default="llama3.1",
        help="Ollama model to use (default: llama3.1)",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Disable LLM and use direct command mode",
    )
    parser.add_argument(
        "--fake-llm", action="store_true",
        help="Use the deterministic FakeOllamaClient (no network, for tests/UAT)",
    )
    parser.add_argument(
        "--sim", action="store_true",
        help="Launch the 3D simulator alongside the REPL so the LLM can drive it",
    )
    parser.add_argument(
        "--robot", default="panda",
        choices=["panda", "ur5", "iiwa"],
        help="Robot to load when --sim is set (default: panda)",
    )
    parser.add_argument(
        "--urdf", default=None,
        help="Override --robot with a raw URDF path",
    )
    parser.add_argument(
        "--hz", type=float, default=240.0,
        help="Simulator step rate when using --sim (default: 240)",
    )
    args = parser.parse_args()

    if args.sim:
        _run_with_sim(args)
    else:
        _run_repl_only(args)


if __name__ == "__main__":
    main()
