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

from dataclasses import dataclass
import math

from .action_tokens import ActionSpec, VLA_ACTION_SPACE


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


def _require_finite(value: object, label: str) -> float:
    """Return a safe numeric coordinate or reject malformed model output."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrajectoryError(f"{label}: expected a number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise TrajectoryError(f"{label}: value must be finite")
    return numeric


def integrate_trajectory(
    start: Pose,
    actions: list[tuple[float, ...]],
    specs: tuple[ActionSpec, ...] = VLA_ACTION_SPACE,
) -> list[Pose]:
    """Turn a sequence of decoded 7-DOF actions into a sequence of poses.

    The first 6 dimensions (dx..dyaw) are deltas, accumulated onto the
    running pose. The 7th (gripper) is an absolute open/close command per
    the action space's own convention (see action_tokens.py), so it's
    taken as-is at each step rather than accumulated - summing gripper
    deltas would make the gripper drift further open/closed with every
    inference step even when the model keeps predicting "no change".
    """
    if len(specs) != 7:
        raise TrajectoryError(f"integrate_trajectory expects a 7-DOF action space, got {len(specs)}")

    start_values = (start.x, start.y, start.z, start.roll, start.pitch, start.yaw, start.gripper)
    for label, value in zip(("start.x", "start.y", "start.z", "start.roll", "start.pitch", "start.yaw", "start.gripper"), start_values):
        _require_finite(value, label)

    poses = [start]
    current = start
    for step, action in enumerate(actions):
        if len(action) != 7:
            raise TrajectoryError(f"action {step}: expected 7 values (6 deltas + gripper), got {len(action)}")
        dx, dy, dz, droll, dpitch, dyaw, gripper = (
            _require_finite(value, f"action {step}[{index}]")
            for index, value in enumerate(action)
        )
        current = Pose(
            x=current.x + dx, y=current.y + dy, z=current.z + dz,
            roll=current.roll + droll, pitch=current.pitch + dpitch, yaw=current.yaw + dyaw,
            gripper=gripper,
        )
        poses.append(current)
    return poses
