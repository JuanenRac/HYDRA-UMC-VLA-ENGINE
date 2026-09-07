# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/action_tokens.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Action tokenization: the "Action Tokens" step in the VLA inference flow.

Real VLA models (OpenVLA, RT-2) don't emit continuous robot actions
directly - they emit discrete token ids, one per action dimension, each
uniformly binned across that dimension's known range (typically 256 bins,
matching an 8-bit action vocabulary). Turning those bins back into
continuous values, and continuous values into bins, is a fixed,
well-defined piece of math independent of which specific VLA model or
Hailo-10 NPU produced/will produce the tokens - exactly the kind of
hardware-independent real logic this v0 pass covers.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_VOCAB_SIZE = 256


class TokenizationError(ValueError):
    """Raised for an out-of-range token, wrong dimensionality, or bad bounds."""


@dataclass(frozen=True)
class ActionSpec:
    name: str
    min: float
    max: float

    def __post_init__(self) -> None:
        if self.min >= self.max:
            raise TokenizationError(f"{self.name}: min ({self.min}) must be < max ({self.max})")


# The 7-DOF action space real VLA papers (OpenVLA, RT-2) train on: a 6-DOF
# end-effector pose delta plus a gripper command. Bounds are per-step deltas
# in meters/radians, not absolute pose - a VLA model predicts small
# corrections, not where the arm ends up.
VLA_ACTION_SPACE: tuple[ActionSpec, ...] = (
    ActionSpec("dx", -0.05, 0.05),
    ActionSpec("dy", -0.05, 0.05),
    ActionSpec("dz", -0.05, 0.05),
    ActionSpec("droll", -0.1, 0.1),
    ActionSpec("dpitch", -0.1, 0.1),
    ActionSpec("dyaw", -0.1, 0.1),
    ActionSpec("gripper", 0.0, 1.0),
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def encode_action(
    values: tuple[float, ...],
    specs: tuple[ActionSpec, ...] = VLA_ACTION_SPACE,
    vocab_size: int = DEFAULT_VOCAB_SIZE,
) -> tuple[int, ...]:
    """Continuous action values -> discrete bin-id tokens, one per dimension.

    Out-of-range values are clamped rather than rejected: a real model's
    raw prediction can slightly overshoot a bound, and clamping is what
    lets a downstream consumer still get a usable (saturated) action
    instead of a hard failure over a rounding-sized excess.
    """
    if len(values) != len(specs):
        raise TokenizationError(f"expected {len(specs)} action values, got {len(values)}")
    tokens = []
    for value, spec in zip(values, specs):
        clamped = _clamp(value, spec.min, spec.max)
        fraction = (clamped - spec.min) / (spec.max - spec.min)
        # fraction in [0, 1] -> bin in [0, vocab_size - 1]; clamp the top
        # edge case where fraction == 1.0 maps past the last valid bin.
        bin_id = min(int(fraction * vocab_size), vocab_size - 1)
        tokens.append(bin_id)
    return tuple(tokens)


def decode_action(
    tokens: tuple[int, ...],
    specs: tuple[ActionSpec, ...] = VLA_ACTION_SPACE,
    vocab_size: int = DEFAULT_VOCAB_SIZE,
) -> tuple[float, ...]:
    """Discrete bin-id tokens -> continuous action values (bin centers)."""
    if len(tokens) != len(specs):
        raise TokenizationError(f"expected {len(specs)} tokens, got {len(tokens)}")
    values = []
    for token, spec in zip(tokens, specs):
        if not (0 <= token < vocab_size):
            raise TokenizationError(f"{spec.name}: token {token} out of range [0, {vocab_size})")
        bin_center_fraction = (token + 0.5) / vocab_size
        values.append(spec.min + bin_center_fraction * (spec.max - spec.min))
    return tuple(values)
