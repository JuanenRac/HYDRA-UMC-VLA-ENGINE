"""Property tests of the action tokens and the trajectory with hypothesis.

hypothesis is a development dependency only (the `dev` extra); where it is not installed this module is skipped, and the
engine itself has no runtime dependency on it. The examples are generated and shrunk by hypothesis, so a failure prints
the smallest input that breaks a property.
"""
import math

import pytest

hypothesis = pytest.importorskip("hypothesis")

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from hydra_umc_vla_engine.action_tokens import (  # noqa: E402
    MAX_VOCAB_SIZE,
    MIN_VOCAB_SIZE,
    VLA_ACTION_SPACE,
    TokenizationError,
    decode_action,
    encode_action,
)
from hydra_umc_vla_engine.trajectory import Pose, TrajectoryError, integrate_trajectory  # noqa: E402

settings.register_profile("engine", max_examples=200, deadline=None)
settings.load_profile("engine")

finite = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)
vocab_sizes = st.one_of(st.sampled_from([MIN_VOCAB_SIZE, 3, 16, 256, 1024, MAX_VOCAB_SIZE]), st.integers(MIN_VOCAB_SIZE, MAX_VOCAB_SIZE))
action_vectors = st.tuples(*[finite for _ in VLA_ACTION_SPACE])


def in_range_vectors():
    return st.tuples(*[st.floats(min_value=spec.min, max_value=spec.max, allow_nan=False) for spec in VLA_ACTION_SPACE])


@given(action_vectors, vocab_sizes)
def test_every_token_is_a_valid_bin(values, vocab_size):
    tokens = encode_action(values, vocab_size=vocab_size)
    assert len(tokens) == len(VLA_ACTION_SPACE)
    assert all(isinstance(token, int) and 0 <= token < vocab_size for token in tokens)


@given(in_range_vectors(), vocab_sizes)
def test_decoding_an_encoding_is_within_half_a_bin(values, vocab_size):
    decoded = decode_action(encode_action(values, vocab_size=vocab_size), vocab_size=vocab_size, snap_zero=False)
    for value, back, spec in zip(values, decoded, VLA_ACTION_SPACE, strict=False):
        half_bin = (spec.max - spec.min) / vocab_size / 2
        assert abs(back - value) <= half_bin * (1 + 1e-9) + 1e-12


@given(st.data(), vocab_sizes)
def test_a_decoded_token_encodes_back_to_itself(data, vocab_size):
    tokens = tuple(data.draw(st.integers(0, vocab_size - 1)) for _ in VLA_ACTION_SPACE)
    assert encode_action(decode_action(tokens, vocab_size=vocab_size, snap_zero=False), vocab_size=vocab_size) == tokens


@given(finite, finite, vocab_sizes)
def test_encoding_never_reverses_the_order_of_two_values(first, second, vocab_size):
    low, high = sorted((first, second))
    for index, _spec in enumerate(VLA_ACTION_SPACE):
        a = [0.0] * len(VLA_ACTION_SPACE)
        b = [0.0] * len(VLA_ACTION_SPACE)
        a[index], b[index] = low, high
        assert encode_action(tuple(a), vocab_size=vocab_size)[index] <= encode_action(tuple(b), vocab_size=vocab_size)[index]


@given(action_vectors, st.sampled_from([math.nan, math.inf, -math.inf]), st.integers(0, len(VLA_ACTION_SPACE) - 1))
def test_a_value_that_is_not_finite_is_never_encoded(values, bad, index):
    broken = list(values)
    broken[index] = bad
    with pytest.raises(TokenizationError):
        encode_action(tuple(broken))


@given(st.integers(-10, MIN_VOCAB_SIZE - 1) | st.integers(MAX_VOCAB_SIZE + 1, MAX_VOCAB_SIZE + 10))
def test_a_vocabulary_size_out_of_range_is_refused(vocab_size):
    with pytest.raises(TokenizationError):
        encode_action((0.0,) * len(VLA_ACTION_SPACE), vocab_size=vocab_size)


poses = st.builds(
    Pose,
    *[st.floats(min_value=-10, max_value=10, allow_nan=False) for _ in range(6)],
    st.floats(min_value=0, max_value=1, allow_nan=False),
)
actions = st.lists(in_range_vectors(), max_size=40)


@given(poses, actions)
def test_a_trajectory_has_one_pose_per_action_and_keeps_its_angles_wrapped(start, steps):
    path = integrate_trajectory(start, steps)
    assert len(path) == len(steps) + 1
    assert path[0] == start
    for pose in path[1:]:
        assert all(-math.pi <= angle <= math.pi for angle in (pose.roll, pose.pitch, pose.yaw))


@given(poses, actions)
def test_the_position_is_the_start_plus_the_sum_of_the_deltas_and_the_gripper_is_the_last_command(start, steps):
    path = integrate_trajectory(start, steps)
    last = path[-1]
    for axis, name in enumerate(("x", "y", "z")):
        expected = getattr(start, name) + sum(step[axis] for step in steps)
        assert last.__dict__[name] == pytest.approx(expected, abs=1e-9)
    if steps:
        assert last.gripper == steps[-1][6]


@given(poses, actions, st.integers(0, 39), st.sampled_from([1.0, -1.0]))
def test_a_delta_outside_the_action_space_rejects_the_whole_sequence(start, steps, where, sign):
    if not steps:
        return
    broken = [list(step) for step in steps]
    broken[where % len(steps)][0] = sign * (VLA_ACTION_SPACE[0].max + 1.0)
    with pytest.raises(TrajectoryError):
        integrate_trajectory(start, [tuple(step) for step in broken])
