# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_consistency.py
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
from hydra_umc_vla_engine.consistency import (
    ConsistencyConfigError,
    ConsistencyPolicy,
    inconsistent_steps,
    load_consistency_policy,
)

ON = ConsistencyPolicy(predictions=3)
A = [(0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), (0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)]


def test_off_by_default_accepts_anything() -> None:
    assert ConsistencyPolicy().enabled is False
    assert inconsistent_steps(A, None, ConsistencyPolicy()) == []


def test_agreeing_predictions_pass() -> None:
    same = [list(a) for a in A]
    near = [[0.012, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.95]]
    assert inconsistent_steps(A, [same, near], ON) == []


def test_reports_each_disagreeing_step_once() -> None:
    far_linear = [[0.04, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]]
    far_gripper = [[0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5]]
    far_both = [[0.04, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]]
    assert inconsistent_steps(A, [far_linear, far_gripper], ON) == [0, 1]
    assert inconsistent_steps(A, [far_linear, far_both], ON) == [0]


def test_rotation_uses_its_own_tolerance() -> None:
    rot = [[0.01, 0.0, 0.0, 0.05, 0.0, 0.0, 0.0], [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]]
    assert inconsistent_steps(A, [rot, rot], ON) == [0]
    loose = ConsistencyPolicy(3, {"linear": 0.005, "rotation": 0.1, "gripper": 0.1})
    assert inconsistent_steps(A, [rot, rot], loose) == []


@pytest.mark.parametrize(
    "bad",
    [None, [], "x", [[[0.0] * 7] * 2], [[[0.0] * 7], [[0.0] * 7]], [[[0.0] * 6] * 2] * 2, [[[True] + [0.0] * 6] * 2] * 2, [[[float("nan")] + [0.0] * 6] * 2] * 2],
)
def test_fails_closed_on_missing_or_malformed(bad: object) -> None:
    with pytest.raises(ConsistencyConfigError):
        inconsistent_steps(A, bad, ON)


@pytest.mark.parametrize("bad", [0, 17, True, 2.5, "3"])
def test_policy_rejects_predictions_out_of_range(bad: object) -> None:
    with pytest.raises(ConsistencyConfigError):
        ConsistencyPolicy(predictions=bad)  # type: ignore[arg-type]


def test_policy_rejects_a_bad_tolerance() -> None:
    with pytest.raises(ConsistencyConfigError):
        ConsistencyPolicy(2, {"linear": -1.0, "rotation": 0.01, "gripper": 0.1})
    with pytest.raises(ConsistencyConfigError):
        ConsistencyPolicy(2, {"linear": 0.01})


def test_loads_from_the_configuration_file(tmp_path: Path) -> None:
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"consistency": {"predictions": 2, "tolerance": {"linear": 0.02}}}), encoding="utf-8")
    policy = load_consistency_policy(cfg)
    assert policy.predictions == 2 and policy.tolerance["linear"] == 0.02 and policy.tolerance["rotation"] == 0.01
    cfg.write_text("{}", encoding="utf-8")
    assert load_consistency_policy(cfg).enabled is False
    cfg.write_text('{"consistency": 3}', encoding="utf-8")
    with pytest.raises(ConsistencyConfigError):
        load_consistency_policy(cfg)
    with pytest.raises(ConsistencyConfigError):
        load_consistency_policy(tmp_path / "missing.json")


def test_shipped_configuration_keeps_the_filter_off() -> None:
    shipped = Path(__file__).resolve().parents[1] / "configs" / "vla-engine.json"
    assert load_consistency_policy(shipped).enabled is False


def _post(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_integrate_endpoint_applies_the_filter(tmp_path: Path) -> None:
    server = VlaEngineServer(("127.0.0.1", 0), tmp_path, consistency=ON)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/trajectory/integrate"
        actions = [list(a) for a in A]
        base = {"start": [0, 0, 0, 0, 0, 0], "actions": actions}
        status, body = _post(url, {**base, "alternatives": [actions, actions]})
        assert status == 200 and len(body["poses"]) == 3
        off = [[0.04, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], actions[1]]
        status, body = _post(url, {**base, "alternatives": [actions, off]})
        assert status == 422 and body["inconsistent_steps"] == [0] and "poses" not in body
        status, body = _post(url, base)
        assert status == 400 and "alternatives" in body["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_integrate_endpoint_unchanged_while_off(tmp_path: Path) -> None:
    server = VlaEngineServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/trajectory/integrate"
        status, body = _post(url, {"start": [0, 0, 0, 0, 0, 0], "actions": [list(A[0])], "alternatives": [[[9.0] * 7]]})
        assert status == 200 and set(body) == {"poses", "guard", "proposal"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
