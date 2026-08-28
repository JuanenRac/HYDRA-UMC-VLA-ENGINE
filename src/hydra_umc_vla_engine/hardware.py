# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/hardware.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real, honest hardware/model-availability probes - no real VLA
inference exists yet (see main.py's own header), so the only real thing
this module can do today is report, truthfully, whether the two real
prerequisites inference would need are actually present: the Hailo-10
NPU device node, and this engine's own real, shared model weights
(owned by the parent HYDRA-UMC-COGNITIVE-NODE - see its own
docker-compose.yml and models.py). Same honest-probe pattern as the
sibling HYDRA-UMC-VISION-NODE's own hardware.py.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

HAILO_DEVICE_PATH = Path("/dev/hailo0")

# This engine has no models/ of its own (pruned - see README's own
# Architecture section): the real shared weights live in the parent
# HYDRA-UMC-COGNITIVE-NODE's own models/ directory, one level up from
# the sibling workspace this repo is checked out into.
PARENT_REPO_NAME = "HYDRA-UMC-COGNITIVE-NODE"
PARENT_MODELS_DIR_NAME = "models"


def accelerator_available() -> bool:
    """Real probe of the Hailo-10 NPU device node - honestly False on
    any machine without the real hardware, never assumed True."""
    return HAILO_DEVICE_PATH.exists()


def model_weights_available(workspace_root: Path) -> bool:
    """Real probe of the parent's real, shared models/ directory -
    `workspace_root` is the directory containing this repo's own
    checkout as a sibling of HYDRA-UMC-COGNITIVE-NODE (the same layout
    `check_family_status` in that parent repo already assumes). Empty
    counts as unavailable, the same real convention the parent's own
    `check_shared_models()` uses - a checked-out-but-never-provisioned
    directory has no real weights either way."""
    models_dir = workspace_root / PARENT_REPO_NAME / PARENT_MODELS_DIR_NAME
    return models_dir.is_dir() and any(models_dir.iterdir())


class EngineMode(str, enum.Enum):
    """The real, honest state this engine can report today - never a
    fourth "ready to infer" value, since no real inference path exists
    yet regardless of what hardware/weights are present."""

    NO_ACCELERATOR = "no_accelerator"
    NO_MODEL_WEIGHTS = "no_model_weights"
    HARDWARE_READY_NO_INFERENCE = "hardware_ready_no_inference"


@dataclass(frozen=True)
class EngineStatus:
    accelerator_present: bool
    model_weights_present: bool
    mode: EngineMode


def determine_mode(accelerator_present: bool, model_weights_present: bool) -> EngineMode:
    """Pure decision logic, real and testable without touching a
    filesystem or device node. Accelerator is checked before model
    weights - the cheaper, more fundamental precondition (a device node
    check) is reported first, same ordering principle as
    HYDRA-UMC-DETECTION-HEF's own safe_load() checking architecture
    compatibility before a checksum."""
    if not accelerator_present:
        return EngineMode.NO_ACCELERATOR
    if not model_weights_present:
        return EngineMode.NO_MODEL_WEIGHTS
    # Both real prerequisites are present, but this v0 still has no real
    # inference code (see main.py's own header) - reporting readiness
    # here would be a real lie about a capability that doesn't exist yet.
    return EngineMode.HARDWARE_READY_NO_INFERENCE


def check_engine_status(workspace_root: Path) -> EngineStatus:
    accelerator_present = accelerator_available()
    model_weights_present = model_weights_available(workspace_root)
    return EngineStatus(
        accelerator_present=accelerator_present,
        model_weights_present=model_weights_present,
        mode=determine_mode(accelerator_present, model_weights_present),
    )
