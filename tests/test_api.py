# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_api.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real end-to-end HTTP tests: a real VlaEngineServer (ThreadingHTTPServer)
hit with real urllib requests - same convention as this family's other
test_api.py files."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from hydra_umc_vla_engine.api import VlaEngineServer


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(url: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@contextmanager
def running_server(workspace: Path) -> Iterator[str]:
    server = VlaEngineServer(("127.0.0.1", 0), workspace)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_tokens_encode_and_decode_roundtrip(tmp_path: Path) -> None:
    action = [0.01, -0.01, 0.0, 0.0, 0.0, 0.0, 0.5]
    with running_server(tmp_path) as base:
        status, body = _post(f"{base}/tokens/encode", {"action": action})
        assert status == 200
        assert len(body["tokens"]) == 7

        status, body2 = _post(f"{base}/tokens/decode", {"tokens": body["tokens"]})
        assert status == 200
        assert len(body2["action"]) == 7


def test_tokens_encode_rejects_wrong_dimension(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        status, body = _post(f"{base}/tokens/encode", {"action": [0.0, 0.0]})
        assert status == 400


def test_tokens_encode_missing_field(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        status, body = _post(f"{base}/tokens/encode", {})
        assert status == 400


def test_trajectory_integrate(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        status, body = _post(f"{base}/trajectory/integrate", {
            "start": [0, 0, 0, 0, 0, 0],
            "actions": [[0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]],
        })
        assert status == 200
        # integrate_trajectory() returns the start pose too (poses[0]),
        # then one entry per action - len(actions) + 1, not len(actions).
        assert len(body["poses"]) == 2
        assert body["poses"][0]["x"] == 0.0
        assert body["poses"][1]["x"] == 0.01
        assert body["poses"][1]["gripper"] == 1.0


def test_trajectory_integrate_accumulates_over_multiple_steps(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        status, body = _post(f"{base}/trajectory/integrate", {
            "start": [0, 0, 0, 0, 0, 0],
            "actions": [
                [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            ],
        })
        assert status == 200
        assert len(body["poses"]) == 3
        assert body["poses"][-1]["x"] == 0.02


def test_trajectory_integrate_rejects_malformed_start(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        status, body = _post(f"{base}/trajectory/integrate", {"start": [0, 0], "actions": []})
        assert status == 400


def test_status_no_accelerator_on_this_dev_machine(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        status, body = _get(f"{base}/status")
        assert status == 200
        assert body["acceleratorPresent"] is False
        assert body["mode"] == "no_accelerator"


def test_status_workspace_override(tmp_path: Path) -> None:
    other = tmp_path / "other"
    with running_server(tmp_path) as base:
        status, body = _get(f"{base}/status?workspace={other}")
        assert status == 200
        assert "mode" in body


def test_stats(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        status, body = _get(f"{base}/stats")
        assert status == 200
        assert body["workspace"] == str(tmp_path)


def test_not_found(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        status, body = _get(f"{base}/nope")
        assert status == 404


def test_malformed_json_body_rejected(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        req = urllib.request.Request(f"{base}/tokens/encode", data=b"{not json", method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "expected HTTPError"
        except urllib.error.HTTPError as e:
            assert e.code == 400
