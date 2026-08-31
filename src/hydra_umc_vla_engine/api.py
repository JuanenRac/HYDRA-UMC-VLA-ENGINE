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

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .action_tokens import DEFAULT_VOCAB_SIZE, TokenizationError, decode_action, encode_action
from .hardware import check_engine_status
from .trajectory import Pose, TrajectoryError, integrate_trajectory


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    def default(o: object) -> object:
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)
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


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    return json.loads(raw)


def _query_params(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    parsed = urlparse(handler.path)
    values = parse_qs(parsed.query, keep_blank_values=True)
    return {key: value[0] for key, value in values.items() if value}


class Handler(BaseHTTPRequestHandler):
    server: "VlaEngineServer"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # quiet by default, same reasoning as this family's other api.py files

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/status":
            params = _query_params(self)
            workspace = Path(params["workspace"]) if "workspace" in params else self.server.workspace
            status = check_engine_status(workspace)
            _write_json(self, 200, {
                "acceleratorPresent": status.accelerator_present,
                "modelWeightsPresent": status.model_weights_present,
                "mode": status.mode.value,
            })
        elif path == "/stats":
            _write_json(self, 200, {"workspace": str(self.server.workspace)})
        else:
            _write_error(self, 404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = _read_json_body(self)
        except json.JSONDecodeError as e:
            _write_error(self, 400, f"malformed JSON body: {e}")
            return
        if path == "/tokens/encode":
            self._handle_encode(body)
        elif path == "/tokens/decode":
            self._handle_decode(body)
        elif path == "/trajectory/integrate":
            self._handle_integrate(body)
        else:
            _write_error(self, 404, "not found")

    def _handle_encode(self, body: dict) -> None:
        try:
            action = tuple(float(v) for v in body["action"])
            vocab_size = int(body.get("vocab_size", DEFAULT_VOCAB_SIZE))
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
            tokens = tuple(int(v) for v in body["tokens"])
            vocab_size = int(body.get("vocab_size", DEFAULT_VOCAB_SIZE))
            values = decode_action(tokens, vocab_size=vocab_size)
        except KeyError as e:
            _write_error(self, 400, f"missing required field: {e}")
            return
        except (TokenizationError, ValueError, TypeError) as e:
            _write_error(self, 400, str(e))
            return
        _write_json(self, 200, {"action": list(values)})

    def _handle_integrate(self, body: dict) -> None:
        try:
            start_values = tuple(float(v) for v in body["start"])
            start = Pose(*start_values, gripper=float(body.get("start_gripper", 0.0)))
            actions_raw = body["actions"]
            if not isinstance(actions_raw, list):
                raise TrajectoryError("actions: expected a JSON array")
            actions = [tuple(a) for a in actions_raw]
            poses = integrate_trajectory(start, actions)
        except KeyError as e:
            _write_error(self, 400, f"missing required field: {e}")
            return
        except (TokenizationError, TrajectoryError, ValueError, TypeError) as e:
            _write_error(self, 400, str(e))
            return
        _write_json(self, 200, {"poses": [asdict(p) for p in poses]})


class VlaEngineServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], workspace: Path) -> None:
        super().__init__(address, Handler)
        self.workspace = workspace
