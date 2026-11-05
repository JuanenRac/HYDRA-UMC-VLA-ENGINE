# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_proposal_ed25519.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A proposal signed with Ed25519 can be checked with the public key alone, and the check refuses what the HMAC check refuses."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from hydra_umc_vla_engine import ed25519_pure, main as main_module
from hydra_umc_vla_engine.api import proposal_record
from hydra_umc_vla_engine.proposal_signing import (
    Ed25519Seed,
    ProposalKeyError,
    key_id_of,
    load_ed25519_seed,
    load_public_keys,
    sign_proposal,
    verify_proposal,
    verify_proposal_ed25519,
)

SEED = Ed25519Seed(bytes(range(32)))
NOW = 1_700_000_000_000
POSES = [{"x": 0.0, "y": 0.0, "z": 0.0}, {"x": 0.1, "y": 0.0, "z": 0.0}]
KEYS = {SEED.key_id: SEED.public_key}


def _signed(**kw) -> dict:
    fingerprint = proposal_record(POSES)["fingerprint"]
    return {"fingerprint": fingerprint, **sign_proposal(SEED, fingerprint, "robot-1", validity_ms=30_000, now_ms=NOW, **kw)}


def test_rfc_8032_vector_one() -> None:
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    assert ed25519_pure.public_key(seed).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    assert ed25519_pure.sign(seed, b"").hex() == (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )


def test_the_key_id_is_the_first_eight_bytes_of_the_sha512_of_the_public_key() -> None:
    assert len(SEED.key_id) == 16
    assert SEED.key_id == key_id_of(SEED.public_key)


def test_an_ed25519_proposal_carries_algorithm_key_id_and_a_long_signature() -> None:
    record = proposal_record(POSES, (SEED, "robot-1", 30_000))
    assert record["signature_alg"] == "ed25519" and record["key_id"] == SEED.key_id and len(record["signature"]) == 128
    assert verify_proposal_ed25519(KEYS, record, expected_robot_id="robot-1") == (True, "")


def test_a_hmac_proposal_is_as_before_and_is_not_taken_for_ed25519() -> None:
    record = proposal_record(POSES, (b"k" * 32, "robot-1", 30_000))
    assert "signature_alg" not in record and "key_id" not in record
    assert verify_proposal(b"k" * 32, record, expected_robot_id="robot-1") == (True, "")
    assert verify_proposal_ed25519(KEYS, record, expected_robot_id="robot-1") == (False, "the proposal is not signed")


def test_the_check_needs_only_the_public_key_and_refuses_what_changed() -> None:
    proposal = _signed(model_version="m1", instruction_sha256="c" * 64)
    ok = lambda p, **kw: verify_proposal_ed25519(KEYS, p, expected_robot_id="robot-1", now_ms=NOW + 1000, **kw)  # noqa: E731
    assert ok(proposal, expected_model_version="m1", expected_instruction_sha256="c" * 64) == (True, "")
    for field, value in (("fingerprint", "f" * 64), ("robot_id", "robot-2"), ("expires_at_ms", NOW + 500_000), ("model_version", "m2"), ("key_id", "0" * 16)):
        assert ok({**proposal, field: value})[0] is False, field
    assert ok({**proposal, "signature": proposal["signature"].upper()})[0] is False
    assert ok({**proposal, "signature": "zz" * 64})[0] is False
    assert ok({**proposal, "signature_alg": "hmac"}) == (False, "the proposal is not signed with ed25519")
    assert ok(proposal, expected_model_version="m2") == (False, "the proposal was made by a different model version")
    assert ok(proposal, expected_instruction_sha256="d" * 64) == (False, "the proposal answers a different instruction")


def test_time_and_robot_rules_are_those_of_the_hmac_check() -> None:
    proposal = _signed()
    check = lambda now, robot="robot-1": verify_proposal_ed25519(KEYS, proposal, expected_robot_id=robot, now_ms=now)  # noqa: E731
    assert check(NOW + 31_000) == (False, "the proposal has expired")
    assert check(NOW - 60_000) == (False, "the proposal was issued in the future")
    assert check(NOW, "robot-2") == (False, "the proposal is for a different robot")
    other = Ed25519Seed(bytes(reversed(range(32))))
    assert verify_proposal_ed25519({other.key_id: other.public_key}, proposal, expected_robot_id="robot-1", now_ms=NOW) == (False, "the proposal is signed by a key that is not listed")


def test_a_signature_made_for_one_key_id_does_not_pass_under_another() -> None:
    other = Ed25519Seed(bytes(reversed(range(32))))
    proposal = _signed()
    keys = {**KEYS, other.key_id: other.public_key}
    swapped = {**proposal, "key_id": other.key_id}
    assert verify_proposal_ed25519(keys, swapped, expected_robot_id="robot-1", now_ms=NOW)[0] is False


def test_the_seed_and_public_key_files(tmp_path: Path) -> None:
    seed_file = tmp_path / "seed.hex"
    seed_file.write_text(bytes(SEED).hex() + "\n", encoding="ascii")
    assert load_ed25519_seed(seed_file) == SEED
    for text in ("", "zz", "00" * 31):
        seed_file.write_text(text, encoding="ascii")
        with pytest.raises(ProposalKeyError):
            load_ed25519_seed(seed_file)
    with pytest.raises(ProposalKeyError):
        load_ed25519_seed(tmp_path / "missing")
    keys_file = tmp_path / "keys.json"
    keys_file.write_text(json.dumps({"keys": {SEED.key_id: SEED.public_key.hex(), "0" * 16: SEED.public_key.hex(), "short": "00"}}), encoding="utf-8")
    assert load_public_keys(keys_file) == KEYS
    keys_file.write_text("not json", encoding="utf-8")
    with pytest.raises(ProposalKeyError):
        load_public_keys(keys_file)


def test_the_fixed_vector_that_the_server_also_checks() -> None:
    """The proposal below is checked by tests/trust.test.ts of HYDRA-UMC-SERVER: the two sides write the signed bytes the same way."""
    proposal = {
        "fingerprint": "ab" * 16, "robot_id": "r1", "issued_at_ms": NOW, "expires_at_ms": NOW + 60_000, "model_version": "m1",
        "instruction_sha256": "c" * 64, "signature_alg": "ed25519", "key_id": SEED.key_id,
    }
    from hydra_umc_vla_engine.proposal_signing import _message_ed25519

    signature = ed25519_pure.sign(bytes(SEED), _message_ed25519("ab" * 16, "r1", NOW, NOW + 60_000, "m1", "c" * 64, SEED.key_id)).hex()
    proposal["signature"] = signature
    assert verify_proposal_ed25519(KEYS, proposal, expected_robot_id="r1", now_ms=NOW + 1000) == (True, "")
    assert SEED.public_key.hex() == "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8" and SEED.key_id == "ed4242ead4ac6948"
    assert signature == "99c2e2f969adddd97ae560d15d4e45327e42b91987ceac7253d3cc45a0acfad4a8cfe4d76fe18cf7c695bcb72afa207a121fbb44ee79f526cf27261c76f7bf02"


def test_serve_refuses_confirmation_with_an_ed25519_key(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    seed_file = tmp_path / "seed.hex"
    seed_file.write_text(bytes(SEED).hex(), encoding="ascii")
    config = tmp_path / "cfg.json"
    config.write_text(json.dumps({"confirmation": {"enabled": True}}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "hydra-umc-vla-engine", "serve", "--port", "0", "--proposal-key-file", str(seed_file), "--proposal-signing", "ed25519", "--robot-id", "r1", "--config", str(config),
    ])
    assert main_module.main() == 2
    assert "does not go with --proposal-signing ed25519" in capsys.readouterr().err
