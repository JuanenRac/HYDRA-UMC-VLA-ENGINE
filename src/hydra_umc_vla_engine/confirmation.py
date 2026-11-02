# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/confirmation.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Human confirmation of a trajectory proposal, in two steps.

A proposal is never an order. With confirmations on, every proposal the engine offers waits to be confirmed by a person, on a device with a screen (the Watch or the
Android app, reached through the server that knows who the person is), in two steps:

1. **prepare** (`POST /confirmations/<id>/prepare`, with the operator): the engine answers a summary of the trajectory (how many steps, how long the path is, the longest
   step, the final pose, how many times the gripper changes, what the guard and the kinematic check said) and a `confirmationToken`. The device shows the summary.
2. **confirm** (`POST /confirmations/<id>/confirm`, with the operator and the token): only a person who has seen the summary can send the token back. The engine checks
   that the token is genuine (an HMAC-SHA256 under the installation key, so nobody else can mint one), that it is the last one issued for this proposal, that it is
   for this operator and this fingerprint, and that it has not expired; it is accepted once. The answer is an **approval**: the fingerprint, the robot, the operator and a short
   time window, signed with the same key, which the layer that executes checks with `verify_approval`.

`POST /confirmations/<id>/reject` throws the proposal away. A proposal that is not confirmed within `ttl_seconds` is forgotten. The engine does not authenticate people: the
operator is named by the caller that holds the bearer token of the API (the server that relays the Watch or the app), and the token of step 1 is bound to that name, so step 2
has to come under the same name. At most `max_pending` proposals wait at the same time; the oldest is dropped to make room.

It is off unless the `confirmation` section of the configuration file says `"enabled": true`, and it needs the key of the signed proposals (`--proposal-key-file`):

    {"confirmation": {"enabled": true, "ttl_seconds": 60, "token_seconds": 30, "max_pending": 16, "approval_validity_ms": 10000}}
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .trajectory import Pose

CONFIG_ENV = "HYDRA_UMC_VLA_ENGINE_CONFIG"
_KEYS = {"enabled", "ttl_seconds", "token_seconds", "max_pending", "approval_validity_ms"}
_OPERATOR = re.compile(r"[A-Za-z0-9_.:@-]{1,64}")
MAX_APPROVAL_VALIDITY_MS = 600_000


class ConfirmationConfigError(ValueError):
    """The confirmation section of the configuration file cannot be used."""


class ConfirmationError(ValueError):
    """A step of the confirmation is refused. `status` is the HTTP status the API answers."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ConfirmationPolicy:
    enabled: bool = False
    ttl_seconds: float = 60.0
    token_seconds: float = 30.0
    max_pending: int = 16
    approval_validity_ms: int = 10_000

    def __post_init__(self) -> None:
        for name, value, low, high in (("ttl_seconds", self.ttl_seconds, 1.0, 3600.0), ("token_seconds", self.token_seconds, 1.0, 600.0)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ConfirmationConfigError(f"confirmation.{name} must be a number from {low:g} to {high:g}")
        if isinstance(self.max_pending, bool) or not isinstance(self.max_pending, int) or not 1 <= self.max_pending <= 256:
            raise ConfirmationConfigError("confirmation.max_pending must be an integer from 1 to 256")
        if isinstance(self.approval_validity_ms, bool) or not isinstance(self.approval_validity_ms, int) or not 1 <= self.approval_validity_ms <= MAX_APPROVAL_VALIDITY_MS:
            raise ConfirmationConfigError(f"confirmation.approval_validity_ms must be an integer from 1 to {MAX_APPROVAL_VALIDITY_MS}")
        if not isinstance(self.enabled, bool):
            raise ConfirmationConfigError("confirmation.enabled must be true or false")


def load_confirmation_policy(path: str | os.PathLike[str] | None = None) -> ConfirmationPolicy:
    chosen = str(path) if path else os.environ.get(CONFIG_ENV, "")
    if not chosen:
        return ConfirmationPolicy()
    try:
        data = json.loads(Path(chosen).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfirmationConfigError(f"cannot read the configuration file {chosen}: {error}") from error
    section = data.get("confirmation", {}) if isinstance(data, dict) else None
    if not isinstance(section, dict) or set(section) - _KEYS:
        raise ConfirmationConfigError(f"{chosen} must hold a JSON object whose confirmation entry is an object with the keys {sorted(_KEYS)}")
    return ConfirmationPolicy(**section)


def summarize(poses: Sequence[Pose], *, robot_id: str, guard: dict | None, kinematics: dict | None) -> dict[str, Any]:
    """What the person sees before confirming: small, and computed from the poses and not from anything the model said about them."""
    path = longest = 0.0
    gripper_changes = 0
    for before, after in zip(poses, poses[1:], strict=False):
        step = math.dist((before.x, before.y, before.z), (after.x, after.y, after.z))
        path += step
        longest = max(longest, step)
        if after.gripper != before.gripper:
            gripper_changes += 1
    final = poses[-1]
    return {
        "robot_id": robot_id, "steps": max(len(poses) - 1, 0), "path_length_m": round(path, 6), "longest_step_m": round(longest, 6),
        "gripper_changes": gripper_changes, "final_pose": {"x": final.x, "y": final.y, "z": final.z, "roll": final.roll, "pitch": final.pitch, "yaw": final.yaw, "gripper": final.gripper},
        "guard": (guard or {}).get("outcome"), "kinematics": (kinematics or {}).get("outcome"),
    }


def _part(text: str) -> bytes:
    raw = text.encode("utf-8")
    return str(len(raw)).encode("ascii") + b":" + raw


def _approval_message(fingerprint: str, robot_id: str, operator: str, approved_at_ms: int, expires_at_ms: int) -> bytes:
    return b"".join(_part(p) for p in ("hydra-umc-vla-approval-v1", fingerprint, robot_id, operator, str(approved_at_ms), str(expires_at_ms)))


def verify_approval(key: bytes, approval: dict, *, expected_fingerprint: str, expected_robot_id: str, now_ms: int | None = None) -> tuple[bool, str]:
    """(True, '') when the approval is genuine, current, for this trajectory and this robot; otherwise (False, why). The layer that executes calls this."""
    now = int(time.time() * 1000) if now_ms is None else now_ms
    fingerprint, robot, operator, approved, expires, signature = (approval.get(k) for k in ("fingerprint", "robot_id", "operator", "approved_at_ms", "expires_at_ms", "signature"))
    if not all(isinstance(v, str) for v in (fingerprint, robot, operator, signature)) or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (approved, expires)):
        return False, "the approval is not signed"
    assert isinstance(fingerprint, str) and isinstance(robot, str) and isinstance(operator, str) and isinstance(approved, int) and isinstance(expires, int)
    expected = hmac.new(key, _approval_message(fingerprint, robot, operator, approved, expires), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode("ascii"), str(signature).encode("utf-8", "replace")):
        return False, "the signature of the approval does not match"
    if fingerprint != expected_fingerprint:
        return False, "the approval is for a different trajectory"
    if not expected_robot_id or robot != expected_robot_id:
        return False, "the approval is for a different robot"
    if approved > now + 5000:
        return False, "the approval was given in the future"
    if now >= expires:
        return False, "the approval has expired"
    return True, ""


@dataclass
class _Pending:
    pending_id: str
    fingerprint: str
    summary: dict[str, Any]
    created: float
    nonce: str = ""
    operator: str = ""
    prepared: float = 0.0


class ConfirmationStore:
    def __init__(self, policy: ConfirmationPolicy, key: bytes, robot_id: str, clock: Callable[[], float] = time.time) -> None:
        self.policy = policy
        self._key = key
        self.robot_id = robot_id
        self._clock = clock
        self._lock = threading.Lock()
        self._pending: OrderedDict[str, _Pending] = OrderedDict()
        self.approved = 0
        self.rejected = 0

    def _expire(self) -> None:
        now = self._clock()
        for pending_id in [i for i, p in self._pending.items() if now - p.created > self.policy.ttl_seconds]:
            del self._pending[pending_id]

    def create(self, fingerprint: str, summary: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._expire()
            while len(self._pending) >= self.policy.max_pending:
                self._pending.popitem(last=False)
            pending_id = secrets.token_hex(8)
            self._pending[pending_id] = _Pending(pending_id, fingerprint, summary, self._clock())
        return {"pending_id": pending_id, "status": "awaiting_confirmation", "expires_in_s": self.policy.ttl_seconds}

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            self._expire()
            now = self._clock()
            return [{"pending_id": p.pending_id, "fingerprint": p.fingerprint, "summary": p.summary, "expires_in_s": round(self.policy.ttl_seconds - (now - p.created), 3)}
                    for p in self._pending.values()]

    def _get(self, pending_id: str) -> _Pending:
        self._expire()
        pending = self._pending.get(pending_id)
        if pending is None:
            raise ConfirmationError("there is no such proposal waiting (it was confirmed, rejected or has expired)", 404)
        return pending

    @staticmethod
    def _operator(operator: object) -> str:
        if not isinstance(operator, str) or not _OPERATOR.fullmatch(operator):
            raise ConfirmationError("operator is 1 to 64 characters of letters, digits and _ . : @ -")
        return operator

    def _token(self, pending: _Pending, issued_ms: int) -> str:
        body = base64.urlsafe_b64encode(json.dumps({"n": pending.nonce, "p": pending.pending_id, "f": pending.fingerprint, "o": pending.operator, "i": issued_ms},
                                                    sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
        return body + "." + hmac.new(self._key, body.encode("ascii"), hashlib.sha256).hexdigest()

    def prepare(self, pending_id: str, operator: object) -> dict[str, Any]:
        """Step 1: the summary and the token the device sends back to confirm. A second prepare replaces the token of the first."""
        name = self._operator(operator)
        with self._lock:
            pending = self._get(pending_id)
            pending.nonce, pending.operator, pending.prepared = secrets.token_hex(12), name, self._clock()
            return {"pending_id": pending_id, "summary": pending.summary, "fingerprint": pending.fingerprint, "confirmationToken": self._token(pending, int(pending.prepared * 1000)),
                    "confirmationValiditySeconds": self.policy.token_seconds}

    def confirm(self, pending_id: str, operator: object, token: object) -> dict[str, Any]:
        """Step 2: the signed approval, once, for the operator that prepared and the token that was issued."""
        name = self._operator(operator)
        if not isinstance(token, str) or token.count(".") != 1 or len(token) > 1024:
            raise ConfirmationError("confirmationToken must be the text that prepare answered")
        with self._lock:
            pending = self._get(pending_id)
            if not pending.nonce:
                raise ConfirmationError("prepare this proposal first: the operator has not seen its summary", 409)
            body, _, signature = token.partition(".")
            expected = hmac.new(self._key, body.encode("ascii", "replace"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected.encode("ascii"), signature.encode("utf-8", "replace")):
                raise ConfirmationError("the confirmation token is not genuine", 403)
            try:
                claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            except (ValueError, UnicodeDecodeError):
                raise ConfirmationError("the confirmation token cannot be read", 403) from None
            if not isinstance(claims, dict) or claims.get("n") != pending.nonce or claims.get("p") != pending_id or claims.get("f") != pending.fingerprint:
                raise ConfirmationError("the confirmation token is not the one issued for this proposal", 403)
            if name != pending.operator or claims.get("o") != name:
                raise ConfirmationError("the confirmation comes from another operator than the one that prepared it", 403)
            if self._clock() - pending.prepared > self.policy.token_seconds:
                pending.nonce = ""
                raise ConfirmationError("the confirmation token has expired: prepare the proposal again", 410)
            del self._pending[pending_id]
            self.approved += 1
            now_ms = int(self._clock() * 1000)
            expires = now_ms + self.policy.approval_validity_ms
            signature = hmac.new(self._key, _approval_message(pending.fingerprint, self.robot_id, name, now_ms, expires), hashlib.sha256).hexdigest()
            return {"approved": True, "fingerprint": pending.fingerprint, "robot_id": self.robot_id, "operator": name, "approved_at_ms": now_ms, "expires_at_ms": expires, "signature": signature}

    def reject(self, pending_id: str, operator: object) -> dict[str, Any]:
        name = self._operator(operator)
        with self._lock:
            pending = self._get(pending_id)
            del self._pending[pending_id]
            self.rejected += 1
            return {"approved": False, "pending_id": pending_id, "fingerprint": pending.fingerprint, "operator": name}
