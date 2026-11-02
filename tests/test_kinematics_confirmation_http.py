# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_kinematics_confirmation_http.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""The kinematic check, the two-step confirmation of proposals and the shared HTTP helpers, against real servers."""
from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from hydra_umc_vla_engine import http_common
from hydra_umc_vla_engine.api import VlaEngineServer
from hydra_umc_vla_engine.confirmation import (
    ConfirmationConfigError,
    ConfirmationError,
    ConfirmationPolicy,
    ConfirmationStore,
    load_confirmation_policy,
    summarize,
    verify_approval,
)
from hydra_umc_vla_engine.kinematic_check import (
    REACHABLE,
    UNAVAILABLE,
    UNREACHABLE,
    KinematicsConfigError,
    KinematicsPolicy,
    check_reach,
    load_kinematics_policy,
)
from hydra_umc_vla_engine.trajectory import Pose

FAKE = str(Path(__file__).with_name("fake_replica.py"))
KEY = b"k" * 32
FINGERPRINT = "a" * 64


def _policy(tmp_path: Path, **change: Any) -> KinematicsPolicy:
    values: dict[str, Any] = {"enabled": True, "command": (sys.executable, FAKE), "urdf": str(tmp_path / "robot.urdf"), "target_joint": "wrist",
                              "initial_joints": {"base": 0.0, "reach": 0.2}, "timeout_seconds": 5.0}
    values.update(change)
    return KinematicsPolicy(**values)


def _poses(*points: tuple[float, float, float]) -> list[Pose]:
    return [Pose(x, y, z, 0.0, 0.0, 0.0, 0.0) for x, y, z in points]


# -------------------------------------------------------------------------------------------------------- kinematic check


def test_a_trajectory_inside_the_reach_is_reachable_and_each_step_starts_from_the_previous_joints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_REPLICA_LOG", str(log))
    result = check_reach(_poses((0.2, 0.0, 0.1), (0.25, 0.05, 0.1), (0.3, 0.1, 0.1)), _policy(tmp_path))
    assert result.outcome == REACHABLE and result.checked == 3 and result.failed_at_step is None
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 3 and all(c[0] == "ik" and c[c.index("--target") + 1] == "wrist" for c in calls)
    assert calls[0][calls[0].index("--joints") + 1] == "base=0.000000000,reach=0.200000000"
    assert calls[1][calls[1].index("--joints") + 1].startswith("base=0.000000000,reach=0.200000000")  # the solution of step 0
    assert calls[2][calls[2].index("--joints") + 1] != calls[0][calls[0].index("--joints") + 1]


def test_a_pose_out_of_reach_is_unreachable_and_says_which(tmp_path: Path) -> None:
    result = check_reach(_poses((0.2, 0.0, 0.1), (0.9, 0.0, 0.1), (0.2, 0.0, 0.1)), _policy(tmp_path))
    assert result.outcome == UNREACHABLE and result.failed_at_step == 1 and result.checked == 1
    assert "step 1" in result.reasons[0] and "cannot be reached" in result.reasons[0]


def test_the_origin_moves_the_goals_into_the_frame_of_the_robot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_REPLICA_LOG", str(log))
    assert check_reach(_poses((0.0, 0.0, 0.1)), _policy(tmp_path, origin=(0.9, 0.0, 0.0))).outcome == UNREACHABLE
    assert check_reach(_poses((0.0, 0.0, 0.1)), _policy(tmp_path, origin=(0.3, 0.0, 0.0))).outcome == REACHABLE
    assert "0.300000000,0.000000000,0.100000000" in json.loads(log.read_text(encoding="utf-8").splitlines()[-1])


def test_a_joint_that_would_turn_too_far_between_two_poses_is_refused(tmp_path: Path) -> None:
    far = check_reach(_poses((0.3, 0.0, 0.1), (-0.3, 0.05, 0.1)), _policy(tmp_path, max_joint_step=0.5))
    assert far.outcome == UNREACHABLE and "turn" in far.reasons[0] and far.max_joint_step > 0.5
    assert check_reach(_poses((0.3, 0.0, 0.1), (-0.3, 0.05, 0.1)), _policy(tmp_path, max_joint_step=7.0)).outcome == REACHABLE


@pytest.mark.parametrize("mode, text", [("crash", "failed at step 0"), ("garbage", "nothing readable"), ("slow", "did not answer")])
def test_a_program_that_fails_is_unavailable_and_not_a_verdict_on_the_trajectory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, text: str) -> None:
    monkeypatch.setenv("FAKE_REPLICA_MODE", mode)
    result = check_reach(_poses((0.2, 0.0, 0.1)), _policy(tmp_path, timeout_seconds=1.0))
    assert result.outcome == UNAVAILABLE and text in result.reasons[0]


def test_a_program_that_is_not_there_and_a_trajectory_that_is_too_long_are_unavailable(tmp_path: Path) -> None:
    missing = check_reach(_poses((0.2, 0.0, 0.1)), _policy(tmp_path, command=(str(tmp_path / "no-such-program"),)))
    assert missing.outcome == UNAVAILABLE and "cannot be run" in missing.reasons[0]
    long = check_reach(_poses(*[(0.2, 0.0, 0.1)] * 5), _policy(tmp_path, max_waypoints=3))
    assert long.outcome == UNAVAILABLE and "at most 3" in long.reasons[0]


@pytest.mark.parametrize("change", [
    {"urdf": ""}, {"target_joint": ""}, {"target_joint": "a b"}, {"command": ()}, {"command": ("a;b",)}, {"initial_joints": {"a b": 1.0}},
    {"initial_joints": {"a": float("nan")}}, {"tolerance_m": 0}, {"max_joint_step": 8}, {"timeout_seconds": 0}, {"max_iterations": 0}, {"max_waypoints": 501}, {"fail_closed": "yes"},
])
def test_a_bad_kinematics_policy_is_refused(tmp_path: Path, change: dict) -> None:
    with pytest.raises(KinematicsConfigError):
        _policy(tmp_path, **change)


def test_the_policy_is_off_without_a_section_and_is_read_from_the_configuration_file(tmp_path: Path) -> None:
    assert load_kinematics_policy(None).enabled is False
    (tmp_path / "off.json").write_text(json.dumps({"confidence": {"minimum": 0.5}}), encoding="utf-8")
    assert load_kinematics_policy(tmp_path / "off.json").enabled is False
    section = {"enabled": True, "command": ["physics-replica"], "urdf": "robot.urdf", "target_joint": "wrist", "origin": [0.1, 0.0, 0.0], "initial_joints": {"base": 0.0}}
    (tmp_path / "on.json").write_text(json.dumps({"kinematics": section}), encoding="utf-8")
    policy = load_kinematics_policy(tmp_path / "on.json")
    assert policy.enabled and policy.fail_closed is True and policy.origin == (0.1, 0.0, 0.0) and Path(policy.urdf) == (tmp_path / "robot.urdf").resolve()
    for bad in ({"kinematics": []}, {"kinematics": {"unknown": 1}}, {"kinematics": {**section, "origin": [1, 2]}}, {"kinematics": {**section, "command": "x"}}, {"kinematics": {**section, "initial_joints": []}}):
        (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(KinematicsConfigError):
            load_kinematics_policy(tmp_path / "bad.json")
    with pytest.raises(KinematicsConfigError):
        load_kinematics_policy(tmp_path / "missing.json")


# ------------------------------------------------------------------------------------------------------------- the server


def _call(url: str, body: object = None, token: str = "") -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def _serve(tmp_path: Path, **kwargs: Any) -> Iterator[tuple[str, VlaEngineServer]]:
    server = VlaEngineServer(("127.0.0.1", 0), tmp_path, **kwargs)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", server
    server.shutdown()
    server.server_close()


def _integrate(base: str, token: str = "", step: float = 0.01, count: int = 3) -> tuple[int, dict]:
    return _call(base + "/trajectory/integrate", {"start": [0.2, 0.0, 0.1, 0, 0, 0], "actions": [[step, 0, 0, 0, 0, 0, 0.0]] * count}, token)


def test_a_reachable_trajectory_is_offered_with_the_verdict(tmp_path: Path) -> None:
    for base, _ in _serve(tmp_path, kinematics=_policy(tmp_path)):
        status, answer = _integrate(base)
        assert status == 200 and answer["kinematics"]["outcome"] == "reachable" and answer["kinematics"]["checked"] == 4
        assert answer["proposal"]["authorized"] is False


def test_an_unreachable_trajectory_is_not_offered_and_the_check_that_cannot_run_is_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for base, _ in _serve(tmp_path, kinematics=_policy(tmp_path)):
        status, answer = _integrate(base, step=0.04, count=10)  # 0.2 -> 0.6 m: out of reach
        assert status == 422 and answer["kinematics"]["outcome"] == "unreachable" and "proposal" not in answer
    monkeypatch.setenv("FAKE_REPLICA_MODE", "crash")
    for base, _ in _serve(tmp_path, kinematics=_policy(tmp_path)):
        status, answer = _integrate(base)
        assert status == 503 and answer["kinematics"]["outcome"] == "unavailable" and "proposal" not in answer
    for base, _ in _serve(tmp_path, kinematics=_policy(tmp_path, fail_closed=False)):
        status, answer = _integrate(base)  # the check could not run and the file says it may go on: the proposal carries the report
        assert status == 200 and answer["kinematics"]["outcome"] == "unavailable"


def test_without_the_policy_nothing_is_asked_and_nothing_is_added(tmp_path: Path) -> None:
    for base, _ in _serve(tmp_path):
        status, answer = _integrate(base)
        assert status == 200 and "kinematics" not in answer and "confirmation" not in answer["proposal"]
        assert _call(base + "/confirmations/pending")[0] == 404
        assert _call(base + "/confirmations/x/prepare", {"operator": "ana"})[0] == 404


# ---------------------------------------------------------------------------------------------------------- confirmation


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def _store(clock: Clock | None = None, **change: Any) -> ConfirmationStore:
    return ConfirmationStore(ConfirmationPolicy(enabled=True, **change), KEY, "arm-1", clock or Clock())


def test_the_two_steps_give_a_signed_approval_that_the_executor_can_check() -> None:
    clock = Clock()
    store = _store(clock)
    pending = store.create(FINGERPRINT, {"steps": 3})
    assert pending["status"] == "awaiting_confirmation" and store.list()[0]["summary"] == {"steps": 3}
    seen = store.prepare(pending["pending_id"], "ana")
    assert seen["summary"] == {"steps": 3} and seen["fingerprint"] == FINGERPRINT and seen["confirmationValiditySeconds"] == 30.0
    clock.now += 5
    approval = store.confirm(pending["pending_id"], "ana", seen["confirmationToken"])
    assert approval["approved"] is True and approval["operator"] == "ana" and approval["robot_id"] == "arm-1"
    now_ms = approval["approved_at_ms"]
    assert verify_approval(KEY, approval, expected_fingerprint=FINGERPRINT, expected_robot_id="arm-1", now_ms=now_ms + 100) == (True, "")
    assert store.list() == [] and store.approved == 1


def test_an_approval_is_for_one_trajectory_one_robot_one_key_and_a_short_time() -> None:
    store = _store()
    pending = store.create(FINGERPRINT, {})
    approval = store.confirm(pending["pending_id"], "ana", store.prepare(pending["pending_id"], "ana")["confirmationToken"])
    now = approval["approved_at_ms"]
    check = lambda a=approval, **kw: verify_approval(KEY, a, **{"expected_fingerprint": FINGERPRINT, "expected_robot_id": "arm-1", "now_ms": now + 10, **kw})  # noqa: E731
    assert check()[0] is True
    assert "different trajectory" in check(expected_fingerprint="b" * 64)[1]
    assert "different robot" in check(expected_robot_id="arm-2")[1]
    assert "expired" in check(now_ms=approval["expires_at_ms"])[1]
    assert "future" in check(now_ms=now - 60_000)[1]
    assert "does not match" in check({**approval, "operator": "eve"})[1]
    assert "does not match" in verify_approval(b"x" * 32, approval, expected_fingerprint=FINGERPRINT, expected_robot_id="arm-1", now_ms=now)[1]
    assert "not signed" in check({"approved": True})[1]


def test_the_token_is_for_this_proposal_this_operator_and_once() -> None:
    clock = Clock()
    store = _store(clock)
    a, b = store.create(FINGERPRINT, {}), store.create("c" * 64, {})
    token_a = store.prepare(a["pending_id"], "ana")["confirmationToken"]
    with pytest.raises(ConfirmationError, match="prepare this proposal first") as not_prepared:
        store.confirm(b["pending_id"], "ana", token_a)
    assert not_prepared.value.status == 409
    store.prepare(b["pending_id"], "ana")
    with pytest.raises(ConfirmationError, match="not the one issued") as other:
        store.confirm(b["pending_id"], "ana", token_a)  # a genuine token, but of the other proposal
    assert other.value.status == 403
    with pytest.raises(ConfirmationError, match="another operator"):
        store.confirm(a["pending_id"], "luis", token_a)
    with pytest.raises(ConfirmationError, match="not genuine"):
        store.confirm(a["pending_id"], "ana", token_a[:-1] + ("0" if token_a[-1] != "0" else "1"))
    with pytest.raises(ConfirmationError):
        store.confirm(a["pending_id"], "ana", "no-dot")
    with pytest.raises(ConfirmationError, match="not genuine"):
        store.confirm(a["pending_id"], "ana", "!!!." + "0" * 64)
    assert store.confirm(a["pending_id"], "ana", token_a)["approved"] is True
    with pytest.raises(ConfirmationError, match="no such proposal") as gone:
        store.confirm(a["pending_id"], "ana", token_a)  # a token is accepted once
    assert gone.value.status == 404


def test_a_second_prepare_replaces_the_token_and_an_old_token_expires() -> None:
    clock = Clock()
    store = _store(clock, token_seconds=10.0)
    pending = store.create(FINGERPRINT, {})
    first = store.prepare(pending["pending_id"], "ana")["confirmationToken"]
    second = store.prepare(pending["pending_id"], "ana")["confirmationToken"]
    with pytest.raises(ConfirmationError, match="not the one issued"):
        store.confirm(pending["pending_id"], "ana", first)
    clock.now += 11
    with pytest.raises(ConfirmationError, match="has expired") as late:
        store.confirm(pending["pending_id"], "ana", second)
    assert late.value.status == 410
    fresh = store.prepare(pending["pending_id"], "ana")["confirmationToken"]
    assert store.confirm(pending["pending_id"], "ana", fresh)["approved"] is True


def test_proposals_expire_are_bounded_and_can_be_rejected() -> None:
    clock = Clock()
    store = _store(clock, ttl_seconds=60.0, max_pending=2)
    ids = [store.create(f"{n:064d}", {})["pending_id"] for n in range(3)]
    assert [p["pending_id"] for p in store.list()] == ids[1:]  # the oldest was dropped to make room
    assert store.reject(ids[1], "ana")["approved"] is False and store.rejected == 1
    clock.now += 61
    assert store.list() == []
    with pytest.raises(ConfirmationError, match="no such proposal"):
        store.prepare(ids[2], "ana")
    for bad in ("", "a b", "x" * 65, None, 5):
        with pytest.raises(ConfirmationError):
            store.prepare(ids[2], bad)


def test_the_summary_is_computed_from_the_poses() -> None:
    poses = [Pose(0, 0, 0, 0, 0, 0, 0.0), Pose(0.03, 0.04, 0, 0, 0, 0, 0.0), Pose(0.03, 0.04, 0.1, 0, 0, 0, 1.0)]
    summary = summarize(poses, robot_id="arm-1", guard={"outcome": "ok"}, kinematics={"outcome": "reachable"})
    assert summary["steps"] == 2 and summary["path_length_m"] == pytest.approx(0.15) and summary["longest_step_m"] == pytest.approx(0.1)
    assert summary["gripper_changes"] == 1 and summary["final_pose"]["z"] == 0.1 and summary["guard"] == "ok" and summary["kinematics"] == "reachable"
    assert summarize(poses[:1], robot_id="r", guard=None, kinematics=None)["steps"] == 0


@pytest.mark.parametrize("change", [{"ttl_seconds": 0}, {"ttl_seconds": 4000}, {"token_seconds": 0}, {"max_pending": 0}, {"max_pending": 257}, {"approval_validity_ms": 0},
                                    {"approval_validity_ms": 600001}, {"enabled": "yes"}, {"ttl_seconds": True}])
def test_a_bad_confirmation_policy_is_refused(change: dict) -> None:
    with pytest.raises(ConfirmationConfigError):
        ConfirmationPolicy(**change)


def test_the_confirmation_section_of_the_configuration_file(tmp_path: Path) -> None:
    assert load_confirmation_policy(None).enabled is False
    (tmp_path / "c.json").write_text(json.dumps({"confirmation": {"enabled": True, "ttl_seconds": 90}}), encoding="utf-8")
    assert load_confirmation_policy(tmp_path / "c.json").ttl_seconds == 90
    (tmp_path / "bad.json").write_text(json.dumps({"confirmation": {"extra": 1}}), encoding="utf-8")
    with pytest.raises(ConfirmationConfigError):
        load_confirmation_policy(tmp_path / "bad.json")


def test_the_whole_flow_over_http(tmp_path: Path) -> None:
    store = _store()
    for base, _ in _serve(tmp_path, confirmations=store, token="t" * 16):
        status, answer = _integrate(base, "t" * 16)
        assert status == 200
        pending_id = answer["proposal"]["confirmation"]["pending_id"]
        assert answer["proposal"]["authorized"] is False and answer["proposal"]["confirmation"]["status"] == "awaiting_confirmation"
        assert _call(base + "/confirmations/pending")[0] == 401
        status, listed = _call(base + "/confirmations/pending", token="t" * 16)
        assert status == 200 and listed["pending"][0]["summary"]["steps"] == 3 and listed["pending"][0]["fingerprint"] == answer["proposal"]["fingerprint"]
        assert _call(base + f"/confirmations/{pending_id}/confirm", {"operator": "ana", "confirmationToken": "a.b"}, "t" * 16)[0] == 409
        status, prepared = _call(base + f"/confirmations/{pending_id}/prepare", {"operator": "ana"}, "t" * 16)
        assert status == 200 and prepared["summary"]["steps"] == 3
        assert _call(base + f"/confirmations/{pending_id}/confirm", {"operator": "luis", "confirmationToken": prepared["confirmationToken"]}, "t" * 16)[0] == 403
        status, approval = _call(base + f"/confirmations/{pending_id}/confirm", {"operator": "ana", "confirmationToken": prepared["confirmationToken"]}, "t" * 16)
        assert status == 200 and approval["approved"] is True
        assert verify_approval(KEY, approval, expected_fingerprint=answer["proposal"]["fingerprint"], expected_robot_id="arm-1", now_ms=approval["approved_at_ms"] + 100)[0] is True
        assert _call(base + f"/confirmations/{pending_id}/prepare", {"operator": "ana"}, "t" * 16)[0] == 404
        status, second = _integrate(base, "t" * 16, step=0.02)
        status, rejected = _call(base + f"/confirmations/{second['proposal']['confirmation']['pending_id']}/reject", {"operator": "ana"}, "t" * 16)
        assert status == 200 and rejected["approved"] is False
        assert _call(base + "/confirmations/x/bogus", {"operator": "ana"}, "t" * 16)[0] in (404,)
        assert _call(base + "/confirmations/x/prepare", {"operator": 5}, "t" * 16)[0] in (400, 404)


# ------------------------------------------------------------------------------------------------ the shared HTTP module


def test_the_copy_of_the_shared_module_is_the_canonical_one() -> None:
    canonical = Path(__file__).resolve().parents[2] / "HYDRA-UMC-SDK" / "tools" / "canonical" / "http_common.py"
    if not canonical.is_file():
        pytest.skip("the SDK checkout is not next to this repository")
    assert Path(http_common.__file__).read_bytes().replace(b"\r\n", b"\n") == canonical.read_bytes().replace(b"\r\n", b"\n")


def test_the_server_limits_the_requests_it_handles_at_the_same_time(tmp_path: Path) -> None:
    for base, server in _serve(tmp_path, max_threads=1):
        assert server.max_threads == 1
        port = int(base.rsplit(":", 1)[1])
        holder = socket.create_connection(("127.0.0.1", port), timeout=5)  # holds the only slot: it connects and says nothing
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as second:
                second.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
                reply = second.recv(4096)
            assert reply.startswith(b"HTTP/1.1 503") and server.refused == 1
        finally:
            holder.close()
    with pytest.raises(ValueError):
        VlaEngineServer(("127.0.0.1", 0), tmp_path, max_threads=0)
