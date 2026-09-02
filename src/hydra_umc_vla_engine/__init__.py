# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/__init__.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""HYDRA-UMC-VLA-ENGINE - Vision-Language-Action engine (Hailo-10).

Translates camera frames and natural-language instructions into robotic
action tokens/trajectories. Child of HYDRA-UMC-COGNITIVE-NODE in the
Cognitive AI Node category.
"""

# Single source of truth for the package version - mirrored into
# pyproject.toml's own `version =` field by bump_version.py on every real
# build, so main.py can print a version even if the package was never
# installed (e.g. run straight from src/).
__version__ = "0.1.0"