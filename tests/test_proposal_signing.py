# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_proposal_signing.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A signed proposal is tied to a trajectory, a robot and a short time window."""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

from hydra_umc_vla_engine import main as main_module
from hydra_umc_vla_engine.api import VlaEngineServer, proposal_record
from hydra_umc_vla_engine.proposal_signing import (
    MAX_VALIDITY_MS,
    ProposalKeyError,
    load_key,
    sign_proposal,
    verify_proposal,
)

KEY = b"k" * 32
NOW = 1_700_000_000_000
POSES = [{"x": 0.0, "y": 0.0, "z": 0.0}, {"x": 0.1, "y": 0.0, "z": 0.0}]


def _record(**changes) -> dict:
    record = proposal_record(POSES, (KEY, "robot-1", 30_000)) if not changes.pop("fixed", False) else {}
    record.update(changes)
    return record


def _signed_at(now: int = NOW) -> dict:
    fingerprint = proposal_record(POSES)["fingerprint"]
    return {"fingerprint": fingerprint, **sign_proposal(KEY, fingerprint, "robot-1", validity_ms=30_000, now_ms=now)}


def test_without_a_signer_the_record_is_as_before() -> None:
    record = proposal_record(POSES)
    assert set(record) == {"authorized", "fingerprint", "requires"} and record["authorized"] is False


def test_with_a_signer_the_record_carries_robot_window_and_signature() -> None:
    record = proposal_record(POSES, (KEY, "robot-1", 30_000))
    assert record["authorized"] is False and record["robot_id"] == "robot-1"
    assert record["expires_at_ms"] - record["issued_at_ms"] == 30_000
    assert verify_proposal(KEY, record, expected_robot_id="robot-1") == (True, "")


def test_a_fresh_proposal_verifies_and_every_change_or_delay_does_not() -> None:
    proposal = _signed_at()
    assert verify_proposal(KEY, proposal, expected_robot_id="robot-1", now_ms=NOW + 1000) == (True, "")
    for field, value in (("fingerprint", "f" * 64), ("robot_id", "robot-2"), ("expires_at_ms", NOW + 999_999), ("signature", "0" * 64)):
        ok, why = verify_proposal(KEY, {**proposal, field: value}, expected_robot_id="robot-1", now_ms=NOW + 1000)
        assert not ok and why, field
    assert "expired" in verify_proposal(KEY, proposal, expected_robot_id="robot-1", now_ms=NOW + 31_000)[1]
    assert "future" in verify_proposal(KEY, proposal, expected_robot_id="robot-1", now_ms=NOW - 60_000)[1]
    assert "different robot" in verify_proposal(KEY, proposal, expected_robot_id="robot-2", now_ms=NOW + 1000)[1]
    assert "different robot" in verify_proposal(KEY, proposal, expected_robot_id="", now_ms=NOW + 1000)[1]


@pytest.mark.parametrize("missing", ["fingerprint", "robot_id", "issued_at_ms", "expires_at_ms", "signature"])
def test_a_proposal_missing_any_signed_field_is_refused(missing: str) -> None:
    proposal = _signed_at()
    proposal.pop(missing)
    assert verify_proposal(KEY, proposal, expected_robot_id="robot-1", now_ms=NOW + 1000)[0] is False


def test_the_validity_has_a_ceiling_and_the_robot_is_required() -> None:
    with pytest.raises(ValueError):
        sign_proposal(KEY, "a" * 64, "robot-1", validity_ms=MAX_VALIDITY_MS + 1)
    with pytest.raises(ValueError):
        sign_proposal(KEY, "a" * 64, " ")


def test_the_key_file_must_exist_and_be_long_enough(tmp_path: Path) -> None:
    with pytest.raises(ProposalKeyError):
        load_key(tmp_path / "missing")
    short = tmp_path / "short"
    short.write_bytes(b"abc")
    with pytest.raises(ProposalKeyError):
        load_key(short)


@contextmanager
def _server(tmp_path: Path, **kwargs):
    server = VlaEngineServer(("127.0.0.1", 0), tmp_path, **kwargs)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _integrate(base: str) -> dict:
    body = {"start": [0, 0, 0, 0, 0, 0], "actions": [[0.01, 0, 0, 0, 0, 0, 0]]}
    req = urllib.request.Request(f"{base}/trajectory/integrate", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def test_the_service_signs_only_when_it_has_a_signer(tmp_path: Path) -> None:
    with _server(tmp_path) as base:
        assert "signature" not in _integrate(base)["proposal"]
    with _server(tmp_path, proposal_signer=(KEY, "robot-1", 30_000)) as base:
        proposal = _integrate(base)["proposal"]
        assert verify_proposal(KEY, proposal, expected_robot_id="robot-1") == (True, "")
        assert verify_proposal(KEY, proposal, expected_robot_id="robot-2")[0] is False


def test_serve_needs_a_robot_and_a_readable_key_with_the_switch(tmp_path: Path, monkeypatch) -> None:
    key_file = tmp_path / "proposal.key"
    key_file.write_bytes(KEY)
    for argv in (
        ["serve", "--proposal-key-file", str(key_file)],
        ["serve", "--proposal-key-file", str(tmp_path / "none"), "--robot-id", "r"],
    ):
        monkeypatch.setattr(sys, "argv", ["hydra-umc-vla-engine", *argv])
        assert main_module.main() == 2


def _bound(**kwargs) -> dict:
    fingerprint = "f" * 64
    record = {"fingerprint": fingerprint}
    record.update(sign_proposal(KEY, fingerprint, "robot-1", validity_ms=30_000, now_ms=NOW, **kwargs))
    return record


def test_the_model_and_the_instruction_are_part_of_what_is_signed() -> None:
    record = _bound(model_version="vla-1.2", instruction_sha256="a" * 64)
    assert verify_proposal(KEY, record, expected_robot_id="robot-1", now_ms=NOW + 1) == (True, "")
    assert verify_proposal(KEY, record, expected_robot_id="robot-1", now_ms=NOW + 1, expected_model_version="vla-1.2", expected_instruction_sha256="a" * 64)[0]
    ok, why = verify_proposal(KEY, record, expected_robot_id="robot-1", now_ms=NOW + 1, expected_model_version="vla-9")
    assert not ok and "model" in why
    ok, why = verify_proposal(KEY, record, expected_robot_id="robot-1", now_ms=NOW + 1, expected_instruction_sha256="b" * 64)
    assert not ok and "instruction" in why


@pytest.mark.parametrize("field, value", [("model_version", "vla-9"), ("instruction_sha256", "b" * 64)])
def test_changing_a_bound_field_breaks_the_signature(field: str, value: str) -> None:
    record = _bound(model_version="vla-1.2", instruction_sha256="a" * 64)
    record[field] = value
    assert verify_proposal(KEY, record, expected_robot_id="robot-1", now_ms=NOW + 1)[0] is False


def test_removing_a_bound_field_breaks_the_signature() -> None:
    record = _bound(model_version="vla-1.2")
    del record["model_version"]
    assert verify_proposal(KEY, record, expected_robot_id="robot-1", now_ms=NOW + 1)[0] is False


def test_the_integrate_route_signs_the_model_and_the_instruction(tmp_path: Path) -> None:
    server = VlaEngineServer(("127.0.0.1", 0), tmp_path, proposal_signer=(KEY, "robot-1", 30_000), model_version="vla-1.2")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/trajectory/integrate"

        def call(body: dict):
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        base = {"start": [0, 0, 0, 0, 0, 0], "actions": [[0.01, 0, 0, 0, 0, 0, 0]]}
        status, answer = call({**base, "instruction_sha256": "c" * 64})
        assert status == 200, answer
        proposal = answer["proposal"]
        assert proposal["model_version"] == "vla-1.2" and proposal["instruction_sha256"] == "c" * 64
        assert verify_proposal(KEY, proposal, expected_robot_id="robot-1", expected_instruction_sha256="c" * 64)[0]
        assert call({**base, "instruction_sha256": "nothex"})[0] == 400
        assert call({**base, "instruction_sha256": 5})[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
