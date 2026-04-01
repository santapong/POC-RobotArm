"""Demo: Interactive LLM chat for robot arm kinematics.

This script starts an interactive chat session where you can ask
natural language questions about robot kinematics.

Requires Ollama to be running with a model installed.
Setup:
    1. Install Ollama: https://ollama.ai
    2. Pull a model: ollama pull llama3.1
    3. Run this script: python examples/demo_llm_chat.py
"""

from src.llm.agent import RobotArmAgent


def main():
    print("=" * 60)
    print("Robot Arm LLM Chat Demo")
    print("=" * 60)
    print()
    print("Example queries:")
    print('  "What robots are available?"')
    print('  "Compute FK for Panda with all joints at zero"')
    print('  "Find joint angles to move the Panda to position 0.5, 0, 0.5"')
    print('  "Plot the UR5 at angles 0, -1.57, 1.57, 0, 0, 0"')
    print()

    agent = RobotArmAgent()

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

        response = agent.process(user_input)
        print(f"\nAssistant > {response}\n")


if __name__ == "__main__":
    main()
