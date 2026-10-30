# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/confidence.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Confidence filter: a trajectory is not offered when the model was not sure of one of its actions.

`configs/vla-engine.json`:

    {"confidence": {"minimum": 0.6}}

* `minimum`: the lowest confidence (0 to 1) an action may have. 0 (the default) turns the
  filter off. When it is above 0 the request must carry one confidence per action; a
  request without them is refused rather than let through (fail closed).

The file is the one given with `--config` or named by HYDRA_UMC_VLA_ENGINE_CONFIG.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_ENV = "HYDRA_UMC_VLA_ENGINE_CONFIG"


class ConfidenceConfigError(ValueError):
    """The configuration file or the confidences of a request cannot be used."""


@dataclass(frozen=True)
class ConfidencePolicy:
    minimum: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.minimum, bool) or not isinstance(self.minimum, (int, float)) or not math.isfinite(self.minimum) or not 0.0 <= self.minimum <= 1.0:
            raise ConfidenceConfigError(f"confidence.minimum must be a number from 0 to 1, got {self.minimum!r}")

    @property
    def enabled(self) -> bool:
        return self.minimum > 0.0


def load_confidence_policy(path: str | os.PathLike[str] | None = None) -> ConfidencePolicy:
    chosen = str(path) if path else os.environ.get(CONFIG_ENV, "")
    if not chosen:
        return ConfidencePolicy()
    try:
        data = json.loads(Path(chosen).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfidenceConfigError(f"cannot read the configuration file {chosen}: {error}") from error
    section = data.get("confidence", {}) if isinstance(data, dict) else None
    if not isinstance(section, dict):
        raise ConfidenceConfigError(f"{chosen} must hold a JSON object whose confidence entry is an object")
    return ConfidencePolicy(**({"minimum": section["minimum"]} if "minimum" in section else {}))


def low_confidence_steps(confidences: object, step_count: int, policy: ConfidencePolicy) -> list[int]:
    """Indices of the actions below the minimum. Raises when the filter is on and the confidences are missing or malformed."""
    if not policy.enabled:
        return []
    if not isinstance(confidences, list) or len(confidences) != step_count:
        raise ConfidenceConfigError(f"confidences: expected one number per action ({step_count}) because a minimum confidence is configured")
    low: list[int] = []
    for index, value in enumerate(confidences):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ConfidenceConfigError(f"confidences[{index}] must be a number from 0 to 1, got {value!r}")
        if value < policy.minimum:
            low.append(index)
    return low
