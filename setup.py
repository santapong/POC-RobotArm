from setuptools import setup, find_packages

setup(
    name="poc-robotarm",
    version="0.1.0",
    description="Robotics Kinematics Solver with LLM Interface",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "roboticstoolbox-python>=1.1.0",
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "spatialmath-python>=1.1.0",
        "matplotlib>=3.7.0",
        "ollama>=0.4.0",
    ],
    entry_points={
        "console_scripts": [
            "robotarm=src.main:main",
        ],
    },
)
