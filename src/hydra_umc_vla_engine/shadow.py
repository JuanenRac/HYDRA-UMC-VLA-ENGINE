# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/shadow.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Shadow mode: compare what the model proposes with what the operator did, and move nothing.

`configs/vla-engine.json`:

    {"shadow": {"enabled": false, "log_file": ""}}

* `enabled`: turns on `POST /shadow/compare` (off by default; the route answers 404 while off).
* `log_file`: when given, one JSON line per comparison is appended there, so a model can be
  judged offline before it is given control. Empty (the default) writes nothing.

A comparison never authorizes anything: it only measures the difference, per step and per
group of values (linear in metres, rotation in radians, gripper in the 0 to 1 range).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_ENV = "HYDRA_UMC_VLA_ENGINE_CONFIG"
MAX_STEPS = 1000


class ShadowError(ValueError):
    """The configuration file or the sequences of a comparison cannot be used."""


@dataclass(frozen=True)
class ShadowPolicy:
    enabled: bool = False
    log_file: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ShadowError(f"shadow.enabled must be true or false, got {self.enabled!r}")
        if not isinstance(self.log_file, str):
            raise ShadowError(f"shadow.log_file must be a string, got {self.log_file!r}")


def load_shadow_policy(path: str | os.PathLike[str] | None = None) -> ShadowPolicy:
    chosen = str(path) if path else os.environ.get(CONFIG_ENV, "")
    if not chosen:
        return ShadowPolicy()
    try:
        data = json.loads(Path(chosen).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ShadowError(f"cannot read the configuration file {chosen}: {error}") from error
    section = data.get("shadow", {}) if isinstance(data, dict) else None
    if not isinstance(section, dict):
        raise ShadowError(f"{chosen} must hold a JSON object whose shadow entry is an object")
    return ShadowPolicy(**{key: section[key] for key in ("enabled", "log_file") if key in section})


def _sequence(value: object, label: str) -> list[tuple[float, ...]]:
    if not isinstance(value, list) or not value:
        raise ShadowError(f"{label}: expected a non-empty JSON array of actions")
    if len(value) > MAX_STEPS:
        raise ShadowError(f"{label}: {len(value)} steps exceed the limit of {MAX_STEPS}")
    out: list[tuple[float, ...]] = []
    for step, action in enumerate(value):
        if not isinstance(action, (list, tuple)) or len(action) != 7:
            raise ShadowError(f"{label}[{step}]: expected 7 numbers")
        numbers: list[float] = []
        for index, number in enumerate(action):
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ShadowError(f"{label}[{step}][{index}] must be a finite number, got {number!r}")
            numbers.append(float(number))
        out.append(tuple(numbers))
    return out


def compare_actions(proposed: object, operator: object) -> dict:
    """Per-step differences between the proposed and the operator's actions (the shorter length is compared)."""
    mine = _sequence(proposed, "proposed")
    theirs = _sequence(operator, "operator")
    common = min(len(mine), len(theirs))
    steps = []
    for step in range(common):
        delta = [a - b for a, b in zip(mine[step], theirs[step], strict=False)]
        steps.append({
            "step": step,
            "linear": math.sqrt(sum(d * d for d in delta[:3])),
            "rotation": math.sqrt(sum(d * d for d in delta[3:6])),
            "gripper": abs(delta[6]),
        })
    summary = {
        group: {
            "mean": sum(s[group] for s in steps) / common,
            "max": max(s[group] for s in steps),
        }
        for group in ("linear", "rotation", "gripper")
    }
    return {
        "compared_steps": common,
        "proposed_steps": len(mine),
        "operator_steps": len(theirs),
        "steps": steps,
        "summary": summary,
        "authorized": False,
    }


def append_log(policy: ShadowPolicy, result: dict) -> None:
    """One JSON line per comparison, when a log file is configured."""
    if not policy.log_file:
        return
    line = json.dumps({"summary": result["summary"], "compared_steps": result["compared_steps"]}, sort_keys=True)
    with open(policy.log_file, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
