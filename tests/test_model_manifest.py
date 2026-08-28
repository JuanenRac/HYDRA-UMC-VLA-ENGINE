# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_model_manifest.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

from hydra_umc_vla_engine.action_tokens import DEFAULT_VOCAB_SIZE, VLA_ACTION_SPACE
from hydra_umc_vla_engine.model_manifest import (
    EXPECTED_MODEL_MANIFEST,
    validate_inference_output,
    validate_model_manifest,
)


def _valid_manifest() -> dict:
    return {"action_dims": len(VLA_ACTION_SPACE), "vocab_size": DEFAULT_VOCAB_SIZE, "hailo_arch": "hailo10h"}


def test_expected_manifest_mirrors_the_real_tokenizer_constants() -> None:
    assert EXPECTED_MODEL_MANIFEST.action_dims == len(VLA_ACTION_SPACE)
    assert EXPECTED_MODEL_MANIFEST.vocab_size == DEFAULT_VOCAB_SIZE


def test_validate_model_manifest_accepts_a_real_compatible_candidate() -> None:
    assert validate_model_manifest(_valid_manifest()) == []


def test_validate_model_manifest_rejects_wrong_action_dims() -> None:
    candidate = _valid_manifest()
    candidate["action_dims"] = 6

    issues = validate_model_manifest(candidate)

    assert any("action_dims" in issue for issue in issues)


def test_validate_model_manifest_rejects_wrong_vocab_size() -> None:
    candidate = _valid_manifest()
    candidate["vocab_size"] = 512

    issues = validate_model_manifest(candidate)

    assert any("vocab_size" in issue for issue in issues)


def test_validate_model_manifest_rejects_unknown_hailo_arch() -> None:
    candidate = _valid_manifest()
    candidate["hailo_arch"] = "hailo99z"

    issues = validate_model_manifest(candidate)

    assert any("hailo_arch" in issue for issue in issues)


def test_validate_model_manifest_reports_every_real_issue_at_once() -> None:
    issues = validate_model_manifest({})

    assert len(issues) == 3


def _valid_output() -> dict:
    return {"tokens": [0, 1, 2, 3, 4, 5, 255], "confidence": 0.87}


def test_validate_inference_output_accepts_a_well_formed_output() -> None:
    assert validate_inference_output(_valid_output()) == []


def test_validate_inference_output_rejects_wrong_token_count() -> None:
    output = _valid_output()
    output["tokens"] = [0, 1, 2]

    issues = validate_inference_output(output)

    assert any("expected 7 values" in issue for issue in issues)


def test_validate_inference_output_rejects_out_of_range_token() -> None:
    output = _valid_output()
    output["tokens"][0] = 256  # vocab_size=256 -> valid range is [0, 256)

    issues = validate_inference_output(output)

    assert any("tokens[0]" in issue for issue in issues)


def test_validate_inference_output_rejects_non_integer_token() -> None:
    output = _valid_output()
    output["tokens"][0] = 12.5

    issues = validate_inference_output(output)

    assert any("tokens[0]" in issue and "not an integer" in issue for issue in issues)


def test_validate_inference_output_rejects_missing_confidence() -> None:
    output = _valid_output()
    del output["confidence"]

    issues = validate_inference_output(output)

    assert any("confidence" in issue for issue in issues)


def test_validate_inference_output_rejects_out_of_range_confidence() -> None:
    output = _valid_output()
    output["confidence"] = 1.5

    issues = validate_inference_output(output)

    assert any("confidence" in issue for issue in issues)


def test_validate_inference_output_rejects_missing_tokens() -> None:
    output = _valid_output()
    del output["tokens"]

    issues = validate_inference_output(output)

    assert any("tokens" in issue for issue in issues)
