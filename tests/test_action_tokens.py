import pytest

from hydra_umc_vla_engine.action_tokens import (
    ActionSpec,
    TokenizationError,
    VLA_ACTION_SPACE,
    decode_action,
    encode_action,
)


def test_action_spec_rejects_invalid_bounds():
    with pytest.raises(TokenizationError):
        ActionSpec("x", 1.0, 0.0)


def test_encode_zero_maps_to_middle_bin():
    # dx spans [-0.05, 0.05]; 0.0 is the exact midpoint.
    tokens = encode_action((0.0,) * 7)
    assert tokens[0] == 128  # vocab_size=256, midpoint bin


def test_encode_min_maps_to_first_bin():
    values = tuple(spec.min for spec in VLA_ACTION_SPACE)
    tokens = encode_action(values)
    assert tokens == (0,) * 7


def test_encode_max_maps_to_last_bin():
    values = tuple(spec.max for spec in VLA_ACTION_SPACE)
    tokens = encode_action(values)
    assert tokens == (255,) * 7


def test_encode_clamps_out_of_range_values():
    values = (10.0, -10.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    tokens = encode_action(values)
    assert tokens[0] == 255  # clamped to dx.max
    assert tokens[1] == 0    # clamped to dy.min


def test_encode_wrong_dimensionality_raises():
    with pytest.raises(TokenizationError):
        encode_action((0.0, 0.0, 0.0))


def test_decode_rejects_out_of_range_token():
    with pytest.raises(TokenizationError):
        decode_action((256, 0, 0, 0, 0, 0, 0))
    with pytest.raises(TokenizationError):
        decode_action((-1, 0, 0, 0, 0, 0, 0))


def test_decode_wrong_dimensionality_raises():
    with pytest.raises(TokenizationError):
        decode_action((0, 0, 0))


def test_round_trip_within_bin_resolution():
    original = (0.02, -0.03, 0.01, 0.05, -0.04, 0.02, 0.7)
    tokens = encode_action(original)
    decoded = decode_action(tokens)
    for orig, dec, spec in zip(original, decoded, VLA_ACTION_SPACE):
        bin_width = (spec.max - spec.min) / 256
        assert abs(orig - dec) <= bin_width


def test_decode_bin_center_not_bin_edge():
    # Token 0 with vocab_size=2 over [0, 1] should decode to the center of
    # the first half, 0.25, not the edge 0.0.
    spec = (ActionSpec("x", 0.0, 1.0),)
    value = decode_action((0,), specs=spec, vocab_size=2)
    assert value[0] == pytest.approx(0.25)
