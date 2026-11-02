# =============================================================================
# HYDRA-UMC-SDK - tools/canonical/http_common.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""What every Python service of the family that answers with the standard library HTTP server does the same way, written once.

This file has a single canonical copy (`tools/canonical/http_common.py` of HYDRA-UMC-SDK) that is vendored, byte for byte, into the Python services that list
it in `PER_REPOSITORY_FILES` of `tools/sync_repo_tools.py`, which keeps the copies identical. A service uses the parts it needs:

* `read_json_body` / `read_json_object`: the body of a request as JSON, bounded. A `Content-Length` that is not a number, negative or above the limit is refused
  (an oversized body is read and thrown away in small pieces, up to a cap, so that the client can finish sending before the answer goes out and nothing large is
  held in memory); `NaN` and `Infinity`, which are not JSON, are refused instead of reaching the arithmetic of the service as numbers; a body that is not UTF-8 is a
  `ValueError` like any other malformed body. A service answers every `ValueError` of these functions with a 400.
* `write_json` / `write_error`: a JSON answer with its length. `write_json` takes a `default` for what `json` cannot write by itself.
* `query_params`: the query string as a dictionary, either refusing a name that occurs twice (the default) or taking the first.
* `bearer_matches` / `reject_unauthorized`: the optional bearer token, compared in constant time; an empty token means no token (a service lets that happen only
  on loopback, see its `access.py`).
* `BoundedThreadingHTTPServer`: the threading HTTP server with a limit on the number of requests handled at the same time. One more answers `503` with
  `Retry-After` at once instead of starting another thread, so a client that opens many connections cannot grow the service without bound.
* `SOCKET_TIMEOUT_SECONDS`: the value for the `timeout` attribute of a handler, the seconds a client may stay silent on its connection before it is dropped.
"""
from __future__ import annotations

import hmac
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

SOCKET_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
DRAIN_FACTOR = 16
DEFAULT_MAX_THREADS = 32


def reject_constant(name: str) -> float:
    """`parse_constant` for `json.loads`: NaN and the infinities are not JSON numbers."""
    raise ValueError(f"{name} is not a valid JSON number")


def _discard(rfile: Any, length: int, chunk: int = 64 * 1024) -> None:
    remaining = length
    while remaining > 0:
        block = rfile.read(min(chunk, remaining))
        if not block:
            return
        remaining -= len(block)


def read_json_body(handler: BaseHTTPRequestHandler, max_bytes: int = DEFAULT_MAX_BODY_BYTES, empty: Any = None) -> Any:
    """The body of the request as JSON. An absent body gives `empty` (`{}` when `empty` is None). Raises `ValueError` (`json.JSONDecodeError` is one) for anything else."""
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except ValueError as error:
        raise ValueError("Content-Length must be an integer") from error
    if length < 0 or length > max_bytes:
        if 0 <= length <= max_bytes * DRAIN_FACTOR:
            _discard(handler.rfile, length)
        raise ValueError(f"request body must contain 0-{max_bytes} bytes")
    if length == 0:
        return {} if empty is None else empty
    return json.loads(handler.rfile.read(length), parse_constant=reject_constant)


def read_json_object(handler: BaseHTTPRequestHandler, max_bytes: int = DEFAULT_MAX_BODY_BYTES) -> dict[str, Any]:
    """Like `read_json_body`, and the body must be a JSON object (a list, a string, a number or null is a `ValueError`)."""
    body = read_json_body(handler, max_bytes)
    if not isinstance(body, dict):
        raise ValueError(f"the body must be a JSON object, not {type(body).__name__}")
    return body


def write_json(handler: BaseHTTPRequestHandler, status: int, payload: object, default: Callable[[Any], Any] | None = None) -> None:
    body = json.dumps(payload, default=default).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def write_error(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    write_json(handler, status, {"error": message})


def query_params(handler: BaseHTTPRequestHandler, repeated: str = "error") -> dict[str, str]:
    """The query string as a dictionary. With `repeated="error"` (the default) a name that occurs more than once raises `ValueError`; with `"first"` the first value wins."""
    values = parse_qs(urlparse(handler.path).query, keep_blank_values=True)
    if repeated == "error":
        twice = sorted(key for key, value in values.items() if len(value) != 1)
        if twice:
            raise ValueError(f"query parameters must occur exactly once: {twice}")
    return {key: value[0] for key, value in values.items() if value}


def bearer_matches(handler: BaseHTTPRequestHandler, expected: str) -> bool:
    """True when no token is configured (`expected` is empty), or the request presents exactly that bearer token. The comparison takes constant time."""
    if not expected:
        return True
    scheme, _, presented = handler.headers.get("Authorization", "").partition(" ")
    return scheme == "Bearer" and hmac.compare_digest(presented.strip().encode("utf-8"), expected.encode("utf-8"))


def reject_unauthorized(handler: BaseHTTPRequestHandler) -> None:
    """Answer 401 for a request that did not present the token."""
    body = b'{"error": "a valid bearer token is required"}'
    handler.send_response(401)
    handler.send_header("WWW-Authenticate", "Bearer")
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that handles at most `max_threads` requests at the same time; one more is answered `503` and closed without a thread of its own."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], max_threads: int = DEFAULT_MAX_THREADS) -> None:
        if isinstance(max_threads, bool) or not isinstance(max_threads, int) or not 1 <= max_threads <= 1024:
            raise ValueError(f"max_threads must be an integer from 1 to 1024, got {max_threads!r}")
        super().__init__(address, handler)
        self.max_threads = max_threads
        self.refused = 0
        self._slots = threading.BoundedSemaphore(max_threads)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._slots.acquire(blocking=False):
            self.refused += 1
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nRetry-After: 1\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                # close our side, then read for an instant what the client already sent: a connection closed with unread data is reset, and the
                # client would lose the 503 it is waiting for. (A short wait: this runs in the thread that accepts connections.)
                request.shutdown(socket.SHUT_WR)
                request.settimeout(0.05)
                request.recv(4096)
            except OSError:
                pass
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()
