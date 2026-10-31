# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/api.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Plain JSON/HTTP surface (stdlib http.server) - same convention as this
family's other api.py files. All routes reach the exact functions
main.py's own `tokens encode/decode`, `trajectory integrate`, and `status`
subcommands already run. `POST /trajectory/integrate` takes the action
sequence directly in the JSON body rather than a server-side file path -
the CLI's own `--actions PATH` only makes sense on the same machine as
that file.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .proposal_signing import sign_proposal
from .access import authorized, reject
from .guard import REJECTED, GuardLimits, guard_trajectory
from .action_tokens import DEFAULT_VOCAB_SIZE, TokenizationError, decode_action, encode_action
from .confidence import ConfidenceConfigError, ConfidencePolicy, low_confidence_steps
from .consistency import ConsistencyConfigError, ConsistencyPolicy, inconsistent_steps
from .hardware import check_engine_status
from .shadow import ShadowError, ShadowPolicy, append_log, compare_actions
from .trajectory import Pose, TrajectoryError, integrate_trajectory


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    def default(o: object) -> object:
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)  # type: ignore[call-overload]
        if hasattr(o, "value"):  # enum
            return o.value
        return str(o)
    body = json.dumps(payload, default=default).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_error(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    _write_json(handler, status, {"error": message})


# Real fix: this used to read a caller-controlled Content-Length with no
# upper bound at all - a lying/oversized header could force unbounded
# memory buffering (same real DoS/OOM class already closed in this
# family's other api.py files, e.g. HYDRA-UMC-ANOMALY-DETECTOR's own).
MAX_BODY_BYTES = 1024 * 1024
# How much of an oversized body this drains before responding - lets the
# client finish sending before the response goes out (same reasoning as
# the sibling api.py modules that already do this). The drained bytes are
# read in 64 KiB pieces and thrown away, so nothing large is held in memory.
DRAIN_CAP_BYTES = MAX_BODY_BYTES * 16


def _reject_constant(name: str) -> float:
    raise ValueError(f"{name} is not a valid JSON number")


def _discard(rfile, length: int, chunk: int = 64 * 1024) -> None:
    """Reads and throws away `length` bytes in small pieces (never a 16 MiB buffer)."""
    remaining = length
    while remaining > 0:
        block = rfile.read(min(chunk, remaining))
        if not block:
            return
        remaining -= len(block)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except ValueError as error:
        raise ValueError("Content-Length must be an integer") from error
    if length < 0 or length > MAX_BODY_BYTES:
        if 0 <= length <= DRAIN_CAP_BYTES:
            _discard(handler.rfile, length)
        raise ValueError(f"request body must contain 0-{MAX_BODY_BYTES} bytes")
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    # json.loads accepts the literals NaN, Infinity and -Infinity, which are not JSON: they would reach the model's arithmetic as real numbers.
    return json.loads(raw, parse_constant=_reject_constant)


def _query_params(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    parsed = urlparse(handler.path)
    values = parse_qs(parsed.query, keep_blank_values=True)
    return {key: value[0] for key, value in values.items() if value}


def proposal_record(
    poses: list[dict],
    signer: tuple[bytes, str, int] | None = None,
    *,
    model_version: str = "",
    instruction_sha256: str = "",
) -> dict:
    """Marks a trajectory as a proposal, never an order.

    The engine only integrates predicted actions into poses; nothing here
    authorizes moving a machine. `fingerprint` identifies exactly these
    poses, so an approval given elsewhere can name the trajectory it
    approves and cannot be reused for a different one.
    """
    canonical = json.dumps(poses, sort_keys=True, separators=(",", ":"))
    record: dict = {
        "authorized": False,
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "requires": "approval by an authenticated control before any execution",
    }
    if signer is not None:
        # signer = (key, robot_id, validity_ms): the proposal also names its robot and time window, signed (proposal_signing.py)
        key, robot_id, validity_ms = signer
        record.update(
            sign_proposal(
                key, record["fingerprint"], robot_id, validity_ms=validity_ms,
                model_version=model_version, instruction_sha256=instruction_sha256,
            )
        )
    return record


def _strict_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number, got {value!r}")
    return float(value)


def _strict_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer, got {value!r}")
    return value


# GET path the project manifest declares as the health probe; it carries no token
HEALTH_PATH = "/health"


class Handler(BaseHTTPRequestHandler):
    server: "VlaEngineServer"

    # Seconds a client may stay silent on its connection before it is dropped,
    # so one that connects and sends nothing cannot hold a handler thread.
    timeout = 15.0

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # quiet by default, same reasoning as this family's other api.py files

    def do_GET(self) -> None:  # noqa: N802
        # the health path of the manifest stays open so the service registry can probe the service without the token
        if urlparse(self.path).path != HEALTH_PATH and not authorized(self, self.server.token):
            reject(self)
            return
        path = urlparse(self.path).path
        if path == "/status":
            params = _query_params(self)
            workspace = self.server.workspace
            if "workspace" in params:
                # only a folder inside the workspace the server was started with
                requested = Path(params["workspace"])
                try:
                    inside = requested.resolve().is_relative_to(self.server.workspace.resolve())
                except OSError:
                    inside = False
                if not inside:
                    _write_error(self, 400, "workspace must be inside the workspace this server was started with")
                    return
                workspace = requested
            status = check_engine_status(workspace)
            _write_json(self, 200, {
                "acceleratorPresent": status.accelerator_present,
                "modelWeightsPresent": status.model_weights_present,
                "mode": status.mode.value,
            })
        elif path == "/health":
            _write_json(self, 200, {"ok": True})
        elif path == "/stats":
            _write_json(self, 200, {"workspace": str(self.server.workspace)})
        else:
            _write_error(self, 404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        if not authorized(self, self.server.token):
            reject(self)
            return
        path = urlparse(self.path).path
        try:
            body = _read_json_body(self)
        except json.JSONDecodeError as e:
            _write_error(self, 400, f"malformed JSON body: {e}")
            return
        except ValueError as e:
            _write_error(self, 400, str(e))
            return
        if path == "/tokens/encode":
            self._handle_encode(body)
        elif path == "/tokens/decode":
            self._handle_decode(body)
        elif path == "/trajectory/integrate":
            self._handle_integrate(body)
        elif path == "/shadow/compare" and self.server.shadow.enabled:
            self._handle_shadow(body)
        else:
            _write_error(self, 404, "not found")

    def _handle_encode(self, body: dict) -> None:
        try:
            action = tuple(_strict_number(v, "action") for v in body["action"])
            vocab_size = _strict_int(body.get("vocab_size", DEFAULT_VOCAB_SIZE), "vocab_size")
            tokens = encode_action(action, vocab_size=vocab_size)
        except KeyError as e:
            _write_error(self, 400, f"missing required field: {e}")
            return
        except (TokenizationError, ValueError, TypeError) as e:
            _write_error(self, 400, str(e))
            return
        _write_json(self, 200, {"tokens": list(tokens)})

    def _handle_decode(self, body: dict) -> None:
        try:
            tokens = tuple(_strict_int(v, "tokens") for v in body["tokens"])
            vocab_size = _strict_int(body.get("vocab_size", DEFAULT_VOCAB_SIZE), "vocab_size")
            values = decode_action(tokens, vocab_size=vocab_size)
        except KeyError as e:
            _write_error(self, 400, f"missing required field: {e}")
            return
        except (TokenizationError, ValueError, TypeError) as e:
            _write_error(self, 400, str(e))
            return
        _write_json(self, 200, {"action": list(values)})

    def _handle_shadow(self, body: dict) -> None:
        # shadow mode: measures the difference between the proposed and the operator's actions; nothing is offered or moved
        try:
            result = compare_actions(body.get("proposed"), body.get("operator"))
            append_log(self.server.shadow, result)
        except ShadowError as e:
            _write_error(self, 400, str(e))
            return
        except OSError as e:
            _write_error(self, 500, f"cannot write the shadow log: {e}")
            return
        _write_json(self, 200, result)

    def _handle_integrate(self, body: dict) -> None:
        try:
            start_values = tuple(_strict_number(v, "start") for v in body["start"])
            start = Pose(*start_values, gripper=_strict_number(body.get("start_gripper", 0.0), "start_gripper"))  # type: ignore[misc,arg-type]
            actions_raw = body["actions"]
            if not isinstance(actions_raw, list):
                raise TrajectoryError("actions: expected a JSON array")
            actions = [tuple(a) for a in actions_raw]
            poses = integrate_trajectory(start, actions)
            low_steps = low_confidence_steps(body.get("confidences"), len(actions), self.server.confidence)
            odd_steps = inconsistent_steps(actions, body.get("alternatives"), self.server.consistency)
            instruction_sha256 = body.get("instruction_sha256", "")
            if not isinstance(instruction_sha256, str) or (
                instruction_sha256 and not re.fullmatch(r"[0-9a-f]{64}", instruction_sha256)
            ):
                raise ValueError("instruction_sha256 must be 64 lowercase hex characters (the SHA-256 of the instruction)")
        except KeyError as e:
            _write_error(self, 400, f"missing required field: {e}")
            return
        except (TokenizationError, TrajectoryError, ConfidenceConfigError, ConsistencyConfigError, ValueError, TypeError) as e:
            _write_error(self, 400, str(e))
            return
        if low_steps:
            # the model was not sure of these actions: no trajectory is offered
            _write_json(self, 422, {"error": "the confidence of some actions is below the configured minimum", "minimum": self.server.confidence.minimum, "low_confidence_steps": low_steps})
            return
        if odd_steps:
            # the repeated predictions of the model disagree on these steps: no trajectory is offered
            _write_json(self, 422, {"error": "the predictions of some actions are not consistent", "predictions": self.server.consistency.predictions, "inconsistent_steps": odd_steps})
            return
        guard_info: dict
        if self.server.guard is not None:
            result = guard_trajectory(poses, self.server.guard)
            guard_info = result.as_dict()
            if result.outcome == REJECTED:
                # a trajectory the guard refuses is not shown as a proposal at all
                _write_json(self, 422, {"error": "the trajectory guard rejected the trajectory", "guard": guard_info})
                return
            poses = result.poses
        elif self.server.require_guard:
            _write_error(self, 503, "this engine was started with --require-guard and has no guard file: no trajectory is offered")
            return
        else:
            guard_info = {"outcome": "not_configured", "reasons": [], "rejected_at_step": None}
        pose_dicts = [asdict(p) for p in poses]
        _write_json(self, 200, {"poses": pose_dicts, "guard": guard_info, "proposal": proposal_record(pose_dicts, self.server.proposal_signer, model_version=self.server.model_version, instruction_sha256=instruction_sha256)})


class VlaEngineServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        workspace: Path,
        token: str = "",
        guard: GuardLimits | None = None,
        require_guard: bool = False,
        proposal_signer: tuple[bytes, str, int] | None = None,
        model_version: str = "",
        confidence: ConfidencePolicy | None = None,
        consistency: ConsistencyPolicy | None = None,
        shadow: ShadowPolicy | None = None,
    ) -> None:
        super().__init__(address, Handler)
        # the lowest confidence an action may have (confidence.py); off by default
        self.confidence = confidence or ConfidencePolicy()
        # how many repeated predictions of a step must agree (consistency.py); off by default
        self.consistency = consistency or ConsistencyPolicy()
        # shadow mode (shadow.py): compares proposals with the operator's actions; off by default
        self.shadow = shadow or ShadowPolicy()
        # the model that produces the actions, signed into every proposal when given
        self.model_version = model_version
        # (key, robot_id, validity_ms): with it every proposal is signed for that robot and a short time window
        self.proposal_signer = proposal_signer
        # the limits of the cell every trajectory is checked against (guard.py); with require_guard no trajectory is offered without them
        self.guard = guard
        self.require_guard = require_guard
        # empty means no token (loopback only; see access.py)
        self.token = token
        self.workspace = workspace
