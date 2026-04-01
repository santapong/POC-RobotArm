# POC-RobotArm

Robotics Kinematics Solver with LLM Interface - A proof-of-concept for solving Forward Kinematics (FK) and Inverse Kinematics (IK) for robot arms, with a natural language interface powered by a local LLM (Ollama).

## Features

- **Forward Kinematics (FK)**: Compute end-effector position/orientation from joint angles
- **Inverse Kinematics (IK)**: Find joint angles to reach a target pose (Levenberg-Marquardt, Newton-Raphson, Gauss-Newton)
- **Predefined Robots**: Franka Emika Panda (7-DOF), Universal Robots UR5 (6-DOF)
- **Custom Robots**: Define your own robot arm using DH parameters
- **3D Visualization**: Matplotlib-based arm plotting and trajectory visualization
- **LLM Chat Interface**: Ask questions in natural language via Ollama (local LLM)
- **Direct Command Mode**: Works without LLM as a CLI tool

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# (Optional) Install Ollama for LLM features
# https://ollama.ai
# Then pull a model:
ollama pull llama3.1
```

## Usage

### Interactive Mode (with LLM)
```bash
python -m src.main
```

Example queries:
- "What is the end-effector position of the Panda at joint angles all zeros?"
- "Find joint angles to reach position (0.5, 0, 0.5) with the Panda"
- "List available robots"
- "Plot the UR5 at angles 0, -1.57, 1.57, 0, 0, 0"

### Direct Command Mode (no LLM needed)
```bash
python -m src.main --no-llm
```

Commands:
```
list                          - List available robots
info <robot>                  - Get robot details
fk <robot> <angles...>        - Forward kinematics
ik <robot> <x> <y> <z>        - Inverse kinematics
plot <robot> <angles...>       - Visualize robot
```

### Python API
```python
from src.robots.predefined import get_panda
from src.kinematics.forward import solve_fk
from src.kinematics.inverse import solve_ik

# Forward Kinematics
panda = get_panda()
result = solve_fk(panda, [0, -0.3, 0, -2.2, 0, 2.0, 0.79])
print(result["position"])  # [x, y, z]

# Inverse Kinematics
ik_result = solve_ik(panda, [0.5, 0.0, 0.5])
print(ik_result["joint_angles"])
```

### Run Examples
```bash
python examples/demo_fk.py    # Forward kinematics demo
python examples/demo_ik.py    # Inverse kinematics demo
python examples/demo_llm_chat.py  # LLM chat demo
```

## Testing

```bash
pytest tests/ -v
```

## Project Structure

```
src/
├── robots/          # Robot model definitions (Panda, UR5, custom)
├── kinematics/      # FK and IK solvers
├── visualization/   # 3D plotting
├── llm/             # Ollama LLM agent with tool calling
└── main.py          # CLI entry point
```

## Tech Stack

- [roboticstoolbox-python](https://github.com/petercorke/robotics-toolbox-python) - FK/IK engine
- [Ollama](https://ollama.ai) - Local LLM for natural language interface
- numpy, scipy, matplotlib
