"""3D robot arm visualization using matplotlib."""

import matplotlib
import numpy as np

matplotlib.use("Agg")  # Non-interactive backend by default
import matplotlib.pyplot as plt
import roboticstoolbox as rtb

from src.kinematics.forward import solve_fk_all_joints


def plot_robot(
    robot: rtb.Robot,
    joint_angles: list[float],
    title: str | None = None,
    save_path: str | None = None,
    show: bool = False,
) -> str | None:
    """Plot the robot arm in 3D for a given joint configuration.

    Args:
        robot: Robot instance.
        joint_angles: Joint angles in radians.
        title: Plot title.
        save_path: If provided, save the figure to this path.
        show: If True, display the plot interactively.

    Returns:
        save_path if the figure was saved, else None.
    """
    frames = solve_fk_all_joints(robot, joint_angles)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    # Extract joint positions
    xs = [f["position"][0] for f in frames]
    ys = [f["position"][1] for f in frames]
    zs = [f["position"][2] for f in frames]

    # Plot links as lines
    ax.plot(xs, ys, zs, "o-", color="steelblue", linewidth=3, markersize=8, label="Links")

    # Highlight base
    ax.scatter([xs[0]], [ys[0]], [zs[0]], color="green", s=150, marker="^", label="Base", zorder=5)

    # Highlight end-effector
    ax.scatter([xs[-1]], [ys[-1]], [zs[-1]], color="red", s=150, marker="*", label="End-Effector", zorder=5)

    # Labels
    for i, f in enumerate(frames):
        label = f"J{i}" if f["joint_index"] != "end_effector" else "EE"
        ax.text(f["position"][0], f["position"][1], f["position"][2], f"  {label}", fontsize=8)

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title(title or f"{robot.name} - Robot Configuration")
    ax.legend()

    # Set equal aspect ratio
    all_coords = np.array([xs, ys, zs])
    max_range = (all_coords.max(axis=1) - all_coords.min(axis=1)).max() / 2
    mid = all_coords.mean(axis=1)
    ax.set_xlim(mid[0] - max_range, mid[0] + max_range)
    ax.set_ylim(mid[1] - max_range, mid[1] + max_range)
    ax.set_zlim(mid[2] - max_range, mid[2] + max_range)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return save_path

    if show:
        matplotlib.use("TkAgg")
        plt.show()
    else:
        plt.close(fig)

    return None


def plot_trajectory(
    robot: rtb.Robot,
    trajectory: list[list[float]],
    save_path: str | None = None,
    title: str | None = None,
) -> str | None:
    """Plot multiple robot configurations overlaid to show a trajectory.

    Args:
        robot: Robot instance.
        trajectory: List of joint angle configurations.
        save_path: If provided, save the figure.
        title: Plot title.
    """
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection="3d")

    n_configs = len(trajectory)
    colors = plt.cm.viridis(np.linspace(0, 1, n_configs))

    for idx, q in enumerate(trajectory):
        frames = solve_fk_all_joints(robot, q)
        xs = [f["position"][0] for f in frames]
        ys = [f["position"][1] for f in frames]
        zs = [f["position"][2] for f in frames]

        alpha = 0.3 + 0.7 * (idx / max(n_configs - 1, 1))
        ax.plot(xs, ys, zs, "o-", color=colors[idx], linewidth=2, markersize=5, alpha=alpha)

    # Highlight start and end
    start_frames = solve_fk_all_joints(robot, trajectory[0])
    end_frames = solve_fk_all_joints(robot, trajectory[-1])
    ax.scatter(
        [start_frames[-1]["position"][0]],
        [start_frames[-1]["position"][1]],
        [start_frames[-1]["position"][2]],
        color="green", s=200, marker="o", label="Start EE", zorder=5,
    )
    ax.scatter(
        [end_frames[-1]["position"][0]],
        [end_frames[-1]["position"][1]],
        [end_frames[-1]["position"][2]],
        color="red", s=200, marker="*", label="End EE", zorder=5,
    )

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title(title or f"{robot.name} - Trajectory ({n_configs} configs)")
    ax.legend()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return save_path

    plt.close(fig)
    return None
