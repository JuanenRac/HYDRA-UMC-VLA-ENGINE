# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/model_manifest.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real, versioned contract a future VLA model integration must satisfy.

No specific OpenVLA/RT-2 variant or version has been chosen yet (see the
README's own Roadmap) - this is honestly a shape/target contract, not a
model loader. `EXPECTED_MODEL_MANIFEST`'s `action_dims`/`vocab_size`
mirror `action_tokens.py`'s own real `VLA_ACTION_SPACE`/
`DEFAULT_VOCAB_SIZE` directly (never duplicated as separate literals),
so this manifest can never silently drift from the tokenizer it
describes. `hailo_arch` is restricted to this ecosystem's own real,
closed Hailo chip family - the same `KNOWN_HAILO_ARCHS` set
HYDRA-UMC-DETECTION-HEF already validates its own model registry
against, since both projects target the same real hardware family.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .action_tokens import DEFAULT_VOCAB_SIZE, VLA_ACTION_SPACE

MANIFEST_SCHEMA_VERSION = "1.0"

# Mirrors HYDRA-UMC-DETECTION-HEF's own KNOWN_HAILO_ARCHS - the real,
# closed set of Hailo chip family identifiers this ecosystem targets.
KNOWN_HAILO_ARCHS = frozenset(
    {"hailo8", "hailo8r", "hailo8l", "hailo15h", "hailo15m", "hailo15l", "hailo10h"}
)


@dataclass(frozen=True)
class ModelManifest:
    """The real shape contract a candidate model must declare."""

    action_dims: int
    vocab_size: int
    hailo_arch: str


# The real contract THIS engine's own tokenizer already implements -
# derived from action_tokens.py, never a separately-maintained literal.
EXPECTED_MODEL_MANIFEST = ModelManifest(
    action_dims=len(VLA_ACTION_SPACE),
    vocab_size=DEFAULT_VOCAB_SIZE,
    hailo_arch="hailo10h",
)


def validate_model_manifest(candidate: dict[str, Any]) -> list[str]:
    """Real validation of a candidate model manifest (e.g. a future
    model's own sidecar JSON) against `EXPECTED_MODEL_MANIFEST`. Returns
    every real mismatch found - empty means the candidate model is
    genuinely compatible with this engine's tokenizer/hardware target."""
    issues: list[str] = []

    action_dims = candidate.get("action_dims")
    if action_dims != EXPECTED_MODEL_MANIFEST.action_dims:
        issues.append(
            f"action_dims mismatch: expected {EXPECTED_MODEL_MANIFEST.action_dims}, got {action_dims!r}"
        )

    vocab_size = candidate.get("vocab_size")
    if vocab_size != EXPECTED_MODEL_MANIFEST.vocab_size:
        issues.append(
            f"vocab_size mismatch: expected {EXPECTED_MODEL_MANIFEST.vocab_size}, got {vocab_size!r}"
        )

    hailo_arch = candidate.get("hailo_arch")
    if hailo_arch not in KNOWN_HAILO_ARCHS:
        issues.append(f"unknown or missing hailo_arch: {hailo_arch!r} (known: {sorted(KNOWN_HAILO_ARCHS)})")

    return issues


def validate_inference_output(output: dict[str, Any]) -> list[str]:
    """Real shape + confidence validation for a (future) model's raw
    inference output - the contract any real VLA model integration would
    have to satisfy before its tokens are trusted enough to decode and
    execute. Returns every real issue found; empty means `output` is
    genuinely well-formed."""
    issues: list[str] = []

    tokens = output.get("tokens")
    expected_dims = EXPECTED_MODEL_MANIFEST.action_dims
    if not isinstance(tokens, (list, tuple)):
        issues.append("tokens: missing or not a list")
    elif len(tokens) != expected_dims:
        issues.append(f"tokens: expected {expected_dims} values, got {len(tokens)}")
    else:
        for index, token in enumerate(tokens):
            if not isinstance(token, int) or isinstance(token, bool):
                issues.append(f"tokens[{index}]: not an integer ({token!r})")
            elif not (0 <= token < EXPECTED_MODEL_MANIFEST.vocab_size):
                issues.append(f"tokens[{index}]: {token} out of range [0, {EXPECTED_MODEL_MANIFEST.vocab_size})")

    confidence = output.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        issues.append("confidence: missing or not a number")
    elif not (0.0 <= float(confidence) <= 1.0):
        issues.append(f"confidence: {confidence} out of range [0.0, 1.0]")

    return issues
