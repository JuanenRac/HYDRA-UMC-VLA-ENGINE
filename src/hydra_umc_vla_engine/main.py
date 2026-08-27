# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/main.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Entry point for HYDRA-UMC-VLA-ENGINE.

Minimal real entry point: prints identity/version/role and exits 0. No
business logic yet - this is the andamiaje (scaffolding) stage. Real VLA
inference logic lands in later passes.
"""
from __future__ import annotations

import sys

from . import __version__

PROJECT_NAME = "HYDRA-UMC-VLA-ENGINE"
ROLE = (
    "Vision-Language-Action engine (Hailo-10) - translates camera frames "
    "and text instructions into robotic action sequences."
)


def main() -> int:
    # Deliberately just identity + role for now: proves the package
    # installs/imports cleanly on real target hardware before any
    # model-loading code exists to fail in more confusing ways.
    print(f"{PROJECT_NAME} v{__version__}")
    print(ROLE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
