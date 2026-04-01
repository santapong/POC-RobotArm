"""CLI entry point for the Robot Arm Kinematics Solver."""

import argparse
import sys

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
    args = parser.parse_args()

    print(BANNER)

    if args.no_llm:
        # Force direct command mode
        agent = RobotArmAgent.__new__(RobotArmAgent)
        agent.model = args.model
        agent.ollama_client = None
        agent._llm_available = False
        print("Running in direct command mode (--no-llm).")
        print("Commands: fk, ik, list, info, plot, help\n")
    else:
        agent = RobotArmAgent(model=args.model)
        if agent.is_llm_mode:
            print(f"LLM mode active (model: {args.model})\n")
        else:
            print("Falling back to direct command mode.\n")

    while True:
        try:
            user_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break
        if user_input.lower() == "reset":
            if agent.ollama_client:
                agent.ollama_client.reset()
            print("Conversation reset.\n")
            continue

        response = agent.process(user_input)
        print(f"\nAssistant > {response}\n")


if __name__ == "__main__":
    main()
