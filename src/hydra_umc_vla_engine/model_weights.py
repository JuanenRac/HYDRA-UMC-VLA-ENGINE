# =============================================================================
# HYDRA-UMC-SDK - Shared "are there model weights here" probe
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""One answer to "does this models directory hold a real weight file?".

Two services ask it with a different list of accepted suffixes: the cognitive
node accepts any weight format it can provision, and an accelerator engine only
the compiled model it can load. The walk is the same, so it lives here once:

* only a non-empty regular file with an accepted suffix counts (a `.gitkeep`, a
  README, a tokenizer or an empty file is not a model);
* a symbolic link, to a file or to a folder, is never followed, so the probe
  cannot leave the models tree;
* a huge tree is not walked to the end (`MAX_FILES_INSPECTED`);
* any filesystem error counts as "not present", it never raises.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Final, Iterable

MAX_FILES_INSPECTED: Final[int] = 20_000

# Every weight format a node can be provisioned with.
ANY_WEIGHT_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".bin", ".gguf", ".har", ".hef", ".onnx", ".safetensors", ".tflite"}
)
# The compiled model of a Hailo accelerator.
COMPILED_MODEL_SUFFIXES: Final[frozenset[str]] = frozenset({".hef"})


def contains_model_artifact(
    models_dir: Path | str,
    suffixes: Iterable[str] = ANY_WEIGHT_SUFFIXES,
    max_files: int = MAX_FILES_INSPECTED,
) -> bool:
    """True when `models_dir` holds a non-empty regular file whose suffix is in `suffixes` (case-insensitive)."""
    wanted = frozenset(suffix.lower() for suffix in suffixes)
    root_dir = Path(models_dir)
    try:
        if not root_dir.is_dir() or root_dir.is_symlink():
            return False
        visited = 0
        for root, _dirs, files in os.walk(root_dir, followlinks=False):
            for name in files:
                visited += 1
                if visited > max_files:
                    return False
                path = Path(root, name)
                if path.suffix.lower() not in wanted or path.is_symlink() or not path.is_file():
                    continue
                if path.stat().st_size > 0:
                    return True
    except OSError:
        return False
    return False
