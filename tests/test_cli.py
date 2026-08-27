import json
import subprocess
import sys

import pytest


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "hydra_umc_vla_engine.main", *args],
        capture_output=True, text=True,
    )


def test_bare_invocation_prints_identity():
    result = run_cli()
    assert result.returncode == 0
    assert "HYDRA-UMC-VLA-ENGINE" in result.stdout


def test_tokens_encode_decode_round_trip():
    encode_result = run_cli("tokens", "encode", "--action", "0,0,0,0,0,0,0.5")
    assert encode_result.returncode == 0
    tokens = encode_result.stdout.strip()
    assert len(tokens.split(",")) == 7

    decode_result = run_cli("tokens", "decode", "--tokens", tokens)
    assert decode_result.returncode == 0
    values = [float(v) for v in decode_result.stdout.strip().split(",")]
    assert values[6] == pytest.approx(0.5, abs=0.01)


def test_tokens_encode_rejects_bad_action():
    result = run_cli("tokens", "encode", "--action", "1,2,3")
    assert result.returncode == 1
    assert "error" in result.stderr


def test_trajectory_integrate(tmp_path):
    actions_path = tmp_path / "actions.json"
    actions_path.write_text(json.dumps([
        [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5],
        [0.0, 0.01, 0.0, 0.0, 0.0, 0.0, 1.0],
    ]), encoding="utf-8")

    result = run_cli("trajectory", "integrate", "--start", "0,0,0,0,0,0", "--actions", str(actions_path))
    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 3
    assert "step 0" in lines[0]
    assert "step 2" in lines[2]
