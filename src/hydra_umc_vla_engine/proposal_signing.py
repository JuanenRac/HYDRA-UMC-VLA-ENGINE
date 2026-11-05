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

With an Ed25519 key (`Ed25519Seed`, a file holding a 32-byte seed in hex) the proposal is signed instead with a key that
only its operator holds: whoever checks needs the PUBLIC key alone (`verify_proposal_ed25519`, and the server through
`POST /api/trajectory/proposals/verify`), so the checker cannot sign. The proposal then carries `signature_alg: "ed25519"`,
the `key_id` (the first eight bytes of the SHA-512 of the public key, in hex) and a 128-hex-character `signature` over a
message of its own (`hydra-umc-vla-proposal-ed25519-v1`, which also covers the key id). The checker decides the algorithm
from its own configuration, never from the proposal, so a proposal cannot ask to be checked more weakly.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

from . import ed25519_pure

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


def key_id_of(public_key: bytes) -> str:
    """The id of a public key: the first eight bytes of its SHA-512, in lowercase hex."""
    return hashlib.sha512(public_key).digest()[:8].hex()


class Ed25519Seed(bytes):
    """The 32-byte seed of an Ed25519 key: given where an HMAC key is given, it makes `sign_proposal` sign with Ed25519."""

    @property
    def public_key(self) -> bytes:
        return ed25519_pure.public_key(bytes(self))

    @property
    def key_id(self) -> str:
        return key_id_of(self.public_key)


def load_ed25519_seed(path: str | Path) -> Ed25519Seed:
    """The seed from a file that holds 64 hexadecimal characters (the file stays in the installation, never in the repository)."""
    try:
        seed = bytes.fromhex(Path(path).read_text(encoding="ascii").strip())
    except (OSError, ValueError) as error:
        raise ProposalKeyError(f"cannot read the Ed25519 seed file (64 hexadecimal characters): {error}") from error
    if len(seed) != ed25519_pure.SEED_SIZE:
        raise ProposalKeyError("the Ed25519 seed must be 32 bytes (64 hexadecimal characters)")
    return Ed25519Seed(seed)


def load_public_keys(path: str | Path) -> dict[str, bytes]:
    """The operators' public keys by key id, from {"keys": {"<key id>": "<64 hex>"}} (the file the server reads too).

    An entry whose id is not the id of its key is left out.
    """
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProposalKeyError(f"cannot read the public keys file: {error}") from error
    keys: dict[str, bytes] = {}
    entries = document.get("keys") if isinstance(document, dict) else None
    for key_id, text in entries.items() if isinstance(entries, dict) else ():
        try:
            key = bytes.fromhex(text)
        except (TypeError, ValueError):
            continue
        if len(key) == ed25519_pure.PUBLIC_KEY_SIZE and key_id_of(key) == str(key_id).lower():
            keys[str(key_id).lower()] = key
    return keys


def _frame(parts: tuple[str, ...]) -> bytes:
    return b"".join(str(len(part.encode("utf-8"))).encode("ascii") + b":" + part.encode("utf-8") for part in parts)


def _message(
    fingerprint: str, robot_id: str, issued_at_ms: int, expires_at_ms: int, model_version: str = "", instruction_sha256: str = ""
) -> bytes:
    return _frame((
        "hydra-umc-vla-proposal-v2", fingerprint, robot_id, str(issued_at_ms), str(expires_at_ms), model_version, instruction_sha256
    ))


def _message_ed25519(
    fingerprint: str, robot_id: str, issued_at_ms: int, expires_at_ms: int, model_version: str, instruction_sha256: str, key_id: str
) -> bytes:
    return _frame((
        "hydra-umc-vla-proposal-ed25519-v1", fingerprint, robot_id, str(issued_at_ms), str(expires_at_ms), model_version, instruction_sha256, key_id
    ))


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
    or for another instruction. A key that is an `Ed25519Seed` signs with Ed25519 (and adds `signature_alg` and `key_id`);
    any other key is an HMAC key.
    """
    if not robot_id.strip():
        raise ValueError("a signed proposal names the robot it is for")
    if not 0 < validity_ms <= MAX_VALIDITY_MS:
        raise ValueError(f"the validity must be between 1 and {MAX_VALIDITY_MS} ms")
    issued = int(time.time() * 1000) if now_ms is None else now_ms
    expires = issued + validity_ms
    extra: dict = {}
    if isinstance(key, Ed25519Seed):
        key_id = key.key_id
        signature = ed25519_pure.sign(
            bytes(key), _message_ed25519(fingerprint, robot_id, issued, expires, model_version, instruction_sha256, key_id)
        ).hex()
        extra = {"signature_alg": "ed25519", "key_id": key_id}
    else:
        signature = hmac.new(
            key, _message(fingerprint, robot_id, issued, expires, model_version, instruction_sha256), hashlib.sha256
        ).hexdigest()
    fields = {"robot_id": robot_id, "issued_at_ms": issued, "expires_at_ms": expires, "signature": signature, **extra}
    if model_version:
        fields["model_version"] = model_version
    if instruction_sha256:
        fields["instruction_sha256"] = instruction_sha256
    return fields


def _context_problem(
    robot_id: str,
    issued: int,
    expires: int,
    model_version: str,
    instruction: str,
    *,
    now: int,
    expected_robot_id: str,
    expected_model_version: str | None,
    expected_instruction_sha256: str | None,
) -> str:
    """Why a proposal whose signature is good must still be refused ('' when it is current, for the robot, the model and the instruction)."""
    if expires <= issued or expires - issued > MAX_VALIDITY_MS:
        return "the validity window of the proposal is not acceptable"
    if issued > now + CLOCK_SKEW_MS:
        return "the proposal was issued in the future"
    if now >= expires:
        return "the proposal has expired"
    if not expected_robot_id or robot_id != expected_robot_id:
        return "the proposal is for a different robot"
    if expected_model_version is not None and model_version != expected_model_version:
        return "the proposal was made by a different model version"
    if expected_instruction_sha256 is not None and instruction != expected_instruction_sha256:
        return "the proposal answers a different instruction"
    return ""


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
    if issued is None or expires is None:
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
    problem = _context_problem(
        robot_id, issued, expires, model_version, instruction, now=now, expected_robot_id=expected_robot_id,
        expected_model_version=expected_model_version, expected_instruction_sha256=expected_instruction_sha256,
    )
    return (False, problem) if problem else (True, "")


def verify_proposal_ed25519(
    public_keys: dict[str, bytes],
    proposal: dict,
    *,
    expected_robot_id: str,
    now_ms: int | None = None,
    expected_model_version: str | None = None,
    expected_instruction_sha256: str | None = None,
) -> tuple[bool, str]:
    """(True, '') when the proposal is signed with Ed25519 by a listed key, is current and is for this robot; otherwise (False, why).

    `public_keys` maps a key id to a public key (`load_public_keys`). Only public keys are needed: whoever checks cannot sign. The rules
    of the time, the robot, the model and the instruction are those of `verify_proposal`.
    """
    now = int(time.time() * 1000) if now_ms is None else now_ms
    fingerprint = proposal.get("fingerprint")
    robot_id = proposal.get("robot_id")
    signature = proposal.get("signature")
    key_id = proposal.get("key_id")
    issued = proposal.get("issued_at_ms")
    expires = proposal.get("expires_at_ms")
    model_version = proposal.get("model_version", "")
    instruction = proposal.get("instruction_sha256", "")
    if not (
        isinstance(fingerprint, str) and isinstance(robot_id, str) and isinstance(signature, str) and isinstance(key_id, str)
        and isinstance(model_version, str) and isinstance(instruction, str)
    ):
        return False, "the proposal is not signed"
    if proposal.get("signature_alg") != "ed25519":
        return False, "the proposal is not signed with ed25519"
    if (
        isinstance(issued, bool) or not isinstance(issued, int) or issued <= 0
        or isinstance(expires, bool) or not isinstance(expires, int) or expires <= 0
    ):
        return False, "the proposal has no valid time window"
    public = public_keys.get(key_id)
    if public is None:
        return False, "the proposal is signed by a key that is not listed"
    try:
        raw = bytes.fromhex(signature)
    except ValueError:
        raw = b""
    message = _message_ed25519(fingerprint, robot_id, issued, expires, model_version, instruction, key_id)
    if len(signature) != 128 or signature != signature.lower() or not ed25519_pure.verify(public, message, raw):
        return False, "the signature of the proposal does not match"
    problem = _context_problem(
        robot_id, issued, expires, model_version, instruction, now=now, expected_robot_id=expected_robot_id,
        expected_model_version=expected_model_version, expected_instruction_sha256=expected_instruction_sha256,
    )
    return (False, problem) if problem else (True, "")
