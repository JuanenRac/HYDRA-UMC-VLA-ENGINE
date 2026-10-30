# =============================================================================
# HYDRA-UMC-VLA-ENGINE - src/hydra_umc_vla_engine/main.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Entry point for HYDRA-UMC-VLA-ENGINE.

Real v0: the action-tokenization (action_tokens.py) and trajectory
generation (trajectory.py) steps of the VLA inference flow - the "Action
Tokens" and "Trajectory Generator" boxes in README.md's diagram - which
are fixed math independent of which VLA model or Hailo-10 NPU would
produce the tokens. Actual model inference still needs that real
hardware and lands later.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

from . import __version__
from .action_tokens import DEFAULT_VOCAB_SIZE, TokenizationError, decode_action, encode_action
from .access import bind_problem, load_token
from .proposal_signing import ProposalKeyError, load_key, sign_proposal
from .api import VlaEngineServer
from .guard import REJECTED, GuardConfigError, guard_trajectory, load_limits
from .hardware import EngineMode, check_engine_status
from .confidence import ConfidenceConfigError, load_confidence_policy
from .rotation_policy import RotationConfigError, load_rotation_policy, set_active_policy
from .trajectory import Pose, TrajectoryError, integrate_trajectory

PROJECT_NAME = "HYDRA-UMC-VLA-ENGINE"
ROLE = (
    "Vision-Language-Action engine (Hailo-10) - translates camera frames "
    "and text instructions into robotic action sequences."
)

# This file lives at src/hydra_umc_vla_engine/main.py - two parents up is
# this repo's own root, and one more level up is the workspace that
# holds it as a sibling of HYDRA-UMC-COGNITIVE-NODE (see hardware.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
# An installed (non-editable) package lives in site-packages, where "two parents
# up" means nothing, so HYDRA_UMC_WORKSPACE (set by the container image) wins.
_DEFAULT_WORKSPACE = Path(os.environ.get("HYDRA_UMC_WORKSPACE") or _REPO_ROOT.parent)

_MODE_MESSAGES = {
    EngineMode.NO_ACCELERATOR: "no Hailo-10 NPU device node on this machine - real inference cannot run here.",
    EngineMode.NO_MODEL_WEIGHTS: "Hailo-10 present, but the parent's shared model weights are missing/empty - real inference cannot run here.",
    EngineMode.HARDWARE_READY_NO_INFERENCE: "hardware and model weights are both present, but this v0 has no real inference code yet.",
}


def _cmd_status(args: argparse.Namespace) -> int:
    status = check_engine_status(args.workspace)
    print(f"accelerator (Hailo-10):    {'present' if status.accelerator_present else 'MISSING'}")
    print(f"model weights (parent):    {'present' if status.model_weights_present else 'MISSING'}")
    print(f"mode: {status.mode.value} - {_MODE_MESSAGES[status.mode]}")
    return 0


def _parse_floats(text: str, expected: int, label: str) -> tuple[float, ...]:
    parts = text.split(",")
    if len(parts) != expected:
        raise TokenizationError(f"{label}: expected {expected} comma-separated values, got {len(parts)}")
    try:
        values = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise TokenizationError(f"{label}: non-numeric value: {exc}") from exc
    if not all(math.isfinite(value) for value in values):
        raise TokenizationError(f"{label}: values must be finite")
    return values


def _parse_ints(text: str, expected: int, label: str) -> tuple[int, ...]:
    parts = text.split(",")
    if len(parts) != expected:
        raise TokenizationError(f"{label}: expected {expected} comma-separated values, got {len(parts)}")
    try:
        return tuple(int(p) for p in parts)
    except ValueError as exc:
        raise TokenizationError(f"{label}: non-integer value: {exc}") from exc


def _cmd_tokens_encode(args: argparse.Namespace) -> int:
    try:
        values = _parse_floats(args.action, 7, "--action")
        tokens = encode_action(values, vocab_size=args.vocab_size)
    except TokenizationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(",".join(str(t) for t in tokens))
    return 0


def _cmd_tokens_decode(args: argparse.Namespace) -> int:
    try:
        tokens = _parse_ints(args.tokens, 7, "--tokens")
        values = decode_action(tokens, vocab_size=args.vocab_size)
    except TokenizationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(",".join(f"{v:.6f}" for v in values))
    return 0


def _apply_config(args: argparse.Namespace) -> bool:
    """Read the rotation settings of the configuration file; False (after the message) when they cannot be used."""
    try:
        set_active_policy(load_rotation_policy(args.config))
    except RotationConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return False
    return True


def _cmd_trajectory_integrate(args: argparse.Namespace) -> int:
    if not _apply_config(args):
        return 2
    try:
        start_values = _parse_floats(args.start, 6, "--start")
        actions_raw = json.loads(Path(args.actions).read_text(encoding="utf-8"))
        if not isinstance(actions_raw, list):
            raise TrajectoryError("actions: expected a JSON array")
        actions = [tuple(a) for a in actions_raw]
        start = Pose(*start_values, gripper=args.start_gripper)
        poses = integrate_trajectory(start, actions)
        if args.guard_file:
            result = guard_trajectory(poses, load_limits(args.guard_file))
            for reason in result.reasons:
                print(f"guard: {reason}", file=sys.stderr)
            print(f"guard: {result.outcome}", file=sys.stderr)
            if result.outcome == REJECTED:
                return 1
            poses = result.poses
    except (TokenizationError, TrajectoryError, GuardConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for i, pose in enumerate(poses):
        print(f"step {i}: x={pose.x:.6f} y={pose.y:.6f} z={pose.z:.6f} "
              f"roll={pose.roll:.6f} pitch={pose.pitch:.6f} yaw={pose.yaw:.6f} gripper={pose.gripper:.6f}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    if not _apply_config(args):
        return 2
    try:
        token = load_token(args.token_file)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    problem = bind_problem(args.addr, token)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    guard_path = args.guard_file or os.environ.get("HYDRA_UMC_VLA_GUARD_FILE")
    guard = None
    if guard_path:
        try:
            guard = load_limits(guard_path)
        except GuardConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.require_guard and guard is None:
        print("error: --require-guard needs a guard file (--guard-file or HYDRA_UMC_VLA_GUARD_FILE)", file=sys.stderr)
        return 2
    signer = None
    if args.proposal_key_file:
        if not args.robot_id.strip():
            print("error: --proposal-key-file needs --robot-id: a signed proposal is for one robot", file=sys.stderr)
            return 2
        try:
            signer = (load_key(args.proposal_key_file), args.robot_id, int(args.proposal_valid_seconds * 1000))
            sign_proposal(signer[0], "0" * 64, signer[1], validity_ms=signer[2])
        except (ProposalKeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    try:
        confidence = load_confidence_policy(args.config)
    except ConfidenceConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    server = VlaEngineServer((args.addr, args.port), args.workspace, token, guard, args.require_guard, signer, model_version=args.model_version.strip(), confidence=confidence)
    if guard is None:
        print("[vla-engine] no trajectory guard: trajectories are offered with guard=not_configured (give --guard-file to check them against the limits of the cell)")
    else:
        print(f"[vla-engine] trajectory guard from {guard_path}: work volume, step limits and {len(guard.zones)} zone(s)")
    print(f"[vla-engine] HTTP API listening on {args.addr}:{args.port} (workspace={args.workspace}; {'Bearer token required' if token else 'no token, loopback only'})")
    print("[vla-engine] POST /tokens/encode, POST /tokens/decode, POST /trajectory/integrate, GET /status, GET /stats")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[vla-engine] shutting down")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hydra-umc-vla-engine")
    subparsers = parser.add_subparsers(dest="command")

    tokens = subparsers.add_parser("tokens", help="Encode/decode VLA action tokens.")
    tokens_sub = tokens.add_subparsers(dest="tokens_command", required=True)

    encode = tokens_sub.add_parser("encode", help="Continuous action -> discrete tokens.")
    encode.add_argument("--action", required=True, help="dx,dy,dz,droll,dpitch,dyaw,gripper")
    encode.add_argument("--vocab-size", type=int, default=DEFAULT_VOCAB_SIZE, dest="vocab_size")
    encode.set_defaults(func=_cmd_tokens_encode)

    decode = tokens_sub.add_parser("decode", help="Discrete tokens -> continuous action.")
    decode.add_argument("--tokens", required=True, help="7 comma-separated bin ids")
    decode.add_argument("--vocab-size", type=int, default=DEFAULT_VOCAB_SIZE, dest="vocab_size")
    decode.set_defaults(func=_cmd_tokens_decode)

    trajectory = subparsers.add_parser("trajectory", help="Generate a trajectory from an action sequence.")
    trajectory_sub = trajectory.add_subparsers(dest="trajectory_command", required=True)

    integrate = trajectory_sub.add_parser("integrate", help="Integrate a JSON action sequence into a pose trajectory.")
    integrate.add_argument("--start", required=True, help="x,y,z,roll,pitch,yaw")
    integrate.add_argument("--start-gripper", type=float, default=0.0, dest="start_gripper")
    integrate.add_argument("--actions", required=True, help="Path to a JSON array of [dx,dy,dz,droll,dpitch,dyaw,gripper] arrays")
    integrate.add_argument("--guard-file", default=None, dest="guard_file", help="Check the trajectory against the limits and zones of the cell in this JSON file (see guard.py); a rejected trajectory exits 1")
    integrate.add_argument("--config", default=None, help="Configuration file with how the rotation deltas are integrated (default: the file named by HYDRA_UMC_VLA_ENGINE_CONFIG, else quaternion composition in the base frame)")
    integrate.set_defaults(func=_cmd_trajectory_integrate)

    status = subparsers.add_parser(
        "status", help="Real, honest report of accelerator/model-weight availability - never a fake ready state."
    )
    status.add_argument(
        "--workspace",
        type=Path,
        default=_DEFAULT_WORKSPACE,
        help="Directory containing the sibling repo checkouts (default: this repo's own parent directory).",
    )
    status.set_defaults(func=_cmd_status)

    serve = subparsers.add_parser(
        "serve",
        help="Run tokens encode/decode, trajectory integrate, and status as a JSON/HTTP "
             "API (POST /tokens/encode, POST /tokens/decode, POST /trajectory/integrate, "
             "GET /status) - the exact same functions the CLI subcommands above already run.",
    )
    serve.add_argument("--addr", default="127.0.0.1", help="address to bind the HTTP API to")
    serve.add_argument("--port", type=int, default=8098, help="port for the HTTP API")
    serve.add_argument("--proposal-key-file", default=None, dest="proposal_key_file",
                       help="file with the key that signs every trajectory proposal for --robot-id and a short time window (off by default: the proposal only carries its fingerprint)")
    serve.add_argument("--robot-id", default="", dest="robot_id", help="the robot the signed proposals are for (needed with --proposal-key-file)")
    serve.add_argument("--model-version", default="", dest="model_version",
                       help="the version of the model that produces the actions; with --proposal-key-file it is signed into every proposal")
    serve.add_argument("--proposal-valid-seconds", type=float, default=60.0, dest="proposal_valid_seconds",
                       help="how long a signed proposal stays valid, at most 600 (default 60)")
    serve.add_argument("--token-file", default=None, help="file with the bearer token every request must present (or the HYDRA_UMC_VLA_ENGINE_TOKEN environment variable). Needed to bind an address that is not loopback.")
    serve.add_argument(
        "--workspace",
        type=Path,
        default=_DEFAULT_WORKSPACE,
        help="Default workspace for GET /status when it is not overridden per-request.",
    )
    serve.add_argument("--guard-file", default=None, dest="guard_file", help="JSON file with the work volume, step limits and zones every trajectory is checked against (or HYDRA_UMC_VLA_GUARD_FILE)")
    serve.add_argument("--require-guard", action="store_true", dest="require_guard", help="Offer no trajectory at all unless a guard file is loaded")
    serve.add_argument("--config", default=None, help="Configuration file with how the rotation deltas are integrated (default: the file named by HYDRA_UMC_VLA_ENGINE_CONFIG, else quaternion composition in the base frame)")
    serve.set_defaults(func=_cmd_serve)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        # Deliberately just identity + role for the bare invocation: proves
        # the package installs/imports cleanly on real target hardware
        # before/alongside any model-loading code.
        print(f"{PROJECT_NAME} v{__version__}")
        print(ROLE)
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
