# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_simulation_bench.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Simulation bench: the real tokens, trajectory, guard and confirmation against a simulated model, a simulated cell and a simulated operator.

The model is a function that writes actions from a fixed seed in the ways a real one fails: smooth, noisy, runaway in one direction, saturated, drifting toward a
person's zone, out of range, not a number, the wrong length. The cell is a work volume with a danger zone and a warning zone. The operator is a script that
prepares, confirms, confirms twice, confirms late, confirms as someone else or takes the token of another proposal. The bench states what must hold for every
proposal whatever the model does: the tool never leaves the volume, never enters the danger zone, never takes a longer step than the limit, and nothing is
approved by anyone but the person the summary was shown to. Nothing here says how a real model behaves: that needs the model and the robot."""
from __future__ import annotations

import math
import random

import pytest

from hydra_umc_vla_engine.action_tokens import VLA_ACTION_SPACE, TokenizationError, decode_action, encode_action
from hydra_umc_vla_engine.confirmation import (
    ConfirmationError,
    ConfirmationPolicy,
    ConfirmationStore,
    summarize,
    verify_approval,
)
from hydra_umc_vla_engine.guard import CLAMPED, OK, REJECTED, GuardConfigError, guard_trajectory, parse_limits
from hydra_umc_vla_engine.trajectory import Pose, TrajectoryError, integrate_trajectory

SEED = 20260101
KEY = b"k" * 32
LIMITS = parse_limits({
    "workspace": {"min": {"x": -1, "y": -1, "z": 0}, "max": {"x": 1, "y": 1, "z": 1}},
    "max_linear_step_m": 0.03,
    "max_angular_step_rad": 0.08,
    "zones": [
        {"id": "person", "level": "danger", "min": {"x": 0.3, "y": 0.3, "z": 0}, "max": {"x": 0.6, "y": 0.6, "z": 1}},
        {"id": "fence", "level": "warning", "min": {"x": -1, "y": -1, "z": 0}, "max": {"x": -0.6, "y": 1, "z": 1}},
    ],
})
START = Pose(0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.5)
DANGER = ((0.3, 0.3, 0.0), (0.6, 0.6, 1.0))


def _model(rng: random.Random, kind: str, steps: int = 60) -> list[tuple[float, ...]]:
    """Seven numbers per step, written the way a model of that kind writes them."""
    low = [s.min for s in VLA_ACTION_SPACE]
    high = [s.max for s in VLA_ACTION_SPACE]
    actions = []
    heading = [rng.uniform(-1, 1) for _ in range(3)]
    for index in range(steps):
        if kind == "smooth":
            move = [0.012 * math.sin(index / 7 + heading[i] * 3) for i in range(3)]
        elif kind == "noisy":
            move = [max(low[i], min(high[i], rng.gauss(0, 0.02))) for i in range(3)]
        elif kind == "runaway":
            move = [0.05 * (1 if heading[i] > 0 else -1) for i in range(3)]
        elif kind == "toward-person":
            move = [0.02, 0.02, 0.0]
        elif kind == "saturated":
            move = [rng.choice([low[i], high[i]]) for i in range(3)]
        else:
            move = [rng.uniform(low[i], high[i]) for i in range(3)]
        turn = [max(-0.04, min(0.04, rng.gauss(0, 0.015))) for _ in range(3, 6)]
        actions.append((*move, *turn, rng.uniform(0.0, 1.0)))
    return actions


def _fields(p: Pose) -> list[float]:
    return [p.x, p.y, p.z, p.roll, p.pitch, p.yaw, p.gripper]


def _inside(p: Pose, box) -> bool:
    return all(box[0][i] <= (p.x, p.y, p.z)[i] <= box[1][i] for i in range(3))


@pytest.mark.parametrize("kind", ["smooth", "noisy", "runaway", "toward-person", "saturated", "random"])
def test_whatever_the_model_writes_the_tool_stays_in_the_volume_out_of_the_danger_zone_and_inside_the_step_limit(kind: str) -> None:
    for run in range(15):
        rng = random.Random(SEED + run)
        start = Pose(rng.uniform(-0.9, -0.1), rng.uniform(-0.9, 0.1), rng.uniform(0.1, 0.9), 0.0, 0.0, 0.0, 0.5)
        proposal = integrate_trajectory(start, _model(rng, kind))
        result = guard_trajectory(proposal, LIMITS)
        assert result.outcome in (OK, CLAMPED, REJECTED)
        if result.outcome == REJECTED:
            assert result.poses == [] and result.reasons and result.rejected_at_step is not None
            continue
        poses = result.poses
        for pose in poses:
            assert -1 <= pose.x <= 1 and -1 <= pose.y <= 1 and 0 <= pose.z <= 1
            assert not _inside(pose, DANGER), (kind, run, pose)
        for before, after in zip(poses, poses[1:], strict=False):
            assert math.dist((before.x, before.y, before.z), (after.x, after.y, after.z)) <= LIMITS.max_linear_step + 1e-9
        if result.outcome == OK:
            assert [v for p in poses for v in _fields(p)] == pytest.approx([v for p in proposal for v in _fields(p)], abs=1e-9)  # as it came, to the last bit of rounding


def test_a_runaway_model_is_cut_back_or_refused_and_a_smooth_one_in_the_clear_is_left_alone() -> None:
    smooth = integrate_trajectory(START, _model(random.Random(SEED), "smooth", 30))
    assert guard_trajectory(smooth, LIMITS).outcome == OK
    runaway = integrate_trajectory(START, _model(random.Random(SEED), "runaway", 60))
    assert guard_trajectory(runaway, LIMITS).outcome in (CLAMPED, REJECTED)


def test_a_model_that_walks_into_the_person_is_refused_at_the_step_where_it_gets_there() -> None:
    proposal = integrate_trajectory(START, _model(random.Random(SEED), "toward-person", 80))
    result = guard_trajectory(proposal, LIMITS)
    assert result.outcome == REJECTED and "person" in " ".join(result.reasons)
    first_inside = next(i for i, pose in enumerate(proposal) if _inside(pose, DANGER))
    assert result.rejected_at_step is not None and result.rejected_at_step <= first_inside


def test_the_guard_is_a_function_of_the_proposal_only() -> None:
    proposal = integrate_trajectory(START, _model(random.Random(SEED), "noisy"))
    assert guard_trajectory(proposal, LIMITS) == guard_trajectory(proposal, LIMITS)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 9.0, -9.0])
def test_a_value_that_is_not_a_number_or_out_of_range_never_becomes_a_pose(bad: float) -> None:
    actions = _model(random.Random(SEED), "smooth", 10)
    actions[4] = (bad, *actions[4][1:])
    try:
        poses = integrate_trajectory(START, actions)
    except TrajectoryError:
        return
    assert guard_trajectory(poses, LIMITS).outcome in (OK, CLAMPED, REJECTED)
    assert all(math.isfinite(p.x) and math.isfinite(p.y) and math.isfinite(p.z) for p in poses)


def test_an_action_of_the_wrong_length_is_refused_before_it_moves_anything() -> None:
    for width in (0, 3, 6, 8):
        with pytest.raises(TrajectoryError):
            integrate_trajectory(START, [tuple([0.0] * width)])


def test_starting_in_the_wrong_place_is_refused_whatever_follows() -> None:
    outside = Pose(5.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.5)
    inside_danger = Pose(0.4, 0.4, 0.5, 0.0, 0.0, 0.0, 0.5)
    bad_gripper = Pose(0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 7.0)
    for start in (outside, inside_danger, bad_gripper):
        result = guard_trajectory(integrate_trajectory(start, _model(random.Random(SEED), "smooth", 5)), LIMITS)
        assert result.outcome == REJECTED and result.rejected_at_step == 0
    assert guard_trajectory([], LIMITS).outcome == REJECTED


@pytest.mark.parametrize("vocab", [3, 16, 256, 1024])
def test_the_tokens_of_a_model_decode_to_actions_the_guard_can_judge_and_a_token_out_of_the_vocabulary_is_refused(vocab: int) -> None:
    rng = random.Random(SEED)
    for _ in range(25):
        wanted = _model(rng, "random", 1)[0]
        tokens = encode_action(wanted, vocab_size=vocab)
        assert len(tokens) == 7 and all(0 <= t < vocab for t in tokens)
        back = decode_action(tokens, vocab_size=vocab, snap_zero=False)
        for value, decoded, spec in zip(wanted, back, VLA_ACTION_SPACE, strict=True):
            assert abs(value - decoded) <= (spec.max - spec.min) / vocab / 2 + 1e-9
    with pytest.raises(TokenizationError):
        decode_action(tuple([vocab] * 7), vocab_size=vocab)


@pytest.mark.parametrize("raw", [[], "limits", {}, {"workspace": {}}, {"workspace": {"min": {"x": 0, "y": 0, "z": 0}, "max": {"x": 1, "y": 1, "z": 1}}, "max_linear_step_m": 0, "max_angular_step_rad": 1}])
def test_limits_that_do_not_describe_a_cell_are_refused(raw: object) -> None:
    with pytest.raises(GuardConfigError):
        parse_limits(raw)


# ------------------------------------------------------------------------------------------------------------- the person who approves
class _Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


def _store(clock: _Clock, **policy) -> ConfirmationStore:
    return ConfirmationStore(ConfirmationPolicy(enabled=True, **policy), KEY, "arm-1", clock)


def _proposal(store: ConfirmationStore, seed: int = SEED, fingerprint: str = "f" * 64):
    poses = guard_trajectory(integrate_trajectory(START, _model(random.Random(seed), "smooth", 20)), LIMITS).poses
    return store.create(fingerprint, summarize(poses, robot_id="arm-1", guard=None, kinematics=None))["pending_id"]


def test_the_operator_that_was_shown_the_summary_approves_once_and_the_approval_is_for_that_trajectory_and_that_robot() -> None:
    clock = _Clock()
    store = _store(clock)
    pending = _proposal(store)
    prepared = store.prepare(pending, "ana")
    assert prepared["summary"]["steps"] == 20 and prepared["summary"]["robot_id"] == "arm-1"
    approval = store.confirm(pending, "ana", prepared["confirmationToken"])
    now_ms = int(clock.now * 1000)
    assert verify_approval(KEY, approval, expected_fingerprint="f" * 64, expected_robot_id="arm-1", now_ms=now_ms) == (True, "")
    assert not verify_approval(KEY, approval, expected_fingerprint="e" * 64, expected_robot_id="arm-1", now_ms=now_ms)[0]
    assert not verify_approval(KEY, approval, expected_fingerprint="f" * 64, expected_robot_id="arm-2", now_ms=now_ms)[0]
    assert not verify_approval(b"x" * 32, approval, expected_fingerprint="f" * 64, expected_robot_id="arm-1", now_ms=now_ms)[0]
    with pytest.raises(ConfirmationError) as again:
        store.confirm(pending, "ana", prepared["confirmationToken"])
    assert again.value.status == 404  # the same approval cannot be spent twice
    assert store.approved == 1


def test_an_approval_does_not_last_and_one_from_the_future_is_refused() -> None:
    clock = _Clock()
    store = _store(clock, approval_validity_ms=5000)
    pending = _proposal(store)
    approval = store.confirm(pending, "ana", store.prepare(pending, "ana")["confirmationToken"])
    start = approval["approved_at_ms"]
    assert verify_approval(KEY, approval, expected_fingerprint="f" * 64, expected_robot_id="arm-1", now_ms=start + 4999)[0]
    assert verify_approval(KEY, approval, expected_fingerprint="f" * 64, expected_robot_id="arm-1", now_ms=start + 5000) == (False, "the approval has expired")
    assert not verify_approval(KEY, approval, expected_fingerprint="f" * 64, expected_robot_id="arm-1", now_ms=start - 60_000)[0]


@pytest.mark.parametrize("change", ["signature", "operator", "expires_at_ms", "fingerprint", "robot_id", "approved_at_ms"])
def test_an_approval_edited_after_it_was_signed_is_refused(change: str) -> None:
    clock = _Clock()
    store = _store(clock)
    pending = _proposal(store)
    approval = store.confirm(pending, "ana", store.prepare(pending, "ana")["confirmationToken"])
    forged = dict(approval)
    forged[change] = forged[change] + 1 if isinstance(forged[change], int) else forged[change][:-1] + ("0" if forged[change][-1] != "0" else "1")
    assert not verify_approval(KEY, forged, expected_fingerprint=forged["fingerprint"], expected_robot_id=forged["robot_id"], now_ms=approval["approved_at_ms"])[0]


def test_every_way_of_confirming_that_is_not_the_operator_who_saw_the_summary_is_refused() -> None:
    clock = _Clock()
    store = _store(clock, token_seconds=30.0)
    one, two = _proposal(store, SEED), _proposal(store, SEED + 1, "a" * 64)
    with pytest.raises(ConfirmationError) as unprepared:
        store.confirm(one, "ana", "x.y")
    assert unprepared.value.status == 409
    token_one = store.prepare(one, "ana")["confirmationToken"]
    token_two = store.prepare(two, "ana")["confirmationToken"]
    for operator, token, status in (("ana", token_two, 403), ("luis", token_one, 403), ("ana", token_one[:-1] + "0", 403), ("ana", "nodots", 400), ("ana", 5, 400), ("", token_one, 400)):
        with pytest.raises(ConfirmationError) as refused:
            store.confirm(one, operator, token)
        assert refused.value.status == status, (operator, status)
    assert store.approved == 0
    clock.now += 31
    with pytest.raises(ConfirmationError) as late:
        store.confirm(one, "ana", token_one)
    assert late.value.status == 410
    with pytest.raises(ConfirmationError) as stale:
        store.confirm(one, "ana", token_one)
    assert stale.value.status == 409  # after a late token the summary has to be shown again


def test_a_second_prepare_replaces_the_token_of_the_first() -> None:
    store = _store(_Clock())
    pending = _proposal(store)
    first = store.prepare(pending, "ana")["confirmationToken"]
    second = store.prepare(pending, "ana")["confirmationToken"]
    with pytest.raises(ConfirmationError):
        store.confirm(pending, "ana", first)
    assert store.confirm(pending, "ana", second)["approved"] is True


def test_a_proposal_nobody_answers_expires_and_the_queue_is_bounded() -> None:
    clock = _Clock()
    store = _store(clock, ttl_seconds=60.0, max_pending=4)
    first = _proposal(store)
    for n in range(6):
        _proposal(store, SEED + n, "b" * 64)
    assert len(store.list()) == 4
    with pytest.raises(ConfirmationError) as gone:
        store.prepare(first, "ana")  # the oldest was pushed out by newer ones
    assert gone.value.status == 404
    clock.now += 61
    assert store.list() == []


def test_a_rejection_is_final_and_counted() -> None:
    store = _store(_Clock())
    pending = _proposal(store)
    assert store.reject(pending, "ana")["approved"] is False
    assert store.rejected == 1 and store.list() == []
    with pytest.raises(ConfirmationError):
        store.reject(pending, "ana")
