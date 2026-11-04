# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_access.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The optional Bearer token: none needed on loopback, mandatory away from it, constant-time comparison, every route guarded."""
from __future__ import annotations

import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

from hydra_umc_vla_engine.access import TOKEN_ENV, authorized, bind_problem, is_loopback, load_token
from hydra_umc_vla_engine.api import VlaEngineServer

TOKEN = "a-long-random-token-1234"


def test_loopback_detection() -> None:
    for addr in ("127.0.0.1", "127.9.9.9", "::1", "[::1]", "localhost"):
        assert is_loopback(addr), addr
    for addr in ("0.0.0.0", "::", "192.168.0.180", "example.com", "127.0.0.1.evil.example", ""):
        assert not is_loopback(addr), addr


def test_bind_problem_demands_a_token_away_from_loopback() -> None:
    assert bind_problem("127.0.0.1", "") is None
    assert bind_problem("0.0.0.0", TOKEN) is None
    assert "not loopback" in (bind_problem("0.0.0.0", "") or "")
    assert bind_problem("192.168.0.180", "") is not None


def test_load_token_from_file_environment_and_nothing(tmp_path: Path) -> None:
    assert load_token(None, {}) == ""
    assert load_token(None, {TOKEN_ENV: " " + TOKEN + " "}) == TOKEN
    file = tmp_path / "token"
    file.write_text(TOKEN + "  ", encoding="utf-8")
    # the file wins over the environment
    assert load_token(file, {TOKEN_ENV: "an-environment-token-9999"}) == TOKEN


def test_load_token_rejects_a_short_or_unreadable_token(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 16"):
        load_token(None, {TOKEN_ENV: "short"})
    with pytest.raises(ValueError, match="cannot read"):
        load_token(tmp_path / "missing", {})


class _Headers(dict):
    def get(self, key, default=""):  # type: ignore[override]
        return super().get(key, default)


class _Handler:
    def __init__(self, header: str | None) -> None:
        self.headers = _Headers({"Authorization": header} if header is not None else {})


def test_authorized_logic() -> None:
    assert authorized(_Handler(None), "")  # no token configured
    assert authorized(_Handler(f"Bearer {TOKEN}"), TOKEN)
    assert not authorized(_Handler(None), TOKEN)
    assert not authorized(_Handler("Bearer wrong-token-0000000"), TOKEN)
    assert not authorized(_Handler(f"Basic {TOKEN}"), TOKEN)
    assert not authorized(_Handler(TOKEN), TOKEN)
    assert not authorized(_Handler("Bearer "), TOKEN)


def _call(url: str, token: str | None, data: bytes | None = None) -> int:
    request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        error.read()
        return error.code


@contextmanager
def _running(token: str):
    server = VlaEngineServer(("127.0.0.1", 0), Path("."), token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_every_route_needs_the_token_when_one_is_set(tmp_path: Path) -> None:
    with _running(TOKEN) as base:
        # the health path of the manifest is the one route left open, for the service registry
        assert _call(f"{base}/health", None) == 200
        assert _call(f"{base}/nothing", None) == 401
        assert _call(f"{base}/nothing", "wrong-token-0000000") == 401
        assert _call(f"{base}/nothing", TOKEN) == 404
        # a POST without the token is refused before its body is even read
        assert _call(f"{base}/tokens/encode", None, b"{}") == 401


def test_no_token_configured_keeps_the_open_loopback_behaviour(tmp_path: Path) -> None:
    with _running("") as base:
        assert _call(f"{base}/nothing", None) == 404


def test_serve_refuses_a_non_loopback_address_without_a_token(capsys: pytest.CaptureFixture[str]) -> None:
    from hydra_umc_vla_engine.main import _build_parser, _cmd_serve

    args = _build_parser().parse_args(["serve", "--addr", "0.0.0.0", "--port", "0"])
    assert _cmd_serve(args) == 2
    assert "not loopback" in capsys.readouterr().err



# ---- the identity of HYDRA-UMC-SERVER (off by default; see server_identity.py)
IDENTITY_KEY = b"a-signing-key-of-the-server-0123456789"


def _signed_token(role: str = "operator", key: bytes = IDENTITY_KEY, exp_offset: int = 600) -> str:
    import base64
    import hashlib
    import hmac
    import json
    import time

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps({"username": "ana", "role": role, "exp": int(time.time()) + exp_offset}).encode())
    return f"{head}.{body}.{b64(hmac.new(key, f'{head}.{body}'.encode(), hashlib.sha256).digest())}"


@contextmanager
def _running_with_identity(token: str, key: bytes | None):
    server = VlaEngineServer(("127.0.0.1", 0), Path("."), token)
    server.identity_key = key
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_the_identity_of_the_server_is_off_by_default() -> None:
    assert VlaEngineServer.identity_key is None
    with _running_with_identity("", None) as base:
        assert _call(f"{base}/nothing", None) == 404  # open on loopback, as before
        assert _call(f"{base}/nothing", _signed_token()) == 404  # a token of the SERVER means nothing, and nothing is asked
    with _running_with_identity(TOKEN, None) as base:
        assert _call(f"{base}/nothing", _signed_token()) == 401
        assert _call(f"{base}/nothing", TOKEN) == 404


def test_with_the_identity_on_a_token_of_the_server_is_accepted_and_nothing_is_open() -> None:
    with _running_with_identity("", IDENTITY_KEY) as base:
        assert _call(f"{base}/nothing", None) == 401  # no credential, even on loopback and without a token of the service
        assert _call(f"{base}/nothing", "not-a-token") == 401
        assert _call(f"{base}/nothing", _signed_token("viewer")) == 404  # accepted: the path just does not exist
        assert _call(f"{base}/tokens/encode", _signed_token("viewer"), b"{}") == 401  # a viewer reads, it does not change
        assert _call(f"{base}/nothing", _signed_token(key=b"another-key-of-more-than-32-characters!")) == 401
        assert _call(f"{base}/nothing", _signed_token(exp_offset=-5)) == 401
    with _running_with_identity(TOKEN, IDENTITY_KEY) as base:
        assert _call(f"{base}/nothing", TOKEN) == 404  # the own token keeps working
        assert _call(f"{base}/nothing", _signed_token("admin")) == 404
