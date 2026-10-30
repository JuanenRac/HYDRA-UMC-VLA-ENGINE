# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/rotation_policy.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""How the rotation deltas of a trajectory are integrated, read from the configuration file.

`configs/vla-engine.json`:

    {"rotation": {"integration": "quaternion", "frame": "base"}}

* `integration`: "quaternion" (the delta is a rotation vector, axis times angle in
  radians, composed with the orientation exactly) or "euler" (the delta is added to
  the roll, pitch and yaw; the earlier behaviour, only right for small angles away
  from pitch +-90 degrees; obsolete, kept for installations that rely on it).
* `frame`: the frame the model's delta is expressed in. "base": the delta turns the
  tool about the axes of the robot base (`delta * current`); "tool": about the axes
  of the end effector (`current * delta`). It must be the one the model was trained
  with.

The file is the one given with `--config` or named by HYDRA_UMC_VLA_ENGINE_CONFIG;
without either the defaults apply (quaternion, base).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

INTEGRATION_MODES = ("quaternion", "euler")
FRAMES = ("base", "tool")
CONFIG_ENV = "HYDRA_UMC_VLA_ENGINE_CONFIG"


class RotationConfigError(ValueError):
    """The configuration file cannot be used."""


@dataclass(frozen=True)
class RotationPolicy:
    integration: str = "quaternion"
    frame: str = "base"

    def __post_init__(self) -> None:
        if self.integration not in INTEGRATION_MODES:
            raise RotationConfigError(f"rotation.integration must be one of {', '.join(INTEGRATION_MODES)}, got {self.integration!r}")
        if self.frame not in FRAMES:
            raise RotationConfigError(f"rotation.frame must be one of {', '.join(FRAMES)}, got {self.frame!r}")


def load_rotation_policy(path: str | os.PathLike[str] | None = None) -> RotationPolicy:
    chosen = str(path) if path else os.environ.get(CONFIG_ENV, "")
    if not chosen:
        return RotationPolicy()
    try:
        data = json.loads(Path(chosen).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RotationConfigError(f"cannot read the configuration file {chosen}: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("rotation", {}), dict):
        raise RotationConfigError(f"{chosen} must hold a JSON object with a rotation object")
    section = data.get("rotation", {})
    values = {}
    for key in ("integration", "frame"):
        if key in section:
            if not isinstance(section[key], str):
                raise RotationConfigError(f"rotation.{key} must be text")
            values[key] = section[key].strip().lower()
    return RotationPolicy(**values)


# The policy that integrate_trajectory and the guard use when the caller gives none. The service sets it once at start from its
# configuration file; it is never changed while requests are being served.
_active = RotationPolicy()


def active_policy() -> RotationPolicy:
    return _active


def set_active_policy(policy: RotationPolicy) -> None:
    global _active
    _active = policy
