# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/guard.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""The trajectory guard: what a model's trajectory must satisfy before anyone is asked to approve it.

A VLA model predicts deltas, and `integrate_trajectory` accumulates them. Nothing in a model's output says the tool stays in the cell, moves at
a speed the machine can follow, or keeps away from a person's zone. The guard puts that on the trajectory itself, with limits that come from the
cell and not from the model:

  * a work volume (an axis-aligned box) the tool must stay in;
  * a longest step, in meters and in radians, and an optional limit on how much a step may differ from the one before it;
  * the zones of HYDRA-UMC-SAFETY-ZONES, in the same JSON (`{"zones": [{"id", "level", "min", "max"}]}`): a step that enters or crosses a
    `danger` zone rejects the trajectory, and a step inside a `warning` zone is held to a fraction of the longest step;
  * the range of the gripper.

The outcome is one of three: `ok` (the trajectory is as it came), `clamped` (a step was longer than allowed, or left the volume, and was
cut back; the later steps are re-integrated from the cut point, so the trajectory is still continuous), or `rejected` (a rule that cannot be
met by cutting back was broken: a danger zone, a value that is not a number, a gripper out of range). A rejected trajectory has no poses. The
guard does not authorize anything: it only decides whether a proposal is worth showing to whoever approves.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .rotation import Quaternion
from .rotation_policy import active_policy
from .trajectory import Pose, compose_rotation, pose_with_orientation

OK = "ok"
CLAMPED = "clamped"
REJECTED = "rejected"


class GuardConfigError(ValueError):
    """The guard file cannot be used."""


Vec = tuple[float, float, float]

# A step is the difference of two integrated poses, so a step that is exactly at a limit can come out a few ulps over it: that is not a violation.
_TOLERANCE = 1.0 + 1e-9


@dataclass(frozen=True)
class Box:
    low: Vec
    high: Vec

    def contains(self, p: Vec) -> bool:
        return all(self.low[i] <= p[i] <= self.high[i] for i in range(3))

    def clamp(self, p: Vec) -> Vec:
        return (min(max(p[0], self.low[0]), self.high[0]), min(max(p[1], self.low[1]), self.high[1]), min(max(p[2], self.low[2]), self.high[2]))

    def crossed_by(self, a: Vec, b: Vec) -> bool:
        """Whether the segment from a to b touches the box (the slab method)."""
        t0, t1 = 0.0, 1.0
        for i in range(3):
            d = b[i] - a[i]
            if abs(d) < 1e-15:
                if a[i] < self.low[i] or a[i] > self.high[i]:
                    return False
                continue
            near, far = (self.low[i] - a[i]) / d, (self.high[i] - a[i]) / d
            if near > far:
                near, far = far, near
            t0, t1 = max(t0, near), min(t1, far)
            if t0 > t1:
                return False
        return True


@dataclass(frozen=True)
class GuardZone:
    zone_id: str
    level: str  # "warning" or "danger"
    box: Box


@dataclass(frozen=True)
class GuardLimits:
    workspace: Box
    max_linear_step: float
    max_angular_step: float
    max_linear_step_change: float | None = None
    gripper_min: float = 0.0
    gripper_max: float = 1.0
    warning_step_factor: float = 0.5
    zones: tuple[GuardZone, ...] = ()


@dataclass
class GuardResult:
    outcome: str
    poses: list[Pose] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    rejected_at_step: int | None = None

    def as_dict(self) -> dict:
        return {"outcome": self.outcome, "reasons": self.reasons, "rejected_at_step": self.rejected_at_step}


# ---- configuration ----


def _number(raw: object, label: str, *, positive: bool = False) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise GuardConfigError(f"{label} must be a finite number, got {raw!r}")
    if positive and raw <= 0:
        raise GuardConfigError(f"{label} must be greater than 0, got {raw!r}")
    return float(raw)


def _vec(raw: object, label: str) -> Vec:
    if not isinstance(raw, dict) or set(raw) != {"x", "y", "z"}:
        raise GuardConfigError(f"{label} must be an object with x, y and z")
    return (_number(raw["x"], f"{label}.x"), _number(raw["y"], f"{label}.y"), _number(raw["z"], f"{label}.z"))


def _box(raw: object, label: str) -> Box:
    if not isinstance(raw, dict) or "min" not in raw or "max" not in raw:
        raise GuardConfigError(f"{label} needs min and max")
    low, high = _vec(raw["min"], f"{label}.min"), _vec(raw["max"], f"{label}.max")
    if any(low[i] > high[i] for i in range(3)):
        raise GuardConfigError(f"{label}: min is above max")
    return Box(low, high)


def parse_limits(raw: object) -> GuardLimits:
    if not isinstance(raw, dict):
        raise GuardConfigError("the guard file must be a JSON object")
    for key in ("workspace", "max_linear_step_m", "max_angular_step_rad"):
        if key not in raw:
            raise GuardConfigError(f"the guard file needs {key}")
    gripper = raw.get("gripper", {"min": 0.0, "max": 1.0})
    if not isinstance(gripper, dict):
        raise GuardConfigError("gripper must be an object with min and max")
    gripper_min, gripper_max = _number(gripper.get("min", 0.0), "gripper.min"), _number(gripper.get("max", 1.0), "gripper.max")
    if gripper_min > gripper_max:
        raise GuardConfigError("gripper: min is above max")
    factor = _number(raw.get("warning_step_factor", 0.5), "warning_step_factor", positive=True)
    if factor > 1.0:
        raise GuardConfigError("warning_step_factor must not be above 1")
    change = raw.get("max_linear_step_change_m")
    zones: list[GuardZone] = []
    seen: set[str] = set()
    entries = raw.get("zones", [])
    if not isinstance(entries, list):
        raise GuardConfigError("zones must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise GuardConfigError("each zone must be an object")
        zone_id, level = entry.get("id"), entry.get("level")
        if not isinstance(zone_id, str) or not zone_id or zone_id in seen:
            raise GuardConfigError(f"zone id {zone_id!r} is missing or used twice")
        if level not in ("warning", "danger"):
            raise GuardConfigError(f"zone {zone_id!r}: level must be warning or danger")
        seen.add(zone_id)
        zones.append(GuardZone(zone_id, level, _box(entry, f"zone {zone_id!r}")))
    return GuardLimits(
        workspace=_box(raw["workspace"], "workspace"),
        max_linear_step=_number(raw["max_linear_step_m"], "max_linear_step_m", positive=True),
        max_angular_step=_number(raw["max_angular_step_rad"], "max_angular_step_rad", positive=True),
        max_linear_step_change=None if change is None else _number(change, "max_linear_step_change_m", positive=True),
        gripper_min=gripper_min,
        gripper_max=gripper_max,
        warning_step_factor=factor,
        zones=tuple(zones),
    )


def load_limits(path: str | Path) -> GuardLimits:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=lambda name: (_ for _ in ()).throw(GuardConfigError(f"{name} is not a number")))
    except OSError as error:
        raise GuardConfigError(f"cannot read the guard file: {error}") from error
    except json.JSONDecodeError as error:
        raise GuardConfigError(f"the guard file is not JSON: {error}") from error
    return parse_limits(raw)


# ---- the guard ----


def _wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _angle_diff(a: float, b: float) -> float:
    return _wrap(a - b)


def guard_trajectory(poses: list[Pose], limits: GuardLimits) -> GuardResult:
    """Checks (and, where it can, cuts back) a trajectory whose first pose is where the tool is now."""
    if not poses:
        return GuardResult(REJECTED, reasons=["the trajectory has no poses"], rejected_at_step=0)
    start = poses[0]
    here: Vec = (start.x, start.y, start.z)
    if not limits.workspace.contains(here):
        return GuardResult(REJECTED, reasons=["the tool starts outside the work volume"], rejected_at_step=0)
    for zone in limits.zones:
        if zone.level == "danger" and zone.box.contains(here):
            return GuardResult(REJECTED, reasons=[f"the tool starts inside the danger zone {zone.zone_id!r}"], rejected_at_step=0)
    if not limits.gripper_min <= start.gripper <= limits.gripper_max:
        return GuardResult(REJECTED, reasons=["the gripper of the first pose is out of range"], rejected_at_step=0)

    out = [start]
    reasons: list[str] = []
    previous_step: Vec = (0.0, 0.0, 0.0)
    for index in range(1, len(poses)):
        wanted = poses[index]
        before = out[-1]
        if not limits.gripper_min <= wanted.gripper <= limits.gripper_max:
            return GuardResult(REJECTED, reasons=reasons + [f"step {index}: the gripper {wanted.gripper} is out of its range"], rejected_at_step=index)
        # the delta the model asked for, taken from the poses it integrated
        raw = (wanted.x - poses[index - 1].x, wanted.y - poses[index - 1].y, wanted.z - poses[index - 1].z)
        policy = active_policy()
        if policy.integration == "quaternion":
            # the turn the model asked for, as a rotation vector in the declared frame
            previous_q, wanted_q = poses[index - 1].quaternion, wanted.quaternion
            relative = wanted_q * previous_q.conjugate() if policy.frame == "base" else previous_q.conjugate() * wanted_q
            angular = relative.to_rotation_vector()
        else:
            angular = (
                _angle_diff(wanted.roll, poses[index - 1].roll),
                _angle_diff(wanted.pitch, poses[index - 1].pitch),
                _angle_diff(wanted.yaw, poses[index - 1].yaw),
            )
        step: Vec = raw
        notes: list[str] = []

        # the longest step, shorter in a warning zone
        cap = limits.max_linear_step
        in_warning = any(z.level == "warning" and z.box.contains((before.x, before.y, before.z)) for z in limits.zones)
        if in_warning:
            cap *= limits.warning_step_factor
        length = math.hypot(*step)
        if length > cap * _TOLERANCE:
            scale = cap / length
            step = (step[0] * scale, step[1] * scale, step[2] * scale)
            notes.append(f"step {index}: the move of {length:.4f} m was cut to {cap:.4f} m" + (" (inside a warning zone)" if in_warning else ""))
        # how much the step may change from the one before
        if limits.max_linear_step_change is not None:
            change = (step[0] - previous_step[0], step[1] - previous_step[1], step[2] - previous_step[2])
            size = math.hypot(*change)
            if size > limits.max_linear_step_change * _TOLERANCE:
                scale = limits.max_linear_step_change / size
                step = (previous_step[0] + change[0] * scale, previous_step[1] + change[1] * scale, previous_step[2] + change[2] * scale)
                notes.append(f"step {index}: the step changed by {size:.4f} m, cut to {limits.max_linear_step_change:.4f} m")
        angle_size = math.hypot(*angular)
        if angle_size > limits.max_angular_step * _TOLERANCE:
            scale = limits.max_angular_step / angle_size
            angular = (angular[0] * scale, angular[1] * scale, angular[2] * scale)
            notes.append(f"step {index}: the turn of {angle_size:.4f} rad was cut to {limits.max_angular_step:.4f} rad")

        target: Vec = (before.x + step[0], before.y + step[1], before.z + step[2])
        if not limits.workspace.contains(target):
            clamped = limits.workspace.clamp(target)
            notes.append(f"step {index}: the tool would leave the work volume, held at its edge")
            target = clamped
        # the zones: the whole segment, not only where it ends
        for zone in limits.zones:
            if zone.level == "danger" and zone.box.crossed_by((before.x, before.y, before.z), target):
                return GuardResult(REJECTED, reasons=reasons + notes + [f"step {index}: the move enters the danger zone {zone.zone_id!r}"], rejected_at_step=index)
        actual_step = (target[0] - before.x, target[1] - before.y, target[2] - before.z)
        if notes:
            reasons.extend(notes)
        previous_step = actual_step
        if policy.integration == "quaternion":
            out.append(pose_with_orientation(
                target[0], target[1], target[2], compose_rotation(before.quaternion, angular, policy), wanted.gripper,
            ))
            continue
        out.append(Pose(
            x=target[0], y=target[1], z=target[2],
            roll=_wrap(before.roll + angular[0]), pitch=_wrap(before.pitch + angular[1]), yaw=_wrap(before.yaw + angular[2]),
            gripper=wanted.gripper,
        ))
    return GuardResult(CLAMPED if reasons else OK, poses=out, reasons=reasons)
