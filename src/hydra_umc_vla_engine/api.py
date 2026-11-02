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
from collections.abc import Callable, Sequence
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from .service_metrics import MetricsHandlerMixin
from .proposal_signing import sign_proposal
from .access import authorized, reject
from .guard import REJECTED, GuardLimits, guard_trajectory
from .http_common import DEFAULT_MAX_BODY_BYTES, DEFAULT_MAX_THREADS, SOCKET_TIMEOUT_SECONDS, BoundedThreadingHTTPServer, query_params, read_json_body, write_error, write_json
from .action_tokens import DEFAULT_VOCAB_SIZE, TokenizationError, decode_action, encode_action
from .confidence import ConfidenceConfigError, ConfidencePolicy, low_confidence_steps
from .consistency import ConsistencyConfigError, ConsistencyPolicy, inconsistent_steps
from .confirmation import ConfirmationError, ConfirmationStore, summarize
from .hardware import check_engine_status
from .kinematic_check import REACHABLE, UNAVAILABLE, KinematicResult, KinematicsPolicy, check_reach
from .shadow import ShadowError, ShadowPolicy, append_log, compare_actions
from .trajectory import Pose, TrajectoryError, integrate_trajectory


def _json_default(o: object) -> object:
    if hasattr(o, "__dataclass_fields__"):
        return asdict(o)  # type: ignore[call-overload]
    if hasattr(o, "value"):  # enum
        return o.value
    return str(o)


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    write_json(handler, status, payload, default=_json_default)


def _write_error(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    write_error(handler, status, message)


# The body of a request is bounded, NaN and the infinities are refused, an oversized body is drained in small pieces: http_common.py (the canonical
# copy lives in HYDRA-UMC-SDK and is shared by the Python services).
MAX_BODY_BYTES = DEFAULT_MAX_BODY_BYTES


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    return read_json_body(handler, MAX_BODY_BYTES)


def _query_params(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    return query_params(handler, "first")


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


class Handler(MetricsHandlerMixin, BaseHTTPRequestHandler):
    server: "VlaEngineServer"
    metrics_service = "hydra-umc-vla-engine"
    metrics_version = __version__

    # Seconds a client may stay silent on its connection before it is dropped,
    # so one that connects and sends nothing cannot hold a handler thread.
    timeout = SOCKET_TIMEOUT_SECONDS

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # quiet by default, same reasoning as this family's other api.py files

    def do_GET(self) -> None:  # noqa: N802
        if self.serve_metrics(authorized=authorized(self, self.server.token)):
            return
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
        elif path == "/confirmations/pending" and self.server.confirmations is not None:
            _write_json(self, 200, {"pending": self.server.confirmations.list()})
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
        elif path.startswith("/confirmations/") and path.count("/") == 3 and self.server.confirmations is not None:
            self._handle_confirmation(path.split("/")[2], path.split("/")[3], body)
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

    def _handle_confirmation(self, pending_id: str, action: str, body: dict) -> None:
        """The two steps of the confirmation of a proposal (confirmation.py): prepare -> the summary and a token; confirm -> the signed approval; reject."""
        store = self.server.confirmations
        assert store is not None
        if not isinstance(body, dict):
            _write_error(self, 400, "the body must be a JSON object")
            return
        try:
            if action == "prepare":
                result = store.prepare(pending_id, body.get("operator"))
            elif action == "confirm":
                result = store.confirm(pending_id, body.get("operator"), body.get("confirmationToken"))
            elif action == "reject":
                result = store.reject(pending_id, body.get("operator"))
            else:
                _write_error(self, 404, "not found")
                return
        except ConfirmationError as e:
            _write_error(self, e.status, str(e))
            return
        _write_json(self, 200, result)

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
        kinematics_info: dict | None = None
        if self.server.kinematics.enabled:
            reach: KinematicResult = self.server.kinematic_runner(poses, self.server.kinematics)
            kinematics_info = reach.as_dict()
            if reach.outcome != REACHABLE:
                refused = reach.outcome != UNAVAILABLE or self.server.kinematics.fail_closed
                if refused:
                    # a trajectory the robot cannot follow (or that could not be checked while the check is required) is not shown as a proposal at all
                    _write_json(self, 422 if reach.outcome != UNAVAILABLE else 503, {"error": "the kinematic check did not pass", "kinematics": kinematics_info, "guard": guard_info})
                    return
        pose_dicts = [asdict(p) for p in poses]
        proposal = proposal_record(pose_dicts, self.server.proposal_signer, model_version=self.server.model_version, instruction_sha256=instruction_sha256)
        answer: dict = {"poses": pose_dicts, "guard": guard_info, "proposal": proposal}
        if kinematics_info is not None:
            answer["kinematics"] = kinematics_info
        if self.server.confirmations is not None:
            # the proposal waits for a person (two steps, confirmation.py); nothing here marks it as approved
            proposal["confirmation"] = self.server.confirmations.create(
                proposal["fingerprint"], summarize(poses, robot_id=self.server.confirmations.robot_id, guard=guard_info, kinematics=kinematics_info),
            )
        _write_json(self, 200, answer)


class VlaEngineServer(BoundedThreadingHTTPServer):
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
        kinematics: KinematicsPolicy | None = None,
        kinematic_runner: Callable[[Sequence[Pose], KinematicsPolicy], KinematicResult] = check_reach,
        confirmations: ConfirmationStore | None = None,
        max_threads: int = DEFAULT_MAX_THREADS,
    ) -> None:
        super().__init__(address, Handler, max_threads)
        # the check of the reach of the robot (kinematic_check.py); off by default. The runner can be replaced, so the tests do not need the program
        self.kinematics = kinematics or KinematicsPolicy()
        self.kinematic_runner = kinematic_runner
        # the two-step confirmation of the proposals (confirmation.py); None leaves its routes answering 404 and the proposals as they were
        self.confirmations = confirmations
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
