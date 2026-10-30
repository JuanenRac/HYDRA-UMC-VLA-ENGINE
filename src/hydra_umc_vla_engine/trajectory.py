# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/trajectory.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Trajectory generation: the "Trajectory Generator" step in the VLA flow.

A VLA model predicts one action *delta* per inference step, not an
absolute target pose - turning a sequence of those deltas into the
absolute pose sequence the motor commands need is a fixed integration
problem (cumulative sum for pose, last-value for gripper state), separate
from running the model or the Hailo-10 NPU that would produce the deltas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from .action_tokens import ActionSpec, VLA_ACTION_SPACE
from .rotation import Quaternion
from .rotation_policy import RotationPolicy, active_policy


class TrajectoryError(ValueError):
    """Raised for a malformed start pose or action sequence."""


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float
    roll: float
    pitch: float
    yaw: float
    gripper: float
    # The orientation as a unit quaternion, when the pose comes from a rotation that was composed; roll, pitch and
    # yaw are then derived from it. Without one it is made from the angles.
    orientation: Quaternion | None = field(default=None, compare=False, repr=False)

    @property
    def quaternion(self) -> Quaternion:
        if self.orientation is not None:
            return self.orientation
        return Quaternion.from_euler(self.roll, self.pitch, self.yaw)


def compose_rotation(current: Quaternion, delta: tuple[float, float, float], policy: RotationPolicy) -> Quaternion:
    """The orientation after turning by `delta` (a rotation vector in radians) in the declared frame."""
    turn = Quaternion.from_rotation_vector(delta)
    return (turn * current if policy.frame == "base" else current * turn).normalized()


def pose_with_orientation(x: float, y: float, z: float, orientation: Quaternion, gripper: float) -> Pose:
    roll, pitch, yaw = orientation.to_euler()
    return Pose(x, y, z, roll, pitch, yaw, gripper, orientation)


# Most steps one trajectory may have, and how far past a spec bound a delta
# may be (a decoded token is always inside it; this only absorbs rounding).
MAX_STEPS = 1000
_BOUND_TOLERANCE = 1e-9


def _require_within(value: float, spec: ActionSpec, label: str) -> float:
    """Model output is never trusted to respect the action space: a delta outside
    the bounds the model was trained on is rejected, not integrated."""
    if value < spec.min - _BOUND_TOLERANCE or value > spec.max + _BOUND_TOLERANCE:
        raise TrajectoryError(f"{label}: {value} is outside the action space [{spec.min}, {spec.max}] for {spec.name}")
    return value


def _require_finite(value: object, label: str) -> float:
    """Return a safe numeric coordinate or reject malformed model output."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrajectoryError(f"{label}: expected a number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise TrajectoryError(f"{label}: value must be finite")
    return numeric


def _wrap_angle(value: float) -> float:
    """Normalize an angle to (-pi, pi] - found while auditing the code:
    this repo's own angle accumulation had no
    wraparound, unlike sibling HYDRA-UMC-VISUAL-SERVOING-API's own
    shortest-turn wrapping (servo.py's `_wrap_angle_diff`). A long action
    sequence (continuous wrist rotation) would otherwise hand a downstream
    motor an ever-growing raw radian value instead of the canonical
    representation of the same physical orientation."""
    return math.atan2(math.sin(value), math.cos(value))


def integrate_trajectory(
    start: Pose,
    actions: list[tuple[float, ...]],
    specs: tuple[ActionSpec, ...] = VLA_ACTION_SPACE,
    rotation: RotationPolicy | None = None,
) -> list[Pose]:
    """Turn a sequence of decoded 7-DOF actions into a sequence of poses.

    The first 6 dimensions (dx..dyaw) are deltas, accumulated onto the
    running pose. The 7th (gripper) is an absolute open/close command per
    the action space's own convention (see action_tokens.py), so it's
    taken as-is at each step rather than accumulated - summing gripper
    deltas would make the gripper drift further open/closed with every
    inference step even when the model keeps predicting "no change".

    The three rotation deltas are composed with the orientation as a rotation
    vector (axis times angle, radians) in the declared frame, not added to the
    roll, pitch and yaw; the configuration (see rotation_policy.py) can still ask
    for the earlier addition of angles, which is only right for small angles
    away from pitch +-90 degrees.
    """
    policy = rotation if rotation is not None else active_policy()
    if len(specs) != 7:
        raise TrajectoryError(f"integrate_trajectory expects a 7-DOF action space, got {len(specs)}")

    start_values = (start.x, start.y, start.z, start.roll, start.pitch, start.yaw, start.gripper)
    for label, value in zip(("start.x", "start.y", "start.z", "start.roll", "start.pitch", "start.yaw", "start.gripper"), start_values):
        _require_finite(value, label)

    if len(actions) > MAX_STEPS:
        raise TrajectoryError(f"actions: {len(actions)} steps exceed the limit of {MAX_STEPS}")

    poses = [start]
    current = start
    for step, action in enumerate(actions):
        if len(action) != 7:
            raise TrajectoryError(f"action {step}: expected 7 values (6 deltas + gripper), got {len(action)}")
        dx, dy, dz, droll, dpitch, dyaw, gripper = (
            _require_finite(value, f"action {step}[{index}]")
            for index, value in enumerate(action)
        )
        for index, (value, spec) in enumerate(zip(
            (dx, dy, dz, droll, dpitch, dyaw, gripper), specs, strict=True
        )):
            _require_within(value, spec, f"action {step}[{index}]")
        # _require_finite above only ever checked the RAW inputs
        # (start's own fields, each action's own 7 values) - two
        # perfectly finite values (e.g. start.x=1e308, dx=1e308) can
        # still silently overflow to inf when ACCUMULATED (float + never
        # raises on overflow, unlike float ** 2), and that was never
        # re-checked before being appended to the trajectory. Checked on
        # the raw sums BEFORE _wrap_angle - an already-infinite angle
        # would otherwise reach math.sin/cos there and raise a raw,
        # unlabeled "math domain error" instead of this same clear,
        # consistent message every other field gets. Raising here (not
        # returning whatever was integrated so far) rejects the whole
        # sequence atomically: no caller ever sees a trajectory
        # truncated partway through, and the FIRST step that actually
        # overflows is the one named in the error.
        new_x = _require_finite(current.x + dx, f"pose after action {step}.x")
        new_y = _require_finite(current.y + dy, f"pose after action {step}.y")
        new_z = _require_finite(current.z + dz, f"pose after action {step}.z")
        new_roll = _require_finite(current.roll + droll, f"pose after action {step}.roll")
        new_pitch = _require_finite(current.pitch + dpitch, f"pose after action {step}.pitch")
        new_yaw = _require_finite(current.yaw + dyaw, f"pose after action {step}.yaw")
        if policy.integration == "quaternion":
            current = pose_with_orientation(new_x, new_y, new_z, compose_rotation(current.quaternion, (droll, dpitch, dyaw), policy), gripper)
        else:
            current = Pose(
                x=new_x, y=new_y, z=new_z,
                roll=_wrap_angle(new_roll),
                pitch=_wrap_angle(new_pitch),
                yaw=_wrap_angle(new_yaw),
                gripper=gripper,
            )
        poses.append(current)
    return poses
