# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/proposal_signing.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A signed trajectory proposal: which trajectory, for which robot, and until when.

The fingerprint of a proposal only names the poses. With a key (a file of this installation, never the
repository) the engine also signs the fingerprint together with the robot and a short time window, so the layer
that executes can check that the proposal is genuine, current and meant for that robot, and a trajectory that was
once approved cannot be replayed later or on another robot. The signature is an HMAC-SHA256: it proves the
proposal comes from a holder of the installation's key; it does not tell one holder from another.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path

MIN_KEY_BYTES = 16
MAX_VALIDITY_MS = 600_000
DEFAULT_VALIDITY_MS = 60_000
CLOCK_SKEW_MS = 5_000


class ProposalKeyError(ValueError):
    """The key file is missing, unreadable or too short."""


def load_key(path: str | Path) -> bytes:
    try:
        raw = Path(path).read_bytes().strip()
    except OSError as error:
        raise ProposalKeyError(f"cannot read the proposal key file: {error}") from error
    if len(raw) < MIN_KEY_BYTES:
        raise ProposalKeyError(f"the proposal key must be at least {MIN_KEY_BYTES} bytes")
    return raw


def _message(
    fingerprint: str, robot_id: str, issued_at_ms: int, expires_at_ms: int, model_version: str = "", instruction_sha256: str = ""
) -> bytes:
    parts = (
        "hydra-umc-vla-proposal-v2", fingerprint, robot_id, str(issued_at_ms), str(expires_at_ms), model_version, instruction_sha256
    )
    return b"".join(str(len(part.encode("utf-8"))).encode("ascii") + b":" + part.encode("utf-8") for part in parts)


def sign_proposal(
    key: bytes,
    fingerprint: str,
    robot_id: str,
    *,
    validity_ms: int = DEFAULT_VALIDITY_MS,
    now_ms: int | None = None,
    model_version: str = "",
    instruction_sha256: str = "",
) -> dict:
    """The signed fields to add to a proposal record.

    `model_version` (the model that produced the actions) and `instruction_sha256` (the hash of the instruction they
    answer) are part of what is signed when given, so an approval cannot be moved to a proposal made by another model
    or for another instruction.
    """
    if not robot_id.strip():
        raise ValueError("a signed proposal names the robot it is for")
    if not 0 < validity_ms <= MAX_VALIDITY_MS:
        raise ValueError(f"the validity must be between 1 and {MAX_VALIDITY_MS} ms")
    issued = int(time.time() * 1000) if now_ms is None else now_ms
    expires = issued + validity_ms
    signature = hmac.new(
        key, _message(fingerprint, robot_id, issued, expires, model_version, instruction_sha256), hashlib.sha256
    ).hexdigest()
    fields = {"robot_id": robot_id, "issued_at_ms": issued, "expires_at_ms": expires, "signature": signature}
    if model_version:
        fields["model_version"] = model_version
    if instruction_sha256:
        fields["instruction_sha256"] = instruction_sha256
    return fields


def verify_proposal(
    key: bytes,
    proposal: dict,
    *,
    expected_robot_id: str,
    now_ms: int | None = None,
    expected_model_version: str | None = None,
    expected_instruction_sha256: str | None = None,
) -> tuple[bool, str]:
    """(True, '') when the proposal is genuine, current and for this robot; otherwise (False, why).

    With `expected_model_version` / `expected_instruction_sha256` the proposal must also be the one made by that
    model for that instruction.
    """
    now = int(time.time() * 1000) if now_ms is None else now_ms
    fingerprint = proposal.get("fingerprint")
    robot_id = proposal.get("robot_id")
    issued = proposal.get("issued_at_ms")
    expires = proposal.get("expires_at_ms")
    signature = proposal.get("signature")
    if not isinstance(fingerprint, str) or not isinstance(robot_id, str) or not isinstance(signature, str):
        return False, "the proposal is not signed"
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (issued, expires)):
        return False, "the proposal has no valid time window"
    model_version = proposal.get("model_version", "")
    instruction = proposal.get("instruction_sha256", "")
    if not isinstance(model_version, str) or not isinstance(instruction, str):
        return False, "the proposal is not signed"
    expected = hmac.new(
        key, _message(fingerprint, robot_id, issued, expires, model_version, instruction), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected.encode("ascii"), signature.encode("utf-8", "replace")):
        return False, "the signature of the proposal does not match"
    if expires <= issued or expires - issued > MAX_VALIDITY_MS:
        return False, "the validity window of the proposal is not acceptable"
    if issued > now + CLOCK_SKEW_MS:
        return False, "the proposal was issued in the future"
    if now >= expires:
        return False, "the proposal has expired"
    if not expected_robot_id or robot_id != expected_robot_id:
        return False, "the proposal is for a different robot"
    if expected_model_version is not None and model_version != expected_model_version:
        return False, "the proposal was made by a different model version"
    if expected_instruction_sha256 is not None and instruction != expected_instruction_sha256:
        return False, "the proposal answers a different instruction"
    return True, ""
