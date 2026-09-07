# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_hardware.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

from pathlib import Path

from hydra_umc_vla_engine.hardware import (
    EngineMode,
    check_engine_status,
    determine_mode,
    model_weights_available,
)


def test_determine_mode_no_accelerator_wins_first() -> None:
    # Accelerator is the cheaper, more fundamental check - reported even
    # when model weights also happen to be missing.
    assert determine_mode(accelerator_present=False, model_weights_present=False) == EngineMode.NO_ACCELERATOR
    assert determine_mode(accelerator_present=False, model_weights_present=True) == EngineMode.NO_ACCELERATOR


def test_determine_mode_no_model_weights() -> None:
    assert determine_mode(accelerator_present=True, model_weights_present=False) == EngineMode.NO_MODEL_WEIGHTS


def test_determine_mode_hardware_ready_still_has_no_real_inference() -> None:
    assert (
        determine_mode(accelerator_present=True, model_weights_present=True)
        == EngineMode.HARDWARE_READY_NO_INFERENCE
    )


def test_model_weights_available_false_when_parent_missing(tmp_path: Path) -> None:
    assert model_weights_available(tmp_path) is False


def test_model_weights_available_false_when_models_dir_empty(tmp_path: Path) -> None:
    (tmp_path / "HYDRA-UMC-COGNITIVE-NODE" / "models").mkdir(parents=True)

    assert model_weights_available(tmp_path) is False


def test_model_weights_available_true_with_real_content(tmp_path: Path) -> None:
    models_dir = tmp_path / "HYDRA-UMC-COGNITIVE-NODE" / "models"
    models_dir.mkdir(parents=True)
    (models_dir / "vla-weights.bin").write_bytes(b"fixture")

    assert model_weights_available(tmp_path) is True


def test_check_engine_status_on_this_real_dev_machine(tmp_path: Path) -> None:
    # A real, honest check against a real (synthetic, empty) workspace -
    # this dev machine has no /dev/hailo0, so accelerator_present must
    # be False regardless of the workspace passed in.
    status = check_engine_status(tmp_path)

    assert status.accelerator_present is False
    assert status.mode == EngineMode.NO_ACCELERATOR
