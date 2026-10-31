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

import math
from dataclasses import dataclass

DEFAULT_VOCAB_SIZE = 256
# A vocabulary needs at least two bins to say anything, and an absurd one only exhausts memory or loses all resolution.
MIN_VOCAB_SIZE = 2
MAX_VOCAB_SIZE = 65536


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


def _check_vocab_size(vocab_size: int) -> None:
    """A vocab_size comes from a request body: 0 or a negative one gives wrong bins (or a ZeroDivisionError), a boolean is not a size."""
    if isinstance(vocab_size, bool) or not isinstance(vocab_size, int) or not (MIN_VOCAB_SIZE <= vocab_size <= MAX_VOCAB_SIZE):
        raise TokenizationError(f"vocab_size must be an integer from {MIN_VOCAB_SIZE} to {MAX_VOCAB_SIZE}, got {vocab_size!r}")


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

    A value that is not a finite number (NaN, infinity) is NOT clamped: clamping a NaN picks the
    upper bound (max(lo, min(hi, nan)) is hi), so a model that produced NaN would have been
    encoded as the maximum movement on every axis. It is rejected instead.
    """
    _check_vocab_size(vocab_size)
    if len(values) != len(specs):
        raise TokenizationError(f"expected {len(specs)} action values, got {len(values)}")
    tokens = []
    for value, spec in zip(values, specs, strict=False):
        if not math.isfinite(value):
            raise TokenizationError(f"{spec.name}: the action value must be a finite number, got {value!r}")
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
    snap_zero: bool = True,
) -> tuple[float, ...]:
    """Discrete bin-id tokens -> continuous action values (bin centers).

    With an even vocabulary no bin is centred on zero: the "no movement"
    token 128 decodes to +half a bin, and a model that keeps predicting
    "stay still" would drift a few millimetres per hundred steps. With
    `snap_zero` (the default) a value within half a bin of zero, on an axis
    whose range is symmetric around zero (the deltas, not the gripper),
    decodes to exactly 0.0."""
    _check_vocab_size(vocab_size)
    if len(tokens) != len(specs):
        raise TokenizationError(f"expected {len(specs)} tokens, got {len(tokens)}")
    values = []
    for token, spec in zip(tokens, specs, strict=False):
        if not (0 <= token < vocab_size):
            raise TokenizationError(f"{spec.name}: token {token} out of range [0, {vocab_size})")
        bin_center_fraction = (token + 0.5) / vocab_size
        value = spec.min + bin_center_fraction * (spec.max - spec.min)
        half_bin = (spec.max - spec.min) / vocab_size / 2
        if snap_zero and spec.min == -spec.max and abs(value) <= half_bin * (1 + 1e-9):
            value = 0.0
        values.append(value)
    return tuple(values)
