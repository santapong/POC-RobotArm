"""Open the interactive 3D simulator with joint sliders.

Run:
    python examples/demo_simulation.py
    python examples/demo_simulation.py --urdf franka_panda/panda.urdf
"""

from src.simulation.gui import main

if __name__ == "__main__":
    main()
