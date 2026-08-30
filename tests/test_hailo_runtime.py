# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_hailo_runtime.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

from pathlib import Path

import pytest

from hydra_umc_vla_engine.action_tokens import TokenizationError
from hydra_umc_vla_engine.hailo_runtime import (
    HailoNotAvailableError,
    HailoVlaModel,
    hailo_output_to_tokens,
    load_hailo_vla_model,
    open_vdevice,
)
from hydra_umc_vla_engine.model_manifest import validate_inference_output


def _fake_model() -> HailoVlaModel:
    # Constructed directly (never via load_hailo_vla_model, which needs
    # real hailort) - proves hailo_output_to_tokens works against any
    # object with the real HailoVlaModel shape, hailort installed or not.
    return HailoVlaModel(
        hef_path=Path("vla-policy.hef"),
        input_name="vla_input",
        input_shape=(224, 224, 3),
        output_name="vla_output",
        output_shape=(8,),
        network_group=object(),
        input_vstream_params=object(),
        output_vstream_params=object(),
    )


class _FakeArray:
    """Stands in for a real numpy ndarray: only .tolist() is used."""

    def __init__(self, data: list) -> None:
        self._data = data

    def tolist(self) -> list:
        return self._data


def test_open_vdevice_raises_clear_error_without_hailort() -> None:
    # hailort is not installed on this development machine - the real,
    # honest state this module must degrade to cleanly rather than
    # letting a bare ImportError surface.
    with pytest.raises(HailoNotAvailableError, match="hailort is not installed"):
        open_vdevice()


def test_load_hailo_vla_model_raises_clear_error_without_hailort() -> None:
    with pytest.raises(HailoNotAvailableError, match="hailort is not installed"):
        load_hailo_vla_model(vdevice=object(), hef_path=Path("vla-policy.hef"))


def test_hailo_output_to_tokens_batched_ndarray_shape() -> None:
    model = _fake_model()
    # Real HailoRT InferVStreams.infer() batches output: shape (1, N).
    raw_output = {"vla_output": _FakeArray([[10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 200.0, 0.87]])}

    result = hailo_output_to_tokens(raw_output, model)

    assert result["tokens"] == [10, 20, 30, 40, 50, 60, 200]
    assert result["confidence"] == pytest.approx(0.87)
    # The exact shape model_manifest.validate_inference_output() checks
    # this engine's real contract against - proves the adapter output is
    # genuinely compatible with the rest of this engine, not just
    # shaped like it.
    assert validate_inference_output(result) == []


def test_hailo_output_to_tokens_unbatched_shape() -> None:
    model = _fake_model()
    raw_output = {"vla_output": _FakeArray([1.4, 2.6, 3.0, 4.0, 5.0, 6.0, 255.0, 0.5])}

    result = hailo_output_to_tokens(raw_output, model)

    assert result["tokens"] == [1, 3, 3, 4, 5, 6, 255]
    assert validate_inference_output(result) == []


def test_hailo_output_to_tokens_plain_list_without_tolist() -> None:
    model = _fake_model()
    raw_output = {"vla_output": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]}

    result = hailo_output_to_tokens(raw_output, model)

    assert result["tokens"] == [0, 0, 0, 0, 0, 0, 0]
    assert result["confidence"] == pytest.approx(1.0)


def test_hailo_output_to_tokens_missing_output_vstream() -> None:
    model = _fake_model()

    with pytest.raises(TokenizationError, match="missing expected vstream"):
        hailo_output_to_tokens({"some_other_output": _FakeArray([1.0])}, model)


def test_hailo_output_to_tokens_wrong_arity() -> None:
    model = _fake_model()
    raw_output = {"vla_output": _FakeArray([1.0, 2.0, 3.0])}

    with pytest.raises(TokenizationError, match="expected 8 values"):
        hailo_output_to_tokens(raw_output, model)
