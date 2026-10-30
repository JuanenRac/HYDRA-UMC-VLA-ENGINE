# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_rotation_quaternion.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
from __future__ import annotations

import json
import math

import pytest

from hydra_umc_vla_engine.action_tokens import ActionSpec
from hydra_umc_vla_engine.rotation import Quaternion
from hydra_umc_vla_engine.rotation_policy import (
    RotationConfigError,
    RotationPolicy,
    load_rotation_policy,
)
from hydra_umc_vla_engine.trajectory import Pose, integrate_trajectory

BASE = RotationPolicy("quaternion", "base")
TOOL = RotationPolicy("quaternion", "tool")
EULER = RotationPolicy("euler", "base")
# a wide action space, so that real rotations (not only the small steps of the default one) can be integrated
WIDE = tuple(ActionSpec(name, -4.0, 4.0) for name in ("dx", "dy", "dz", "droll", "dpitch", "dyaw")) + (ActionSpec("gripper", 0.0, 1.0),)
START = Pose(0, 0, 0, 0, 0, 0, 0)


def _final(actions, policy):
    return integrate_trajectory(START, actions, WIDE, policy)[-1]


def test_rotation_deltas_do_not_commute_and_the_order_is_kept() -> None:
    quarter = math.pi / 2
    x_then_y = _final([(0, 0, 0, quarter, 0, 0, 0), (0, 0, 0, 0, quarter, 0, 0)], BASE)
    y_then_x = _final([(0, 0, 0, 0, quarter, 0, 0), (0, 0, 0, quarter, 0, 0, 0)], BASE)
    assert x_then_y.quaternion.angle_to(y_then_x.quaternion) > 1.0
    # exactly the composition of the two turns, about the fixed axes of the base
    expected = Quaternion.from_rotation_vector((0, quarter, 0)) * Quaternion.from_rotation_vector((quarter, 0, 0))
    assert x_then_y.quaternion.angle_to(expected) < 1e-9
    # adding the angles gives the same pose for both orders, which is the error this replaces
    assert _final([(0, 0, 0, quarter, 0, 0, 0), (0, 0, 0, 0, quarter, 0, 0)], EULER).roll == pytest.approx(
        _final([(0, 0, 0, 0, quarter, 0, 0), (0, 0, 0, quarter, 0, 0, 0)], EULER).roll
    )


def test_the_frame_of_the_delta_is_the_one_declared() -> None:
    start = Pose(0, 0, 0, 0, 0, math.pi / 2, 0)  # the tool is turned a quarter about the base z
    about_base_x = integrate_trajectory(start, [(0, 0, 0, 0.5, 0, 0, 0)], WIDE, BASE)[-1].quaternion
    about_tool_x = integrate_trajectory(start, [(0, 0, 0, 0.5, 0, 0, 0)], WIDE, TOOL)[-1].quaternion
    assert about_base_x.angle_to(about_tool_x) > 0.5
    expected_base = Quaternion.from_rotation_vector((0.5, 0, 0)) * start.quaternion
    expected_tool = start.quaternion * Quaternion.from_rotation_vector((0.5, 0, 0))
    assert about_base_x.angle_to(expected_base) < 1e-9
    assert about_tool_x.angle_to(expected_tool) < 1e-9


def test_a_small_turn_near_pitch_ninety_stays_a_small_turn() -> None:
    start = Pose(0, 0, 0, 0, math.radians(89.9), 0, 0)
    end = integrate_trajectory(start, [(0, 0, 0, math.radians(1.0), 0, 0, 0)], WIDE, BASE)[-1]
    assert start.quaternion.angle_to(end.quaternion) == pytest.approx(math.radians(1.0), abs=1e-6)


def test_the_orientation_is_always_a_unit_quaternion_over_a_long_sequence() -> None:
    actions = [(0, 0, 0, 0.3, -0.2, 0.4, 0.5)] * 400
    poses = integrate_trajectory(START, actions, WIDE, BASE)
    assert all(abs(p.quaternion.norm - 1.0) < 1e-9 for p in poses)
    assert all(-math.pi <= p.roll <= math.pi and -math.pi <= p.yaw <= math.pi for p in poses)


def test_the_earlier_addition_of_angles_is_still_available_from_the_configuration() -> None:
    pose = integrate_trajectory(START, [(0, 0, 0, 0.1, 0.2, 0.3, 0)], WIDE, EULER)[-1]
    assert (pose.roll, pose.pitch, pose.yaw) == pytest.approx((0.1, 0.2, 0.3))


def test_the_configuration_file_chooses_the_integration_and_the_frame(tmp_path, monkeypatch) -> None:
    assert load_rotation_policy() == RotationPolicy("quaternion", "base")
    config = tmp_path / "vla.json"
    config.write_text(json.dumps({"rotation": {"integration": "Euler", "frame": "tool"}}), encoding="utf-8")
    assert load_rotation_policy(config) == RotationPolicy("euler", "tool")
    monkeypatch.setenv("HYDRA_UMC_VLA_ENGINE_CONFIG", str(config))
    assert load_rotation_policy().integration == "euler"
    config.write_text(json.dumps({"rotation": {"frame": "world"}}), encoding="utf-8")
    with pytest.raises(RotationConfigError):
        load_rotation_policy(config)
    with pytest.raises(RotationConfigError):
        load_rotation_policy(tmp_path / "missing.json")
