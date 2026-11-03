# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/test_kinematics_service.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""The kinematic check against the inverse-kinematics service of PHYSICS-REPLICA (`POST /ik`), with the child process as the alternative."""
from __future__ import annotations

import json
import math
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from hydra_umc_vla_engine.kinematic_check import (
    REACHABLE,
    UNAVAILABLE,
    UNREACHABLE,
    KinematicsConfigError,
    KinematicsPolicy,
    check_reach,
    load_kinematics_policy,
)
from hydra_umc_vla_engine.trajectory import Pose

FAKE = str(Path(__file__).with_name("fake_replica.py"))


class _Fake:
    """A service that answers like the one of PHYSICS-REPLICA, with the same two-joint arm as fake_replica.py."""

    def __init__(self) -> None:
        self.mode = ""
        self.token = ""
        self.calls: list[dict[str, Any]] = []
        self.auth: list[str] = []


def _handler(fake: _Fake) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # silence
            pass

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            fake.calls.append({"path": self.path, **body})
            fake.auth.append(self.headers.get("Authorization", ""))
            if fake.mode == "off":
                return self._send(404, {"error": "off", "code": "ik_off"})
            if fake.token and self.headers.get("Authorization") != f"Bearer {fake.token}":
                return self._send(401, {"error": "token", "code": "unauthorized"})
            if fake.mode == "garbage":
                return self._send(200, {"hello": "world"})
            if fake.mode == "timeout":
                return self._send(200, {"reached": False, "residual": 1.0, "iterations": 3, "timed_out": True})
            x, y, z = body["goal"]
            reach = math.hypot(x, y)
            if reach > 0.5 or z > 0.4:
                return self._send(200, {"reached": False, "residual": max(reach - 0.5, z - 0.4), "iterations": 200, "timed_out": False})
            self._send(200, {"reached": True, "residual": 0.0, "iterations": 5, "timed_out": False, "joints": {"base": math.atan2(y, x), "reach": reach}})

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return Handler


@pytest.fixture
def service() -> Iterator[tuple[_Fake, str]]:
    fake = _Fake()
    server = HTTPServer(("127.0.0.1", 0), _handler(fake))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield fake, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _policy(tmp_path: Path, **change: Any) -> KinematicsPolicy:
    values: dict[str, Any] = {"enabled": True, "command": (sys.executable, FAKE), "urdf": str(tmp_path / "robot.urdf"), "target_joint": "wrist",
                              "initial_joints": {"base": 0.0, "reach": 0.2}, "timeout_seconds": 5.0}
    values.update(change)
    return KinematicsPolicy(**values)


def _poses(*points: tuple[float, float, float]) -> list[Pose]:
    return [Pose(x, y, z, 0.0, 0.0, 0.0, 0.0) for x, y, z in points]


def test_the_service_is_off_unless_an_address_is_given(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_REPLICA_LOG", str(log))
    assert _policy(tmp_path).service_url == ""
    assert check_reach(_poses((0.2, 0.0, 0.1)), _policy(tmp_path)).outcome == REACHABLE
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1  # the child process answered


def test_the_service_answers_each_step_and_the_child_process_is_not_run(service: tuple[_Fake, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake, url = service
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_REPLICA_LOG", str(log))
    result = check_reach(_poses((0.2, 0.0, 0.1), (0.25, 0.05, 0.1), (0.3, 0.1, 0.1)), _policy(tmp_path, service_url=url))
    assert result.outcome == REACHABLE and result.checked == 3
    assert not log.exists()
    assert [c["path"] for c in fake.calls] == ["/ik"] * 3
    assert fake.calls[0]["target"] == "wrist" and fake.calls[0]["joints"] == {"base": 0.0, "reach": 0.2}
    assert fake.calls[1]["joints"]["reach"] == pytest.approx(0.2)  # the joints that reached step 0
    assert fake.calls[2]["joints"] != fake.calls[0]["joints"]
    assert fake.calls[0]["max_iterations"] == 200 and fake.calls[0]["tolerance"] == 0.002


def test_a_goal_the_service_does_not_reach_is_a_verdict_and_the_process_is_not_asked(service: tuple[_Fake, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, url = service
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_REPLICA_LOG", str(log))
    result = check_reach(_poses((0.2, 0.0, 0.1), (0.9, 0.0, 0.1)), _policy(tmp_path, service_url=url))
    assert result.outcome == UNREACHABLE and result.failed_at_step == 1 and "did not reach" in result.reasons[0]
    assert not log.exists()


def test_a_service_that_ran_out_of_time_is_unavailable(service: tuple[_Fake, str], tmp_path: Path) -> None:
    fake, url = service
    fake.mode = "timeout"
    result = check_reach(_poses((0.2, 0.0, 0.1)), _policy(tmp_path, service_url=url))
    assert result.outcome == UNAVAILABLE and "ran out of time" in result.reasons[0]


@pytest.mark.parametrize("mode", ["off", "garbage"])
def test_a_service_that_cannot_be_used_falls_back_to_the_child_process(service: tuple[_Fake, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    fake, url = service
    fake.mode = mode
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_REPLICA_LOG", str(log))
    assert check_reach(_poses((0.2, 0.0, 0.1)), _policy(tmp_path, service_url=url)).outcome == REACHABLE
    assert len(fake.calls) == 1 and len(log.read_text(encoding="utf-8").splitlines()) == 1
    # without the alternative the same service is just unavailable
    strict = check_reach(_poses((0.2, 0.0, 0.1)), _policy(tmp_path, service_url=url, service_fallback=False))
    assert strict.outcome == UNAVAILABLE and "service cannot be used" in strict.reasons[0]


def test_a_service_that_is_not_listening_falls_back_to_the_child_process(tmp_path: Path) -> None:
    assert check_reach(_poses((0.2, 0.0, 0.1)), _policy(tmp_path, service_url="http://127.0.0.1:9")).outcome == REACHABLE
    assert check_reach(_poses((0.2, 0.0, 0.1)), _policy(tmp_path, service_url="http://127.0.0.1:9", service_fallback=False)).outcome == UNAVAILABLE


def test_the_token_comes_from_the_environment_and_is_sent_as_a_bearer(service: tuple[_Fake, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake, url = service
    fake.token = "s3cret-token"
    monkeypatch.setenv("VLA_TEST_IK_TOKEN", "s3cret-token")
    policy = _policy(tmp_path, service_url=url, service_token_env="VLA_TEST_IK_TOKEN", service_fallback=False)
    assert check_reach(_poses((0.2, 0.0, 0.1)), policy).outcome == REACHABLE
    assert fake.auth[-1] == "Bearer s3cret-token"
    monkeypatch.setenv("VLA_TEST_IK_TOKEN", "wrong")
    assert check_reach(_poses((0.2, 0.0, 0.1)), policy).outcome == UNAVAILABLE  # 401 is not a verdict on the pose


def test_the_service_address_must_be_plain_and_a_remote_one_needs_a_token_variable(tmp_path: Path) -> None:
    for bad in ("ftp://127.0.0.1:1", "http://127.0.0.1:1/ik", "http://user:pw@127.0.0.1:1", "http://127.0.0.1:1?x=1", "127.0.0.1:8118", "http://"):
        with pytest.raises(KinematicsConfigError):
            _policy(tmp_path, service_url=bad)
    with pytest.raises(KinematicsConfigError):
        _policy(tmp_path, service_url="http://192.168.0.50:8118")
    with pytest.raises(KinematicsConfigError):
        _policy(tmp_path, service_url="http://localhost:8118", service_token_env="not a name")
    with pytest.raises(KinematicsConfigError):
        _policy(tmp_path, service_fallback="yes")
    assert _policy(tmp_path, service_url="http://192.168.0.50:8118", service_token_env="IK_TOKEN").service_url
    assert _policy(tmp_path, service_url="http://localhost:8118").service_url
    assert _policy(tmp_path, service_url="http://[::1]:8118").service_url


def test_the_configuration_file_reads_the_service_keys_and_describe_never_shows_the_address(tmp_path: Path) -> None:
    path = tmp_path / "vla.json"
    section = {"enabled": True, "urdf": "robot.urdf", "target_joint": "wrist", "service_url": "http://127.0.0.1:8118",
               "service_token_env": "IK_TOKEN", "service_fallback": False}
    path.write_text(json.dumps({"kinematics": section}), encoding="utf-8")
    policy = load_kinematics_policy(path)
    assert (policy.service_url, policy.service_token_env, policy.service_fallback) == ("http://127.0.0.1:8118", "IK_TOKEN", False)
    assert policy.describe()["service"] is True and "127.0.0.1" not in json.dumps(policy.describe())
