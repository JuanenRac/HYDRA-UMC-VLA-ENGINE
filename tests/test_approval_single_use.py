# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_approval_single_use.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""An approval can carry an identity of its own, and the layer that executes accepts it once."""
from __future__ import annotations

import pytest

from hydra_umc_vla_engine.confirmation import (
    ApprovalLedger,
    ConfirmationConfigError,
    ConfirmationPolicy,
    ConfirmationStore,
    load_confirmation_policy,
    verify_approval,
    verify_approval_once,
)

KEY = b"k" * 32
FINGERPRINT = "f" * 64


class Clock:
    def __init__(self) -> None:
        self.now = 1_700_000_000.0

    def __call__(self) -> float:
        return self.now


def _approval(single_use: bool) -> dict:
    store = ConfirmationStore(ConfirmationPolicy(enabled=True, single_use=single_use), KEY, "arm-1", Clock())
    pending = store.create(FINGERPRINT, {"steps": 1})
    seen = store.prepare(pending["pending_id"], "ana")
    return store.confirm(pending["pending_id"], "ana", seen["confirmationToken"])


def _check(approval: dict, ledger: ApprovalLedger, **change: object) -> tuple[bool, str]:
    arguments: dict = {"expected_fingerprint": FINGERPRINT, "expected_robot_id": "arm-1", "ledger": ledger, "now_ms": approval["approved_at_ms"] + 100}
    arguments.update(change)
    return verify_approval_once(KEY, approval, **arguments)


def test_the_default_is_the_first_form_without_an_identity() -> None:
    assert ConfirmationPolicy().single_use is False
    approval = _approval(False)
    assert "approval_id" not in approval
    assert verify_approval(KEY, approval, expected_fingerprint=FINGERPRINT, expected_robot_id="arm-1", now_ms=approval["approved_at_ms"] + 100) == (True, "")


def test_with_single_use_the_approval_has_an_identity_that_is_signed() -> None:
    approval = _approval(True)
    assert len(approval["approval_id"]) == 32
    now = approval["approved_at_ms"] + 100
    assert verify_approval(KEY, approval, expected_fingerprint=FINGERPRINT, expected_robot_id="arm-1", now_ms=now) == (True, "")
    other = {**approval, "approval_id": "0" * 32}
    assert "does not match" in verify_approval(KEY, other, expected_fingerprint=FINGERPRINT, expected_robot_id="arm-1", now_ms=now)[1]
    dropped = {k: v for k, v in approval.items() if k != "approval_id"}
    assert "does not match" in verify_approval(KEY, dropped, expected_fingerprint=FINGERPRINT, expected_robot_id="arm-1", now_ms=now)[1]
    for bad in ("short", 7, "G" * 32, ""):
        assert verify_approval(KEY, {**approval, "approval_id": bad}, expected_fingerprint=FINGERPRINT, expected_robot_id="arm-1", now_ms=now) == (False, "the approval is not signed")


def test_the_same_approval_is_accepted_only_once() -> None:
    approval = _approval(True)
    ledger = ApprovalLedger()
    assert _check(approval, ledger) == (True, "")
    assert _check(approval, ledger) == (False, "the approval was already used")
    assert _check(_approval(True), ledger) == (True, "")        # another approval has another identity


def test_a_refused_approval_does_not_use_up_its_identity() -> None:
    approval = _approval(True)
    ledger = ApprovalLedger()
    assert _check(approval, ledger, expected_robot_id="arm-2")[0] is False
    assert _check(approval, ledger, expected_fingerprint="e" * 64)[0] is False
    assert _check(approval, ledger, now_ms=approval["expires_at_ms"] + 1) == (False, "the approval has expired")
    assert _check(approval, ledger) == (True, "")


def test_an_approval_without_identity_is_accepted_unless_the_layer_asks_for_one() -> None:
    approval = _approval(False)
    ledger = ApprovalLedger()
    assert _check(approval, ledger) == (True, "")
    assert _check(approval, ledger) == (True, "")                 # the first form cannot be tracked
    assert _check(approval, ledger, require_id=True) == (False, "the approval has no identity of its own")


def test_the_ledger_forgets_an_identity_only_when_the_approval_has_expired_and_refuses_when_full() -> None:
    ledger = ApprovalLedger(max_entries=2)
    assert ledger.accept("a" * 32, 1000, 10) and ledger.accept("b" * 32, 1000, 10)
    assert ledger.accept("c" * 32, 1000, 10) is False             # full of identities that could still be presented
    assert ledger.accept("a" * 32, 1000, 10) is False
    assert ledger.accept("c" * 32, 2000, 1000) is True            # the first two have expired by then and are forgotten
    assert ledger.accept("a" * 32, 3000, 1500) is True            # and an expired one may come again (its approval no longer passes anyway)


def test_the_setting_is_read_from_the_file(tmp_path) -> None:
    path = tmp_path / "vla.json"
    path.write_text('{"confirmation": {"enabled": true, "single_use": true}}', encoding="utf-8")
    assert load_confirmation_policy(path).single_use is True
    with pytest.raises(ConfirmationConfigError):
        ConfirmationPolicy(single_use="yes")  # type: ignore[arg-type]
