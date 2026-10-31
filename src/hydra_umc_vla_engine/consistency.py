# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/consistency.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Consistency filter: a trajectory is not offered when the model's repeated predictions disagree.

`configs/vla-engine.json`:

    {"consistency": {"predictions": 3, "tolerance": {"linear": 0.005, "rotation": 0.01, "gripper": 0.1}}}

* `predictions`: how many predictions of the same step must agree. 1 (the default) turns the
  filter off. When it is N above 1 the request must carry `alternatives`: N-1 further action
  sequences, each as long as `actions`; a request without them is refused (fail closed).
* `tolerance`: the largest difference two predictions of the same value may have to count as
  the same (linear in metres, rotation in radians, gripper in the 0 to 1 range).

The file is the one given with `--config` or named by HYDRA_UMC_VLA_ENGINE_CONFIG.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_ENV = "HYDRA_UMC_VLA_ENGINE_CONFIG"
MAX_PREDICTIONS = 16
_GROUPS = ("linear", "rotation", "gripper")
_DEFAULT_TOLERANCE = {"linear": 0.005, "rotation": 0.01, "gripper": 0.1}


class ConsistencyConfigError(ValueError):
    """The configuration file or the alternative predictions of a request cannot be used."""


def _tolerance_default() -> dict[str, float]:
    return dict(_DEFAULT_TOLERANCE)


@dataclass(frozen=True)
class ConsistencyPolicy:
    predictions: int = 1
    tolerance: dict[str, float] = field(default_factory=_tolerance_default)

    def __post_init__(self) -> None:
        if isinstance(self.predictions, bool) or not isinstance(self.predictions, int) or not 1 <= self.predictions <= MAX_PREDICTIONS:
            raise ConsistencyConfigError(f"consistency.predictions must be an integer from 1 to {MAX_PREDICTIONS}, got {self.predictions!r}")
        if not isinstance(self.tolerance, dict) or set(self.tolerance) != set(_GROUPS):
            raise ConsistencyConfigError(f"consistency.tolerance must hold exactly {', '.join(_GROUPS)}")
        for name, value in self.tolerance.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ConsistencyConfigError(f"consistency.tolerance.{name} must be a number that is not negative, got {value!r}")

    @property
    def enabled(self) -> bool:
        return self.predictions > 1


def load_consistency_policy(path: str | os.PathLike[str] | None = None) -> ConsistencyPolicy:
    chosen = str(path) if path else os.environ.get(CONFIG_ENV, "")
    if not chosen:
        return ConsistencyPolicy()
    try:
        data = json.loads(Path(chosen).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConsistencyConfigError(f"cannot read the configuration file {chosen}: {error}") from error
    section = data.get("consistency", {}) if isinstance(data, dict) else None
    if not isinstance(section, dict):
        raise ConsistencyConfigError(f"{chosen} must hold a JSON object whose consistency entry is an object")
    kwargs: dict[str, object] = {}
    if "predictions" in section:
        kwargs["predictions"] = section["predictions"]
    if "tolerance" in section:
        given = section["tolerance"]
        if not isinstance(given, dict):
            raise ConsistencyConfigError("consistency.tolerance must be an object")
        kwargs["tolerance"] = {**_DEFAULT_TOLERANCE, **given}
    return ConsistencyPolicy(**kwargs)  # type: ignore[arg-type]


def _group(index: int) -> str:
    return "linear" if index < 3 else "rotation" if index < 6 else "gripper"


def inconsistent_steps(actions: list[tuple[float, ...]], alternatives: object, policy: ConsistencyPolicy) -> list[int]:
    """Indices of the steps where an alternative prediction differs from `actions` by more than the tolerance.

    Raises when the filter is on and the alternatives are missing or malformed (fail closed)."""
    if not policy.enabled:
        return []
    needed = policy.predictions - 1
    if not isinstance(alternatives, list) or len(alternatives) != needed:
        raise ConsistencyConfigError(f"alternatives: expected {needed} further action sequence(s) because {policy.predictions} consistent predictions are configured")
    bad: set[int] = set()
    for which, sequence in enumerate(alternatives):
        if not isinstance(sequence, list) or len(sequence) != len(actions):
            raise ConsistencyConfigError(f"alternatives[{which}]: expected {len(actions)} actions, as many as actions")
        for step, (mine, other) in enumerate(zip(actions, sequence, strict=False)):
            if not isinstance(other, (list, tuple)) or len(other) != len(mine):
                raise ConsistencyConfigError(f"alternatives[{which}][{step}]: expected {len(mine)} numbers")
            for index, (a, b) in enumerate(zip(mine, other, strict=False)):
                if isinstance(b, bool) or not isinstance(b, (int, float)) or not math.isfinite(b):
                    raise ConsistencyConfigError(f"alternatives[{which}][{step}][{index}] must be a finite number, got {b!r}")
                if abs(a - b) > policy.tolerance[_group(index)]:
                    bad.add(step)
    return sorted(bad)
