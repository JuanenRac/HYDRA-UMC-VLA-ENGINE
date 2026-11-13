# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_cli_inprocess.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The command line, run in this process (the earlier tests start a process for each command, which a coverage measure cannot follow): the tokens, the
trajectory with and without a guard, the status of the engine and every option set of `serve` that stops the start with exit 2 and says why."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from hydra_umc_vla_engine import main as m

GUARD = {
    "workspace": {"min": {"x": -1, "y": -1, "z": 0}, "max": {"x": 1, "y": 1, "z": 1}},
    "max_linear_step_m": 0.03,
    "max_angular_step_rad": 0.08,
    "zones": [{"id": "person", "level": "danger", "min": {"x": 0.3, "y": 0.3, "z": 0}, "max": {"x": 0.6, "y": 0.6, "z": 1}}],
}


def run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["hydra-umc-vla-engine", *argv])
    monkeypatch.delenv("HYDRA_UMC_VLA_ENGINE_CONFIG", raising=False)
    monkeypatch.delenv("HYDRA_UMC_VLA_GUARD_FILE", raising=False)
    return m.main()


@pytest.fixture(autouse=True)
def _no_listening(monkeypatch: pytest.MonkeyPatch) -> None:
    """A serve that gets past every check must not listen: the server is the real one but its loop stops at once."""
    real = m.VlaEngineServer

    class Stopping(real):  # type: ignore[misc, valid-type]
        def serve_forever(self, poll_interval: float = 0.5) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(m, "VlaEngineServer", Stopping)


def test_the_bare_command_says_who_it_is(monkeypatch, capsys):
    assert run(monkeypatch) == 0
    assert "HYDRA-UMC-VLA-ENGINE" in capsys.readouterr().out


def test_tokens_go_round_and_a_bad_action_or_token_is_an_error_not_a_trace(monkeypatch, capsys):
    assert run(monkeypatch, "tokens", "encode", "--action", "0,0,0,0,0,0,0.5") == 0
    tokens = capsys.readouterr().out.strip()
    assert run(monkeypatch, "tokens", "decode", "--tokens", tokens) == 0
    assert len(capsys.readouterr().out.strip().split(",")) == 7
    for args in (["encode", "--action", "1,2,3"], ["encode", "--action", "a,b,c,d,e,f,g"], ["encode", "--action", "nan,0,0,0,0,0,0"],
                 ["decode", "--tokens", "1,2"], ["decode", "--tokens", "x,1,1,1,1,1,1"], ["decode", "--tokens", "9999,1,1,1,1,1,1"]):
        assert run(monkeypatch, "tokens", *args) == 1, args
        assert capsys.readouterr().err.startswith("error:")


def test_the_status_says_what_is_missing(monkeypatch, capsys, tmp_path: Path):
    assert run(monkeypatch, "status", "--workspace", str(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "accelerator (Hailo-10):" in out and "mode:" in out


def _actions(tmp_path: Path, rows: object) -> str:
    path = tmp_path / "actions.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return str(path)


def test_a_trajectory_is_integrated_and_printed_step_by_step(monkeypatch, capsys, tmp_path: Path):
    actions = _actions(tmp_path, [[0.01, 0, 0, 0, 0, 0, 0.5]] * 3)
    assert run(monkeypatch, "trajectory", "integrate", "--start", "0,0,0.5,0,0,0", "--actions", actions) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 4 and lines[0].startswith("step 0:") and "x=0.030000" in lines[-1]


def test_a_trajectory_with_a_guard_is_cut_back_or_refused_and_the_reasons_are_printed(monkeypatch, capsys, tmp_path: Path):
    guard = tmp_path / "guard.json"
    guard.write_text(json.dumps(GUARD), encoding="utf-8")
    clear = _actions(tmp_path, [[0.01, 0, 0, 0, 0, 0, 0.5]] * 3)
    assert run(monkeypatch, "trajectory", "integrate", "--start", "0,0,0.5,0,0,0", "--actions", clear, "--guard-file", str(guard)) == 0
    assert "guard: ok" in capsys.readouterr().err
    long_step = _actions(tmp_path, [[0.05, 0.05, 0, 0, 0, 0, 0.5]] * 2)
    assert run(monkeypatch, "trajectory", "integrate", "--start", "0,0,0.5,0,0,0", "--actions", long_step, "--guard-file", str(guard)) == 0
    assert "guard: clamped" in capsys.readouterr().err
    into_person = _actions(tmp_path, [[0.05, 0.05, 0, 0, 0, 0, 0.5]] * 10)
    assert run(monkeypatch, "trajectory", "integrate", "--start", "0.1,0.1,0.5,0,0,0", "--actions", into_person, "--guard-file", str(guard)) == 1
    assert "guard: rejected" in capsys.readouterr().err


def test_a_trajectory_that_cannot_be_read_is_an_error(monkeypatch, capsys, tmp_path: Path):
    base = ["trajectory", "integrate", "--start", "0,0,0.5,0,0,0"]
    assert run(monkeypatch, *base, "--actions", str(tmp_path / "missing.json")) == 1
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert run(monkeypatch, *base, "--actions", str(broken)) == 1
    assert run(monkeypatch, *base, "--actions", _actions(tmp_path, {"not": "a list"})) == 1
    assert run(monkeypatch, *base, "--actions", _actions(tmp_path, [[0, 0, 0]])) == 1
    assert run(monkeypatch, "trajectory", "integrate", "--start", "0,0,0.5", "--actions", _actions(tmp_path, [])) == 1
    assert run(monkeypatch, *base, "--actions", _actions(tmp_path, []), "--guard-file", str(tmp_path / "noguard.json")) == 1
    assert capsys.readouterr().err.count("error:") == 6


def test_a_configuration_file_that_cannot_be_read_stops_the_command(monkeypatch, capsys, tmp_path: Path):
    config = tmp_path / "config.json"
    config.write_text("{", encoding="utf-8")
    assert run(monkeypatch, "trajectory", "integrate", "--start", "0,0,0,0,0,0", "--actions", _actions(tmp_path, []), "--config", str(config)) == 2
    assert run(monkeypatch, "serve", "--config", str(config)) == 2
    assert capsys.readouterr().err.count("error:") == 2


def _serve(monkeypatch, *args: str) -> int:
    return run(monkeypatch, "serve", "--port", "0", *args)


def test_a_serve_that_binds_the_network_without_a_token_is_refused(monkeypatch, capsys):
    assert _serve(monkeypatch, "--addr", "0.0.0.0") == 2
    assert "error:" in capsys.readouterr().err


def test_a_token_file_or_key_file_that_is_not_there_is_refused(monkeypatch, capsys, tmp_path: Path):
    assert _serve(monkeypatch, "--token-file", str(tmp_path / "notoken")) == 2
    assert _serve(monkeypatch, "--identity-key-file", str(tmp_path / "nokey")) == 2
    assert capsys.readouterr().err.count("error:") == 2


def test_the_guard_file_must_be_there_when_it_is_required(monkeypatch, capsys, tmp_path: Path):
    assert _serve(monkeypatch, "--require-guard") == 2
    assert "--require-guard needs a guard file" in capsys.readouterr().err
    assert _serve(monkeypatch, "--guard-file", str(tmp_path / "noguard.json")) == 2
    broken = tmp_path / "guard.json"
    broken.write_text(json.dumps({"workspace": 3}), encoding="utf-8")
    assert _serve(monkeypatch, "--guard-file", str(broken)) == 2


def test_a_signed_proposal_needs_a_robot_and_a_key_that_can_be_read(monkeypatch, capsys, tmp_path: Path):
    key = tmp_path / "proposal.key"
    key.write_text("p" * 40, encoding="utf-8")
    assert _serve(monkeypatch, "--proposal-key-file", str(key)) == 2
    assert "--robot-id" in capsys.readouterr().err
    assert _serve(monkeypatch, "--proposal-key-file", str(tmp_path / "nokey"), "--robot-id", "arm-1") == 2
    short = tmp_path / "short.key"
    short.write_text("abc", encoding="utf-8")
    assert _serve(monkeypatch, "--proposal-key-file", str(short), "--robot-id", "arm-1") == 2
    assert _serve(monkeypatch, "--proposal-key-file", str(key), "--robot-id", "arm-1", "--proposal-signing", "ed25519") == 2


def test_the_confirmation_of_proposals_needs_the_key_and_the_hmac_signing(monkeypatch, capsys, tmp_path: Path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"confirmation": {"enabled": True}}), encoding="utf-8")
    key = tmp_path / "proposal.key"
    key.write_text("p" * 40, encoding="utf-8")
    assert _serve(monkeypatch, "--config", str(config)) == 2
    assert "needs --proposal-key-file and --robot-id" in capsys.readouterr().err
    assert _serve(monkeypatch, "--config", str(config), "--proposal-key-file", str(key), "--robot-id", "arm-1", "--proposal-signing", "ed25519") == 2
    assert _serve(monkeypatch, "--config", str(config), "--proposal-key-file", str(key), "--robot-id", "arm-1") == 0
    assert "CONFIRMATION ON" in capsys.readouterr().out


@pytest.mark.parametrize(("section", "content"), [
    ("confidence", "text"), ("consistency", "text"), ("shadow", "text"), ("kinematics", {"surprise": 1}), ("confirmation", {"surprise": 1}), ("confirmation", {"ttl_seconds": -5}),
])
def test_a_section_of_the_configuration_that_cannot_be_used_stops_the_start(monkeypatch, capsys, tmp_path: Path, section: str, content: object):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({section: content}), encoding="utf-8")
    assert _serve(monkeypatch, "--config", str(config)) == 2
    assert capsys.readouterr().err.startswith("error:")


def test_a_start_with_a_guard_says_so_and_a_start_without_one_says_that_too(monkeypatch, capsys, tmp_path: Path):
    assert _serve(monkeypatch) == 0
    out = capsys.readouterr().out
    assert "no trajectory guard" in out and "shutting down" in out
    guard = tmp_path / "guard.json"
    guard.write_text(json.dumps(GUARD), encoding="utf-8")
    assert _serve(monkeypatch, "--guard-file", str(guard), "--require-guard") == 0
    assert "trajectory guard from" in capsys.readouterr().out


def test_a_number_of_threads_outside_the_range_stops_the_start(monkeypatch, capsys):
    assert _serve(monkeypatch, "--max-threads", "0") == 2
    assert capsys.readouterr().err.startswith("error:")
