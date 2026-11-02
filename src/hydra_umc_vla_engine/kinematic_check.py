# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/kinematic_check.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""The kinematic check of a trajectory: can the robot get to every pose of it, inside the limits of its joints?

A model predicts poses of the tool; nothing in its output says the arm can reach them. Before a trajectory is shown to the person who approves it, this check
asks the kinematics of HYDRA-UMC-PHYSICS-REPLICA (its `ik` command, which moves one frame to a point by damped least squares on the Jacobian and keeps every joint
inside the limits the URDF declares) whether each waypoint can be reached. The first waypoint starts from the joint positions of the configuration; each next one
starts from the joints that reached the one before, so the answer also says how far the joints have to turn between two waypoints, and a jump above
`max_joint_step` is refused as a motion no controller could follow smoothly.

What it checks is the position of the tool (the `ik` of PHYSICS-REPLICA is a position solver): the orientation of the poses is not checked here, and neither are the
collisions of the arm, which need the zones and a trajectory in joint space. The program is run as a child process, with a list of arguments (no shell), a time
limit and a limit on the number of waypoints; a waypoint the program cannot reach is `unreachable`; a program that is not there, that fails or that answers something
that cannot be read is `unavailable`, and with `fail_closed` (true unless the file says otherwise) no trajectory is offered then.

The whole thing is off unless the `kinematics` section of the configuration file says `"enabled": true`:

    {"kinematics": {"enabled": true, "command": ["physics-replica"], "urdf": "robot.urdf", "target_joint": "wrist",
                    "initial_joints": {"shoulder": 0.0, "elbow": 0.5}, "origin": [0.0, 0.0, 0.0], "tolerance_m": 0.002,
                    "max_iterations": 200, "max_joint_step": 0.5, "timeout_seconds": 10, "max_waypoints": 64, "fail_closed": true}}
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .trajectory import Pose

CONFIG_ENV = "HYDRA_UMC_VLA_ENGINE_CONFIG"
REACHABLE, UNREACHABLE, UNAVAILABLE = "reachable", "unreachable", "unavailable"
_KEYS = {"enabled", "command", "urdf", "target_joint", "initial_joints", "origin", "tolerance_m", "max_iterations", "max_joint_step", "timeout_seconds", "max_waypoints", "fail_closed"}
_NAME = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_PART = re.compile(r"[A-Za-z0-9_./:\\ -]{1,300}")
_LINE = re.compile(r"^([A-Za-z0-9_.:-]{1,64})=(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)$")


class KinematicsConfigError(ValueError):
    """The kinematics section of the configuration file cannot be used."""


@dataclass(frozen=True)
class KinematicsPolicy:
    enabled: bool = False
    command: tuple[str, ...] = ("physics-replica",)
    urdf: str = ""
    target_joint: str = ""
    initial_joints: dict[str, float] = field(default_factory=dict)
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    tolerance_m: float = 0.002
    max_iterations: int = 200
    max_joint_step: float = 0.5
    timeout_seconds: float = 10.0
    max_waypoints: int = 64
    fail_closed: bool = True

    def __post_init__(self) -> None:
        if not self.enabled:
            return
        if not self.urdf or not self.target_joint or not _NAME.fullmatch(self.target_joint):
            raise KinematicsConfigError("kinematics needs urdf and target_joint (a joint name of 1 to 64 plain characters)")
        if not self.command or any(not isinstance(c, str) or not _PART.fullmatch(c) for c in self.command) or len(self.command) > 4:
            raise KinematicsConfigError("kinematics.command is the program (and at most 3 leading arguments) as a list of plain texts")
        if any(not isinstance(n, str) or not _NAME.fullmatch(n) or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for n, v in self.initial_joints.items()):
            raise KinematicsConfigError("kinematics.initial_joints maps joint names to finite numbers")
        for name, value, low, high in (("tolerance_m", self.tolerance_m, 0.0, 1.0), ("max_joint_step", self.max_joint_step, 0.0, 7.0), ("timeout_seconds", self.timeout_seconds, 0.0, 120.0)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low < value <= high:
                raise KinematicsConfigError(f"kinematics.{name} must be a number above {low:g} and at most {high:g}")
        if isinstance(self.max_iterations, bool) or not isinstance(self.max_iterations, int) or not 1 <= self.max_iterations <= 10000:
            raise KinematicsConfigError("kinematics.max_iterations must be an integer from 1 to 10000")
        if isinstance(self.max_waypoints, bool) or not isinstance(self.max_waypoints, int) or not 1 <= self.max_waypoints <= 500:
            raise KinematicsConfigError("kinematics.max_waypoints must be an integer from 1 to 500")
        if not isinstance(self.fail_closed, bool):
            raise KinematicsConfigError("kinematics.fail_closed must be true or false")

    def describe(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "target_joint": self.target_joint, "tolerance_m": self.tolerance_m, "max_joint_step": self.max_joint_step,
                "max_waypoints": self.max_waypoints, "fail_closed": self.fail_closed}


def load_kinematics_policy(path: str | os.PathLike[str] | None = None) -> KinematicsPolicy:
    chosen = str(path) if path else os.environ.get(CONFIG_ENV, "")
    if not chosen:
        return KinematicsPolicy()
    try:
        data = json.loads(Path(chosen).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise KinematicsConfigError(f"cannot read the configuration file {chosen}: {error}") from error
    section = data.get("kinematics", {}) if isinstance(data, dict) else None
    if not isinstance(section, dict) or set(section) - _KEYS:
        raise KinematicsConfigError(f"{chosen} must hold a JSON object whose kinematics entry is an object with the keys {sorted(_KEYS)}")
    values = dict(section)
    base = Path(chosen).resolve().parent
    if "command" in values:
        if not isinstance(values["command"], list):
            raise KinematicsConfigError("kinematics.command must be a list")
        values["command"] = tuple(values["command"])
    if "origin" in values:
        origin = values["origin"]
        if not isinstance(origin, list) or len(origin) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in origin):
            raise KinematicsConfigError("kinematics.origin is a list of three finite numbers")
        values["origin"] = tuple(float(v) for v in origin)
    if "urdf" in values and isinstance(values["urdf"], str) and values["urdf"] and not Path(values["urdf"]).is_absolute():
        values["urdf"] = str(base / values["urdf"])  # the URDF is found next to the configuration file
    if "initial_joints" in values and not isinstance(values["initial_joints"], dict):
        raise KinematicsConfigError("kinematics.initial_joints must be an object")
    return KinematicsPolicy(**values)


Runner = Callable[[Sequence[str], float], "subprocess.CompletedProcess[str]"]


def _run(command: Sequence[str], timeout: float) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(list(command), capture_output=True, text=True, timeout=timeout, shell=False, check=False)


@dataclass
class KinematicResult:
    outcome: str  # reachable, unreachable or unavailable
    reasons: list[str] = field(default_factory=list)
    checked: int = 0
    failed_at_step: int | None = None
    max_joint_step: float = 0.0
    seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "reasons": self.reasons, "checked": self.checked, "failed_at_step": self.failed_at_step,
                "max_joint_step": round(self.max_joint_step, 6), "seconds": round(self.seconds, 3)}


def _joints_arg(joints: dict[str, float]) -> str:
    return ",".join(f"{name}={value:.9f}" for name, value in sorted(joints.items()))


def check_reach(poses: Sequence[Pose], policy: KinematicsPolicy, runner: Runner = _run, clock: Callable[[], float] = time.monotonic) -> KinematicResult:
    """Ask the kinematics whether every pose of the trajectory can be reached, one after the other."""
    started = clock()
    if len(poses) > policy.max_waypoints:
        return KinematicResult(UNAVAILABLE, [f"the trajectory has {len(poses)} poses and the check takes at most {policy.max_waypoints}"], 0, None, 0.0, clock() - started)
    joints = dict(policy.initial_joints)
    widest = 0.0
    for step, pose in enumerate(poses):
        goal = (pose.x + policy.origin[0], pose.y + policy.origin[1], pose.z + policy.origin[2])
        command = [*policy.command, "ik", "--urdf", policy.urdf, "--target", policy.target_joint, "--goal", ",".join(f"{v:.9f}" for v in goal),
                   "--tolerance", f"{policy.tolerance_m:g}", "--max-iterations", str(policy.max_iterations)]
        if joints:
            command += ["--joints", _joints_arg(joints)]
        try:
            done = runner(command, policy.timeout_seconds)
        except subprocess.TimeoutExpired:
            return KinematicResult(UNAVAILABLE, [f"the kinematics did not answer within {policy.timeout_seconds:g} s at step {step}"], step, step, widest, clock() - started)
        except OSError as error:
            return KinematicResult(UNAVAILABLE, [f"the kinematics program cannot be run: {error.strerror or type(error).__name__}"], step, step, widest, clock() - started)
        if done.returncode == 1:
            message = (done.stderr or "").strip().splitlines()[-1:] or ["no answer"]
            return KinematicResult(UNREACHABLE, [f"step {step} ({goal[0]:.3f}, {goal[1]:.3f}, {goal[2]:.3f}) cannot be reached: {message[0][:200]}"], step, step, widest, clock() - started)
        if done.returncode != 0:
            message = (done.stderr or "").strip().splitlines()[-1:] or [f"exit code {done.returncode}"]
            return KinematicResult(UNAVAILABLE, [f"the kinematics failed at step {step}: {message[0][:200]}"], step, step, widest, clock() - started)
        solved: dict[str, float] = {}
        for line in done.stdout.splitlines():
            match = _LINE.match(line.strip())
            if match:
                solved[match.group(1)] = float(match.group(2))
        if not solved or any(not math.isfinite(v) for v in solved.values()):
            return KinematicResult(UNAVAILABLE, [f"the kinematics answered nothing readable at step {step}"], step, step, widest, clock() - started)
        if joints:
            jump = max((abs(solved[name] - joints[name]) for name in solved if name in joints), default=0.0)
            widest = max(widest, jump)
            if jump > policy.max_joint_step:
                return KinematicResult(UNREACHABLE, [f"between step {step - 1} and step {step} a joint would turn {jump:.3f} rad, above {policy.max_joint_step:g}"], step, step, widest, clock() - started)
        joints = {**joints, **solved}
    return KinematicResult(REACHABLE, [], len(poses), None, widest, clock() - started)
