import math

import pytest

from hydra_umc_vla_engine.trajectory import Pose, TrajectoryError, integrate_trajectory


def test_integrate_accumulates_deltas():
    start = Pose(0, 0, 0, 0, 0, 0, gripper=0.0)
    actions = [
        (0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5),
        (0.01, 0.02, 0.0, 0.0, 0.0, 0.0, 1.0),
    ]
    poses = integrate_trajectory(start, actions)

    assert len(poses) == 3  # start + 2 steps
    assert poses[0] == start
    assert poses[1].x == pytest.approx(0.01)
    assert poses[2].x == pytest.approx(0.02)
    assert poses[2].y == pytest.approx(0.02)


def test_gripper_is_absolute_not_accumulated():
    start = Pose(0, 0, 0, 0, 0, 0, gripper=0.0)
    actions = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3),
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3),
    ]
    poses = integrate_trajectory(start, actions)
    # If gripper were summed it would be 0.6 at step 2 - it must stay 0.3.
    assert poses[2].gripper == pytest.approx(0.3)


def test_empty_action_sequence_returns_only_start():
    start = Pose(1, 2, 3, 0, 0, 0, gripper=0.5)
    poses = integrate_trajectory(start, [])
    assert poses == [start]


def test_wrong_action_dimensionality_raises():
    start = Pose(0, 0, 0, 0, 0, 0, gripper=0.0)
    with pytest.raises(TrajectoryError):
        integrate_trajectory(start, [(0.0, 0.0, 0.0)])


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), "0.1", True])
def test_non_finite_or_non_numeric_action_is_rejected(invalid):
    start = Pose(0, 0, 0, 0, 0, 0, gripper=0.0)
    with pytest.raises(TrajectoryError):
        integrate_trajectory(start, [(invalid, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)])


def test_non_finite_start_pose_is_rejected():
    start = Pose(float("nan"), 0, 0, 0, 0, 0, gripper=0.0)
    with pytest.raises(TrajectoryError):
        integrate_trajectory(start, [])


# (P1):
# individually-finite inputs whose ACCUMULATED sum overflows to inf.

def test_accumulated_linear_overflow_is_rejected_not_returned_as_infinite():
    # Both start.x and the delta are perfectly finite on their own -
    # it's the SUM that overflows a float, silently (unlike float ** 2,
    # which Python raises OverflowError for instead).
    start = Pose(1e308, 0, 0, 0, 0, 0, gripper=0.0)
    with pytest.raises(TrajectoryError, match="pose after action 0"):
        integrate_trajectory(start, [(1e308, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)])


def test_accumulated_angular_overflow_is_rejected_with_a_clear_message():
    # roll+droll overflowing to inf used to reach math.sin/cos inside
    # _wrap_angle and raise an unlabeled "math domain error" instead of
    # this same clear message every other field gets.
    start = Pose(0, 0, 0, 1e308, 0, 0, gripper=0.0)
    with pytest.raises(TrajectoryError, match="pose after action 0.roll"):
        integrate_trajectory(start, [(0.0, 0.0, 0.0, 1e308, 0.0, 0.0, 0.0)])


def test_a_sequence_that_overflows_partway_through_rejects_the_whole_trajectory():
    # The real closure criterion: no caller ever sees a trajectory
    # truncated right before the overflowing step - integrate_trajectory
    # either returns the whole thing or raises, never something
    # partially built. Confirmed via the same exception also propagating
    # even after 2 genuinely valid steps already accumulated fine.
    start = Pose(0, 0, 0, 0, 0, 0, gripper=0.0)
    actions = [
        (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (1e308, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (1e308, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ]
    with pytest.raises(TrajectoryError, match="pose after action 3"):
        integrate_trajectory(start, actions)


def test_rotation_deltas_accumulate():
    start = Pose(0, 0, 0, 0, 0, 0, gripper=0.0)
    actions = [(0, 0, 0, 0.1, 0.0, 0.0, 0.0), (0, 0, 0, 0.1, 0.0, 0.0, 0.0)]
    poses = integrate_trajectory(start, actions)
    assert poses[2].roll == pytest.approx(0.2)


def test_rotation_wraps_instead_of_growing_without_bound():
    # Found while auditing the code: continuous
    # wrist rotation (many small yaw deltas in the same direction) used to
    # accumulate as a plain sum with no wraparound, unlike sibling
    # HYDRA-UMC-VISUAL-SERVOING-API's own shortest-turn angle wrapping. A
    # downstream motor command must see the canonical (-pi, pi] angle, not
    # an ever-growing raw radian value.
    start = Pose(0, 0, 0, 0, 0, 0, gripper=0.0)
    step = math.pi / 2
    actions = [(0, 0, 0, 0.0, 0.0, step, 0.0)] * 5  # 5 * pi/2 = 2.5*pi total
    poses = integrate_trajectory(start, actions)
    final_yaw = poses[-1].yaw
    assert -math.pi < final_yaw <= math.pi
    # 2.5*pi wraps to 0.5*pi (equivalent orientation, canonical range).
    assert final_yaw == pytest.approx(math.pi / 2)


def test_rotation_wrap_preserves_the_real_orientation():
    # The wrapped angle must still be the SAME physical orientation, not
    # just clamped into range - sin/cos at the wrapped angle must match
    # the true unwrapped total.
    start = Pose(0, 0, 0, 0, 0, 0, gripper=0.0)
    unwrapped_total = 3 * math.pi + 0.4
    actions = [(0, 0, 0, 0.0, 0.0, unwrapped_total, 0.0)]
    poses = integrate_trajectory(start, actions)
    wrapped = poses[-1].yaw
    assert math.sin(wrapped) == pytest.approx(math.sin(unwrapped_total), abs=1e-9)
    assert math.cos(wrapped) == pytest.approx(math.cos(unwrapped_total), abs=1e-9)
