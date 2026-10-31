# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_shadow.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from hydra_umc_vla_engine.api import VlaEngineServer
from hydra_umc_vla_engine.shadow import ShadowError, ShadowPolicy, compare_actions, load_shadow_policy

P = [[0.03, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [0.0, 0.04, 0.0, 0.0, 0.0, 0.1, 1.0]]
O = [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]]


def test_identical_sequences_have_no_difference() -> None:
    result = compare_actions(P, P)
    assert result["summary"]["linear"] == {"mean": 0.0, "max": 0.0}
    assert result["authorized"] is False and result["compared_steps"] == 2


def test_measures_each_group() -> None:
    result = compare_actions(P, O)
    assert result["steps"][0]["linear"] == pytest.approx(0.03)
    assert result["steps"][1]["linear"] == pytest.approx(0.04)
    assert result["steps"][1]["rotation"] == pytest.approx(0.1)
    assert result["steps"][1]["gripper"] == 1.0
    assert result["summary"]["linear"]["mean"] == pytest.approx(0.035)
    assert result["summary"]["linear"]["max"] == pytest.approx(0.04)


def test_compares_the_common_length() -> None:
    result = compare_actions(P, O[:1])
    assert (result["compared_steps"], result["proposed_steps"], result["operator_steps"]) == (1, 2, 1)


@pytest.mark.parametrize("bad", [None, [], "x", [[0.0] * 6], [[True] + [0.0] * 6], [[float("inf")] + [0.0] * 6]])
def test_refuses_malformed_sequences(bad: object) -> None:
    with pytest.raises(ShadowError):
        compare_actions(bad, O)
    with pytest.raises(ShadowError):
        compare_actions(P, bad)


def test_policy_defaults_and_loading(tmp_path: Path) -> None:
    assert ShadowPolicy().enabled is False and ShadowPolicy().log_file == ""
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"shadow": {"enabled": True, "log_file": "x.jsonl"}}), encoding="utf-8")
    assert load_shadow_policy(cfg) == ShadowPolicy(True, "x.jsonl")
    cfg.write_text('{"shadow": {"enabled": "yes"}}', encoding="utf-8")
    with pytest.raises(ShadowError):
        load_shadow_policy(cfg)
    cfg.write_text('{"shadow": 1}', encoding="utf-8")
    with pytest.raises(ShadowError):
        load_shadow_policy(cfg)


def test_shipped_configuration_keeps_shadow_off() -> None:
    shipped = Path(__file__).resolve().parents[1] / "configs" / "vla-engine.json"
    assert load_shadow_policy(shipped).enabled is False


def _post(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _serve(server: VlaEngineServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_route_is_not_found_while_off(tmp_path: Path) -> None:
    server = VlaEngineServer(("127.0.0.1", 0), tmp_path)
    thread = _serve(server)
    try:
        status, _ = _post(f"http://127.0.0.1:{server.server_address[1]}/shadow/compare", {"proposed": P, "operator": O})
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_route_compares_and_logs_when_on(tmp_path: Path) -> None:
    log = tmp_path / "shadow.jsonl"
    server = VlaEngineServer(("127.0.0.1", 0), tmp_path, shadow=ShadowPolicy(True, str(log)))
    thread = _serve(server)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/shadow/compare"
        status, body = _post(url, {"proposed": P, "operator": O})
        assert status == 200 and body["authorized"] is False and body["compared_steps"] == 2
        status, body = _post(url, {"proposed": P})
        assert status == 400
        lines = log.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1 and json.loads(lines[0])["compared_steps"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
