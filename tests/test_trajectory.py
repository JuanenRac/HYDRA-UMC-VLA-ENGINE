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


def test_rotation_deltas_accumulate():
    start = Pose(0, 0, 0, 0, 0, 0, gripper=0.0)
    actions = [(0, 0, 0, 0.1, 0.0, 0.0, 0.0), (0, 0, 0, 0.1, 0.0, 0.0, 0.0)]
    poses = integrate_trajectory(start, actions)
    assert poses[2].roll == pytest.approx(0.2)
