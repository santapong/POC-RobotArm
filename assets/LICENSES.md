# Asset Licenses

## `urdf/ur5/ur5.urdf`

Hand-written URDF using **primitive shapes** (cylinders, boxes) and the
publicly-documented Universal Robots UR5 DH parameters
(a, d, alpha values from the UR5 datasheet).

- No upstream meshes are vendored. The visualization is a primitive-shape
  approximation; the kinematic chain matches the official UR5.
- Authored for this project; released under the same license as the rest
  of the repository.
- DH parameters are public information; their inclusion in a URDF does
  not create a derivative-work obligation.

## `urdf/iiwa/`, `franka_panda/`

Loaded via PyBullet's bundled ``pybullet_data`` directory. See the
[bullet3 repository](https://github.com/bulletphysics/bullet3) for those
models' upstream licenses (Zlib for bullet3 itself; individual robot
models retain their original licenses).
