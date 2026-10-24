# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_guard.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""The trajectory guard: the limits of the cell applied to what a model proposes."""
from __future__ import annotations

import json
import math
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from hydra_umc_vla_engine import main as engine_main
from hydra_umc_vla_engine.api import VlaEngineServer
from hydra_umc_vla_engine.guard import (
    CLAMPED,
    OK,
    REJECTED,
    Box,
    GuardConfigError,
    GuardLimits,
    GuardZone,
    guard_trajectory,
    load_limits,
    parse_limits,
)
from hydra_umc_vla_engine.trajectory import Pose, integrate_trajectory

CELL = {
    "workspace": {"min": {"x": -0.5, "y": -0.5, "z": 0.0}, "max": {"x": 0.5, "y": 0.5, "z": 0.6}},
    "max_linear_step_m": 0.02,
    "max_angular_step_rad": 0.1,
    "zones": [
        {"id": "operator", "level": "danger", "min": {"x": 0.2, "y": -0.1, "z": 0.0}, "max": {"x": 0.3, "y": 0.1, "z": 0.6}},
        {"id": "approach", "level": "warning", "min": {"x": 0.0, "y": -0.1, "z": 0.0}, "max": {"x": 0.2, "y": 0.1, "z": 0.6}},
    ],
}
START = Pose(-0.3, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0)


def limits(**change) -> GuardLimits:
    raw = json.loads(json.dumps(CELL))
    raw.update(change)
    return parse_limits(raw)


def moves(*steps: tuple[float, float, float], start: Pose = START) -> list[Pose]:
    return integrate_trajectory(start, [(dx, dy, dz, 0.0, 0.0, 0.0, 0.0) for dx, dy, dz in steps])


def test_a_trajectory_that_respects_every_limit_is_ok_and_unchanged() -> None:
    poses = moves(*[(0.01, 0.0, 0.0)] * 5)
    result = guard_trajectory(poses, limits())
    assert result.outcome == OK and result.reasons == []
    assert result.poses == poses


def test_a_step_longer_than_the_limit_is_cut_back_and_the_later_steps_follow_from_the_cut() -> None:
    poses = moves((0.05, 0.0, 0.0), (0.01, 0.0, 0.0))
    result = guard_trajectory(poses, limits())
    assert result.outcome == CLAMPED
    assert result.poses[1].x == pytest.approx(START.x + 0.02)
    assert result.poses[2].x == pytest.approx(START.x + 0.03), "the second step starts where the first one was cut"
    assert any("cut" in r for r in result.reasons)


def test_the_cut_keeps_the_direction_of_the_move() -> None:
    result = guard_trajectory(moves((0.03, 0.04, 0.0)), limits())
    step = (result.poses[1].x - START.x, result.poses[1].y - START.y)
    assert math.hypot(*step) == pytest.approx(0.02)
    assert step[1] / step[0] == pytest.approx(0.04 / 0.03)


def test_a_turn_longer_than_the_limit_is_cut_back() -> None:
    poses = integrate_trajectory(START, [(0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0)])
    result = guard_trajectory(poses, limits(max_angular_step_rad=0.04))
    assert result.outcome == CLAMPED
    assert result.poses[1].roll == pytest.approx(0.04)


def test_the_tool_is_held_at_the_edge_of_the_work_volume() -> None:
    start = Pose(0.49, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0)
    big = limits(max_linear_step_m=0.5)
    poses = moves((0.05, 0.0, 0.0), (0.05, 0.0, 0.0), start=start)
    # the zone of the operator is at x 0.2-0.3: this start is beyond it, so the move only meets the wall
    result = guard_trajectory(poses, big)
    assert result.outcome == CLAMPED
    assert all(p.x <= 0.5 + 1e-12 for p in result.poses)
    assert result.poses[-1].x == pytest.approx(0.5)


def test_a_start_outside_the_volume_or_inside_a_danger_zone_is_rejected() -> None:
    assert guard_trajectory(moves((0.01, 0, 0), start=Pose(2.0, 0, 0.3, 0, 0, 0, 0)), limits()).outcome == REJECTED
    inside = guard_trajectory(moves((0.01, 0, 0), start=Pose(0.25, 0.0, 0.3, 0, 0, 0, 0)), limits())
    assert inside.outcome == REJECTED and "danger zone" in inside.reasons[0]


def test_entering_a_danger_zone_rejects_the_trajectory_and_gives_no_poses() -> None:
    poses = moves(*[(0.02, 0.0, 0.0)] * 40)
    result = guard_trajectory(poses, limits())
    assert result.outcome == REJECTED
    assert result.poses == []
    assert result.rejected_at_step is not None and 1 <= result.rejected_at_step <= 40
    assert "operator" in result.reasons[-1]


def test_a_single_step_that_jumps_over_a_danger_zone_is_still_caught() -> None:
    # the zone is 0.1 m thick; one step of 0.4 m (not cut, on purpose) crosses it from one side to the other
    wide = limits(max_linear_step_m=0.5)
    poses = moves(*[(0.05, 0.0, 0.0)] * 6, start=Pose(0.1, 0.0, 0.3, 0, 0, 0, 0))
    poses = [poses[0], Pose(0.45, 0.0, 0.3, 0, 0, 0, 0)]  # one step from one side of the zone to the other, as a model that jumped would give
    result = guard_trajectory(poses, wide)
    assert result.outcome == REJECTED, "the segment is checked, not only the point where the step ends"


def test_the_tool_that_goes_around_a_danger_zone_is_fine() -> None:
    poses = moves(*[(0.0, 0.02, 0.0)] * 6, start=Pose(0.25, 0.2, 0.3, 0, 0, 0, 0))
    assert guard_trajectory(poses, limits()).outcome == OK


def test_inside_a_warning_zone_the_steps_are_held_to_a_fraction() -> None:
    poses = moves((0.02, 0.0, 0.0), start=Pose(0.05, 0.0, 0.3, 0, 0, 0, 0))
    result = guard_trajectory(poses, limits(warning_step_factor=0.5))
    assert result.outcome == CLAMPED
    assert result.poses[1].x - 0.05 == pytest.approx(0.01)
    assert "warning zone" in result.reasons[0]


def test_how_much_a_step_may_change_from_the_one_before_is_limited() -> None:
    poses = moves((0.02, 0.0, 0.0), (-0.02, 0.0, 0.0))
    result = guard_trajectory(poses, limits(max_linear_step_change_m=0.01))
    assert result.outcome == CLAMPED
    steps = [result.poses[i + 1].x - result.poses[i].x for i in range(2)]
    assert abs(steps[1] - steps[0]) <= 0.01 + 1e-12


def test_a_gripper_out_of_its_range_is_rejected() -> None:
    poses = integrate_trajectory(START, [(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)])
    poses.append(Pose(*poses[-1].__dict__.values()) if False else Pose(START.x, START.y, START.z, 0, 0, 0, 3.0))
    result = guard_trajectory(poses, limits())
    assert result.outcome == REJECTED and "gripper" in result.reasons[-1]


def test_an_empty_trajectory_is_rejected() -> None:
    assert guard_trajectory([], limits()).outcome == REJECTED


@pytest.mark.parametrize(
    "bad",
    [
        {"workspace": {"min": {"x": 1, "y": 0, "z": 0}, "max": {"x": 0, "y": 1, "z": 1}}},  # min above max
        {"max_linear_step_m": 0},
        {"max_angular_step_rad": -1},
        {"max_linear_step_m": float("nan")},
        {"max_linear_step_change_m": 0},
        {"warning_step_factor": 2},
        {"gripper": {"min": 1, "max": 0}},
        {"zones": "none"},
        {"zones": [{"id": "a", "level": "mild", "min": {"x": 0, "y": 0, "z": 0}, "max": {"x": 1, "y": 1, "z": 1}}]},
        {"zones": [{"id": "a", "level": "danger", "min": {"x": 0, "y": 0}, "max": {"x": 1, "y": 1, "z": 1}}]},
    ],
)
def test_a_guard_file_that_cannot_be_trusted_is_refused(bad: dict) -> None:
    raw = json.loads(json.dumps(CELL))
    raw.update(bad)
    with pytest.raises(GuardConfigError):
        parse_limits(raw)


def test_the_two_zones_with_the_same_id_and_a_file_without_limits_are_refused() -> None:
    raw = json.loads(json.dumps(CELL))
    raw["zones"].append(raw["zones"][0])
    with pytest.raises(GuardConfigError):
        parse_limits(raw)
    with pytest.raises(GuardConfigError):
        parse_limits({"workspace": CELL["workspace"]})
    with pytest.raises(GuardConfigError):
        parse_limits([])


def test_a_guard_file_is_read_and_a_missing_or_broken_one_is_an_error(tmp_path: Path) -> None:
    good = tmp_path / "cell.json"
    good.write_text(json.dumps(CELL), encoding="utf-8")
    assert load_limits(good).max_linear_step == 0.02
    with pytest.raises(GuardConfigError):
        load_limits(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{nope", encoding="utf-8")
    with pytest.raises(GuardConfigError):
        load_limits(broken)
    nan = tmp_path / "nan.json"
    nan.write_text('{"workspace": {"min": {"x": NaN, "y": 0, "z": 0}, "max": {"x": 1, "y": 1, "z": 1}}, "max_linear_step_m": 1, "max_angular_step_rad": 1}', encoding="utf-8")
    with pytest.raises(GuardConfigError):
        load_limits(nan)


def test_the_segment_test_of_a_box() -> None:
    box = Box((0, 0, 0), (1, 1, 1))
    assert box.crossed_by((-1, 0.5, 0.5), (2, 0.5, 0.5))
    assert not box.crossed_by((-1, 2, 0.5), (2, 2, 0.5))
    assert box.crossed_by((0.5, 0.5, 0.5), (0.6, 0.5, 0.5))
    assert not box.crossed_by((1.1, 0, 0), (1.2, 0, 0))
    assert box.crossed_by((1.0, 0.5, 0.5), (1.5, 0.5, 0.5)), "touching the face counts"


# ---- through the HTTP API ----


def _serve(guard: GuardLimits | None, require_guard: bool = False):
    server = VlaEngineServer(("127.0.0.1", 0), Path("."), "", guard, require_guard)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def _post(url: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def _stop(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_the_api_returns_the_guarded_trajectory_and_says_what_the_guard_did() -> None:
    server, thread, base = _serve(limits())
    try:
        status, body = _post(f"{base}/trajectory/integrate", {"start": list(START.__dict__.values())[:6], "actions": [[0.05, 0, 0, 0, 0, 0, 0]]})
        assert status == 200
        assert body["guard"]["outcome"] == CLAMPED
        assert body["poses"][1]["x"] == pytest.approx(START.x + 0.02)
        assert body["proposal"]["authorized"] is False
    finally:
        _stop(server, thread)


def test_the_api_refuses_a_trajectory_the_guard_rejects_and_offers_no_proposal() -> None:
    server, thread, base = _serve(limits())
    try:
        actions = [[0.02, 0, 0, 0, 0, 0, 0]] * 40
        status, body = _post(f"{base}/trajectory/integrate", {"start": [-0.3, 0, 0.3, 0, 0, 0], "actions": actions})
        assert status == 422
        assert body["guard"]["outcome"] == REJECTED and "proposal" not in body and "poses" not in body
    finally:
        _stop(server, thread)


def test_without_a_guard_the_response_says_so_and_with_require_guard_nothing_is_offered() -> None:
    server, thread, base = _serve(None)
    try:
        status, body = _post(f"{base}/trajectory/integrate", {"start": [0, 0, 0, 0, 0, 0], "actions": [[0.01, 0, 0, 0, 0, 0, 0]]})
        assert status == 200 and body["guard"]["outcome"] == "not_configured"
    finally:
        _stop(server, thread)
    server, thread, base = _serve(None, require_guard=True)
    try:
        status, body = _post(f"{base}/trajectory/integrate", {"start": [0, 0, 0, 0, 0, 0], "actions": [[0.01, 0, 0, 0, 0, 0, 0]]})
        assert status == 503 and "--require-guard" in body["error"]
    finally:
        _stop(server, thread)


def test_the_cli_checks_a_trajectory_against_a_guard_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    cell = tmp_path / "cell.json"
    cell.write_text(json.dumps(CELL), encoding="utf-8")
    actions = tmp_path / "a.json"
    actions.write_text(json.dumps([[0.05, 0, 0, 0, 0, 0, 0]]), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["x", "trajectory", "integrate", "--start", "-0.3,0,0.3,0,0,0", "--actions", str(actions), "--guard-file", str(cell)])
    assert engine_main.main() == 0
    captured = capsys.readouterr()
    assert "guard: clamped" in captured.err and "x=-0.280000" in captured.out
    many = tmp_path / "many.json"
    many.write_text(json.dumps([[0.02, 0, 0, 0, 0, 0, 0]] * 40), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["x", "trajectory", "integrate", "--start", "-0.3,0,0.3,0,0,0", "--actions", str(many), "--guard-file", str(cell)])
    assert engine_main.main() == 1
    assert "guard: rejected" in capsys.readouterr().err


def test_serve_refuses_to_start_with_an_unusable_guard_or_require_guard_without_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["x", "serve", "--port", "0", "--guard-file", str(bad)])
    assert engine_main.main() == 2
    monkeypatch.delenv("HYDRA_UMC_VLA_GUARD_FILE", raising=False)
    monkeypatch.setattr("sys.argv", ["x", "serve", "--port", "0", "--require-guard"])
    assert engine_main.main() == 2
    assert "guard" in capsys.readouterr().err


def test_a_zone_is_a_box_with_a_level() -> None:
    zone = GuardZone("z", "danger", Box((0, 0, 0), (1, 1, 1)))
    assert zone.level == "danger" and zone.box.contains((0.5, 0.5, 0.5))
