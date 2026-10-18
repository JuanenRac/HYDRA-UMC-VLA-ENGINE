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

import pytest

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
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=5)
        assert caught.value.code == 400


def test_oversized_content_length_rejected(tmp_path: Path) -> None:
    # Real regression: _read_json_body() used to read a caller-controlled
    # Content-Length with no upper bound at all - a client claiming a
    # multi-gigabyte body would make the handler block reading (and
    # buffering) that many bytes. This sends a real, just-over-the-limit
    # body (still small - just over 1 MiB, not gigabytes) and proves the
    # server rejects it with a clean 400 rather than accepting it.
    from hydra_umc_vla_engine.api import MAX_BODY_BYTES

    with running_server(tmp_path) as base:
        oversized = b"x" * (MAX_BODY_BYTES + 1)
        req = urllib.request.Request(f"{base}/tokens/encode", data=oversized, method="POST")
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=5)
        assert caught.value.code == 400
        assert "0-" in caught.value.read().decode()


def test_an_integrated_trajectory_is_a_proposal_bound_to_its_poses(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        first = _post(f"{base}/trajectory/integrate", {"start": [0, 0, 0, 0, 0, 0], "actions": [[0.05, 0, 0, 0, 0, 0, 0]]})[1]
        again = _post(f"{base}/trajectory/integrate", {"start": [0, 0, 0, 0, 0, 0], "actions": [[0.05, 0, 0, 0, 0, 0, 0]]})[1]
        other = _post(f"{base}/trajectory/integrate", {"start": [0, 0, 0, 0, 0, 0], "actions": [[0.04, 0, 0, 0, 0, 0, 0]]})[1]
    assert first["proposal"]["authorized"] is False
    assert len(first["proposal"]["fingerprint"]) == 64
    assert first["proposal"]["fingerprint"] == again["proposal"]["fingerprint"]
    assert first["proposal"]["fingerprint"] != other["proposal"]["fingerprint"]



def _post_raw(url: str, raw: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_a_nan_model_output_is_refused_not_turned_into_the_maximum_movement(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        # the literal NaN (not valid JSON, but accepted by json.loads), the string "nan" (accepted by float()) and infinity
        for raw in (b'{"action": [NaN, 0, 0, 0, 0, 0, 0]}', b'{"action": ["nan", 0, 0, 0, 0, 0, 0]}', b'{"action": [Infinity, 0, 0, 0, 0, 0, 0]}', b'{"action": [0, 0, 0, 0, 0, 0, "inf"]}'):
            status, body = _post_raw(f"{base}/tokens/encode", raw)
            assert status == 400, raw
            assert "error" in body


def test_a_bad_vocab_size_is_a_400_not_a_crashed_handler(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        for vocab in (0, -5, 1, 1000000):
            status, body = _post(f"{base}/tokens/encode", {"action": [0.0] * 7, "vocab_size": vocab})
            assert status == 400, vocab
        status, _ = _post(f"{base}/tokens/decode", {"tokens": [0] * 7, "vocab_size": 0})
        assert status == 400
        # and the server is still serving
        status, _ = _post(f"{base}/tokens/encode", {"action": [0.0] * 7})
        assert status == 200


def test_deltas_outside_the_action_space_are_a_400(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        status, body = _post(f"{base}/trajectory/integrate", {"start": [0, 0, 0, 0, 0, 0], "actions": [[10, 0, -5, 3, 0, 0, 7]] * 3})
    assert status == 400
    assert "action space" in body["error"]


def test_strict_types_on_encode_decode_and_integrate(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        assert _post(f"{base}/tokens/encode", {"action": [True, 0, 0, 0, 0, 0, 0]})[0] == 400
        assert _post(f"{base}/tokens/encode", {"action": ["0.01", 0, 0, 0, 0, 0, 0]})[0] == 400
        assert _post(f"{base}/tokens/decode", {"tokens": [128.7] * 7})[0] == 400
        assert _post(f"{base}/tokens/decode", {"tokens": ["7"] * 7})[0] == 400
        assert _post(f"{base}/tokens/decode", {"tokens": [128] * 7, "vocab_size": 2.9})[0] == 400
        assert _post(f"{base}/trajectory/integrate", {"start": ["0"] * 6, "actions": []})[0] == 400


def test_the_workspace_override_stays_inside_the_servers_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with running_server(workspace) as base:
        status, _ = _get(f"{base}/status?workspace={outside}")
        assert status == 400
        status, _ = _get(f"{base}/status?workspace={workspace}")
        assert status == 200


def test_health_answers_ok(tmp_path: Path) -> None:
    with running_server(tmp_path) as base:
        assert _get(f"{base}/health") == (200, {"ok": True})


def test_the_handler_has_a_socket_timeout() -> None:
    from hydra_umc_vla_engine.api import Handler

    assert Handler.timeout is not None and Handler.timeout > 0
