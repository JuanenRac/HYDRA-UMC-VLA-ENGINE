# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_damaged_guard_file.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A guard file in another encoding."""
from __future__ import annotations

import pytest

from hydra_umc_vla_engine.guard import GuardConfigError, load_limits


@pytest.mark.parametrize("raw", [b"\xff\xfe{\x00", b'{"note": "se\xf1al"}'])
def test_a_guard_file_in_another_encoding_is_a_configuration_error(tmp_path, raw):
    path = tmp_path / "guard.json"
    path.write_bytes(raw)
    with pytest.raises(GuardConfigError):
        load_limits(path)
