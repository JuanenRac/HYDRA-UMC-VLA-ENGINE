# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/hailo_runtime.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real HailoRT (hailo_platform) integration boundary for VLA inference.

hardware.py already reports, honestly, whether a Hailo-10 device node and
this engine's shared model weights are present - but until now nothing in
this repo actually knew how to *load* a real HailoRT model or turn its raw
output into this engine's own token contract (model_manifest.py,
action_tokens.py). This module is that missing piece, prepared ahead of
the real Hailo-10 module landing (see the project's own README/roadmap):
when it plugs in, `load_hailo_vla_model()` is the one function that needs
to actually run against real silicon - everything else here is real,
tested logic today.

The real pip package is `hailort` (not on PyPI - Hailo Developer Zone, or
`apt install hailo-all` on Raspberry Pi OS with a Hailo module attached);
its Python import name is `hailo_platform`. Real, confirmed API surface
used here: `VDevice()`, `HEF(path)`, `ConfigureParams.create_from_hef(hef,
interface=HailoStreamInterface.PCIe)`, `vdevice.configure(hef,
configure_params)` -> a list of `ConfiguredNetworkGroup`,
`InputVStreamParams.make(network_group)` /
`OutputVStreamParams.make(network_group)`, and each vstream info exposing
real `.name`/`.shape` attributes via `hef.get_input_vstream_infos()` /
`get_output_vstream_infos()`. Actually running inference
(`InferVStreams(...)` as a context manager around an activated network
group) is the next real step once a real `.hef` model file exists - not
added here, since there is no real model to compile one from yet (see
model_manifest.py's own "no specific model chosen" note).

Same lazy-import + injectable-boundary pattern as every other real
hardware transport this ecosystem has added (serial_transport.py,
mavlink_transport.py, spi_bridge/transport.py, ...): `hailo_platform` is
imported only inside the two functions that genuinely need real HailoRT
(`open_vdevice`, `load_hailo_vla_model`), each raising a clear
`HailoNotAvailableError` instead of a bare `ImportError` when the package
isn't installed - true on this development machine today. Everything
downstream of a loaded model (`hailo_output_to_tokens`) is written
against plain data (an array-like with `.tolist()`, matching both a real
numpy-backed HailoRT result and the plain-list fakes this module's own
tests use), so it is fully unit-testable without hailort or a Hailo-10 NPU.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .action_tokens import TokenizationError
from .model_manifest import EXPECTED_MODEL_MANIFEST

HAILORT_INSTALL_HINT = (
    "hailort is not installed - get it from the Hailo Developer Zone, or "
    "`apt install hailo-all` on Raspberry Pi OS with a Hailo-10 module attached "
    "(it is not on PyPI). This module's tokenization/manifest-matching logic "
    "works and is tested without it."
)


class HailoNotAvailableError(RuntimeError):
    """Raised when hailo_platform (the hailort package) is not importable,
    or when a real .hef does not match this engine's single-tensor-in/
    single-tensor-out contract."""


@dataclass(frozen=True)
class HailoVlaModel:
    """A real HailoRT network group, configured from a real .hef file -
    only ever constructed by load_hailo_vla_model() below, never by hand,
    since `network_group`/`*_vstream_params` are real HailoRT objects."""

    hef_path: Path
    input_name: str
    input_shape: tuple[int, ...]
    output_name: str
    output_shape: tuple[int, ...]
    network_group: object
    input_vstream_params: object
    output_vstream_params: object


def open_vdevice() -> object:
    """Open a real Hailo VDevice targeting whichever Hailo module (Hailo-8
    or Hailo-10) is actually attached - the only place this module imports
    hailo_platform to obtain one. Lazy, so a host without the real hailort
    package installed still gets a clear RuntimeError instead of an
    ImportError surfacing from deep inside this module.
    """
    try:
        from hailo_platform import VDevice  # type: ignore[import-not-found]
    except ImportError as error:
        raise HailoNotAvailableError(HAILORT_INSTALL_HINT) from error
    return VDevice()


def load_hailo_vla_model(vdevice: object, hef_path: Path) -> HailoVlaModel:
    """Configure a real .hef onto an already-open VDevice and extract its
    real input/output vstream shapes.

    Real HailoRT flow: HEF(path) -> ConfigureParams.create_from_hef(hef,
    interface=HailoStreamInterface.PCIe) -> vdevice.configure(hef, params)
    -> InputVStreamParams.make(network_group) /
    OutputVStreamParams.make(network_group). Needs a real hailort install
    and a real compiled .hef model - this function is the one real
    boundary where that dependency is unavoidable, same as
    bootloader_client.py needing a real spidev transport to flash real
    silicon (this session's own STM32H745 SPI-OTA work).
    """
    try:
        from hailo_platform import (  # type: ignore[import-not-found]
            HEF,
            ConfigureParams,
            HailoStreamInterface,
            InputVStreamParams,
            OutputVStreamParams,
        )
    except ImportError as error:
        raise HailoNotAvailableError(HAILORT_INSTALL_HINT) from error

    hef = HEF(str(hef_path))
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = vdevice.configure(hef, configure_params)
    network_group = network_groups[0]

    input_infos = hef.get_input_vstream_infos()
    output_infos = hef.get_output_vstream_infos()
    if len(input_infos) != 1 or len(output_infos) != 1:
        raise HailoNotAvailableError(
            f"{hef_path}: expected exactly 1 input and 1 output vstream for this "
            f"engine's single-tensor-in/single-tensor-out VLA contract, got "
            f"{len(input_infos)} input(s) and {len(output_infos)} output(s)"
        )

    return HailoVlaModel(
        hef_path=hef_path,
        input_name=input_infos[0].name,
        input_shape=tuple(input_infos[0].shape),
        output_name=output_infos[0].name,
        output_shape=tuple(output_infos[0].shape),
        network_group=network_group,
        input_vstream_params=InputVStreamParams.make(network_group),
        output_vstream_params=OutputVStreamParams.make(network_group),
    )


def hailo_output_to_tokens(raw_output: dict[str, Any], model: HailoVlaModel) -> dict[str, Any]:
    """Adapt a real HailoRT inference result (output vstream name -> an
    array-like with a real .tolist()) into the {"tokens": [...],
    "confidence": ...} shape model_manifest.validate_inference_output()
    already validates against this engine's real EXPECTED_MODEL_MANIFEST
    (7 action tokens + a trailing confidence scalar - the shape this
    engine's own manifest declares). Rounds token floats to the nearest
    bin id, since a real model's raw output is continuous logits/argmax
    values, not pre-quantized ints.
    """
    if model.output_name not in raw_output:
        raise TokenizationError(
            f"hailo output missing expected vstream {model.output_name!r} (got {sorted(raw_output)})"
        )
    array = raw_output[model.output_name]
    # A real ndarray from InferVStreams.infer() is batched: shape (1, N)
    # for this engine's one-inference-per-call usage. .tolist() is a real
    # numpy method too, so this line works unchanged against either a
    # real ndarray or the plain-list fakes this module's tests use.
    values = array.tolist() if hasattr(array, "tolist") else list(array)
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        values = values[0]

    expected_dims = EXPECTED_MODEL_MANIFEST.action_dims
    if len(values) != expected_dims + 1:
        raise TokenizationError(
            f"hailo output {model.output_name!r}: expected {expected_dims + 1} values "
            f"({expected_dims} action tokens + 1 confidence), got {len(values)}"
        )
    *token_values, confidence = values
    tokens = [int(round(float(value))) for value in token_values]
    return {"tokens": tokens, "confidence": float(confidence)}
