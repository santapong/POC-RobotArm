"""CLI entry point for the Robot Arm Kinematics Solver."""

import argparse
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

    agent = RobotArmAgent(model=args.model)
    if agent.is_llm_mode:
        print(f"LLM mode active (model: {args.model})\n")
    else:
        print("Falling back to direct command mode.\n")
    return agent


def _repl(agent: RobotArmAgent, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            user_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            stop_event.set()
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            stop_event.set()
            break
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
    print("Starting 3D simulator (PyBullet) and REPL together...\n")

    sim = RobotArmSim(urdf_path=args.urdf, use_gui=True)
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
        "--sim", action="store_true",
        help="Launch the 3D simulator alongside the REPL so the LLM can drive it",
    )
    parser.add_argument(
        "--urdf", default=None,
        help="URDF path for --sim (default: kuka_iiwa/model.urdf)",
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
