# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_confidence.py
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
from hydra_umc_vla_engine.confidence import (
    ConfidenceConfigError,
    ConfidencePolicy,
    load_confidence_policy,
    low_confidence_steps,
)

ON = ConfidencePolicy(0.6)


def test_off_by_default_accepts_anything() -> None:
    assert low_confidence_steps(None, 3, ConfidencePolicy()) == []


def test_reports_the_steps_below_the_minimum() -> None:
    assert low_confidence_steps([0.9, 0.59, 0.6, 0.1], 4, ON) == [1, 3]


@pytest.mark.parametrize("bad", [None, [0.9], "x", [0.9, True], [0.9, 2.0], [0.9, float("nan")]])
def test_fails_closed_on_missing_or_malformed(bad: object) -> None:
    with pytest.raises(ConfidenceConfigError):
        low_confidence_steps(bad, 2, ON)


@pytest.mark.parametrize("bad", [-0.1, 1.5, True, "0.5", float("inf")])
def test_policy_rejects_a_minimum_out_of_range(bad: object) -> None:
    with pytest.raises(ConfidenceConfigError):
        ConfidencePolicy(bad)  # type: ignore[arg-type]


def test_loads_from_the_configuration_file(tmp_path: Path) -> None:
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"rotation": {"frame": "tool"}, "confidence": {"minimum": 0.7}}), encoding="utf-8")
    assert load_confidence_policy(cfg).minimum == 0.7
    cfg.write_text("{}", encoding="utf-8")
    assert load_confidence_policy(cfg).enabled is False
    cfg.write_text('{"confidence": 3}', encoding="utf-8")
    with pytest.raises(ConfidenceConfigError):
        load_confidence_policy(cfg)
    with pytest.raises(ConfidenceConfigError):
        load_confidence_policy(tmp_path / "missing.json")


def _post(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_integrate_endpoint_applies_the_filter(tmp_path: Path) -> None:
    server = VlaEngineServer(("127.0.0.1", 0), tmp_path, confidence=ON)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/trajectory/integrate"
        base = {"start": [0, 0, 0, 0, 0, 0], "actions": [[0.01, 0, 0, 0, 0, 0, 0], [0.01, 0, 0, 0, 0, 0, 0]]}
        status, body = _post(url, {**base, "confidences": [0.9, 0.8]})
        assert status == 200 and len(body["poses"]) == 3
        status, body = _post(url, {**base, "confidences": [0.9, 0.2]})
        assert status == 422 and body["low_confidence_steps"] == [1] and "poses" not in body
        status, body = _post(url, base)
        assert status == 400 and "confidences" in body["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
