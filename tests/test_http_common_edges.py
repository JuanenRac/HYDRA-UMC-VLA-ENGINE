# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_http_common_edges.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The edges of the HTTP helpers every service of the family shares: a body that is too long, not a number, not JSON, not UTF-8 or not an object; a query string
that repeats a name; the bearer token; and the server that refuses the request after its limit with a 503 instead of starting another thread."""
from __future__ import annotations

import io
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler

import pytest

from hydra_umc_vla_engine import http_common as hc


class _Fake:
    """Enough of a request handler for the helpers: headers, a body to read, a place to write, a path."""

    def __init__(self, body: bytes = b"", headers: dict[str, str] | None = None, path: str = "/") -> None:
        self.headers = dict(headers or {})
        if body and "Content-Length" not in self.headers:
            self.headers["Content-Length"] = str(len(body))
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.path = path
        self.status: int | None = None
        self.sent: list[tuple[str, str]] = []

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        self.sent.append((name, value))

    def end_headers(self) -> None:
        pass


def test_an_absent_body_is_an_empty_object_or_what_the_caller_asked_for():
    assert hc.read_json_body(_Fake()) == {}
    assert hc.read_json_body(_Fake(), empty=[]) == []


@pytest.mark.parametrize("length", ["abc", "-1", "1.5"])
def test_a_content_length_that_is_not_a_whole_non_negative_number_is_refused(length):
    with pytest.raises(ValueError):
        hc.read_json_body(_Fake(b"{}", {"Content-Length": length}))


def test_a_body_over_the_limit_is_refused_and_thrown_away_so_the_client_can_finish():
    fake = _Fake(b"x" * 300, {"Content-Length": "300"})
    with pytest.raises(ValueError, match="0-100"):
        hc.read_json_body(fake, max_bytes=100)
    assert fake.rfile.read() == b""  # the whole body was read and discarded


def test_a_body_far_over_the_limit_is_not_even_read():
    fake = _Fake(b"x" * 64, {"Content-Length": str(100 * hc.DRAIN_FACTOR + 1)})
    with pytest.raises(ValueError):
        hc.read_json_body(fake, max_bytes=100)
    assert len(fake.rfile.read()) == 64  # nothing was drained: a client that claims this much is cut off


def test_a_short_body_that_ends_before_its_length_does_not_hang_the_discard():
    fake = _Fake(b"x" * 10, {"Content-Length": "300"})
    with pytest.raises(ValueError):
        hc.read_json_body(fake, max_bytes=100)


@pytest.mark.parametrize("body", [b"{", b"\xff\xfe", b'{"a": NaN}', b'{"a": Infinity}', b'{"a": -Infinity}'])
def test_a_body_that_is_not_json_or_has_a_non_number_is_a_value_error(body):
    with pytest.raises(ValueError):
        hc.read_json_body(_Fake(body))


def test_an_object_is_required_where_the_service_asks_for_one():
    assert hc.read_json_object(_Fake(b'{"a": 1}')) == {"a": 1}
    for body in (b"[1]", b'"text"', b"3", b"null"):
        with pytest.raises(ValueError, match="JSON object"):
            hc.read_json_object(_Fake(body))


def test_the_answers_carry_their_length_and_the_error_has_one_field():
    fake = _Fake()
    hc.write_json(fake, 201, {"ok": True})
    assert fake.status == 201 and ("Content-Length", str(len(fake.wfile.getvalue()))) in fake.sent
    error = _Fake()
    hc.write_error(error, 418, "teapot")
    assert error.status == 418 and error.wfile.getvalue() == b'{"error": "teapot"}'


def test_write_json_uses_the_default_for_what_json_cannot_write():
    fake = _Fake()
    hc.write_json(fake, 200, {"x": {1, 2}}, default=lambda value: sorted(value))
    assert fake.wfile.getvalue() == b'{"x": [1, 2]}'


def test_the_query_string_refuses_a_repeated_name_unless_the_first_is_wanted():
    assert hc.query_params(_Fake(path="/a?x=1&y=2")) == {"x": "1", "y": "2"}
    assert hc.query_params(_Fake(path="/a?x=")) == {"x": ""}
    with pytest.raises(ValueError, match="exactly once"):
        hc.query_params(_Fake(path="/a?x=1&x=2"))
    assert hc.query_params(_Fake(path="/a?x=1&x=2"), repeated="first") == {"x": "1"}
    assert hc.query_params(_Fake(path="/a")) == {}


@pytest.mark.parametrize(
    ("header", "expected", "ok"),
    [
        ("Bearer secret", "secret", True),
        ("Bearer  secret ", "secret", True),
        ("Bearer wrong", "secret", False),
        ("Basic secret", "secret", False),
        ("bearer secret", "secret", False),
        ("secret", "secret", False),
        ("", "secret", False),
        ("", "", True),
        ("Bearer anything", "", True),
    ],
)
def test_the_bearer_token_is_checked_exactly_and_an_empty_token_means_no_token(header, expected, ok):
    headers = {"Authorization": header} if header else {}
    assert hc.bearer_matches(_Fake(headers=headers), expected) is ok


def test_an_unauthorized_request_gets_a_401_that_asks_for_a_bearer_token():
    fake = _Fake()
    hc.reject_unauthorized(fake)
    assert fake.status == 401 and ("WWW-Authenticate", "Bearer") in fake.sent and b"bearer token" in fake.wfile.getvalue()


@pytest.mark.parametrize("threads", [0, -1, 1025, True, 1.5, "8"])
def test_the_limit_of_threads_must_be_a_whole_number_from_one_to_1024(threads):
    with pytest.raises(ValueError, match="max_threads"):
        hc.BoundedThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler, threads)


def test_a_request_over_the_limit_is_answered_503_at_once_and_the_slot_comes_back():
    release = threading.Event()
    entered = threading.Event()

    class Slow(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def do_GET(self) -> None:  # noqa: N802
            entered.set()
            release.wait(5)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    server = hc.BoundedThreadingHTTPServer(("127.0.0.1", 0), Slow, max_threads=1)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def get() -> bytes:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
            connection.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            data = b""
            while chunk := connection.recv(4096):
                data += chunk
            return data

    first: list[bytes] = []
    holder = threading.Thread(target=lambda: first.append(get()))
    holder.start()
    try:
        assert entered.wait(5)
        refused = get()
        assert refused.startswith(b"HTTP/1.1 503") and b"Retry-After: 1" in refused and server.refused == 1
        release.set()
        holder.join(5)
        assert first and first[0].startswith(b"HTTP/1.0 200") or first[0].startswith(b"HTTP/1.1 200")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not get().startswith((b"HTTP/1.0 200", b"HTTP/1.1 200")):
            time.sleep(0.05)
        assert server.refused >= 1
    finally:
        release.set()
        server.shutdown()
        server.server_close()
