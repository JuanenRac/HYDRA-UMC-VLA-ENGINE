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
import sys
from pathlib import Path

from . import __version__
from .action_tokens import DEFAULT_VOCAB_SIZE, TokenizationError, decode_action, encode_action
from .trajectory import Pose, TrajectoryError, integrate_trajectory

PROJECT_NAME = "HYDRA-UMC-VLA-ENGINE"
ROLE = (
    "Vision-Language-Action engine (Hailo-10) - translates camera frames "
    "and text instructions into robotic action sequences."
)


def _parse_floats(text: str, expected: int, label: str) -> tuple[float, ...]:
    parts = text.split(",")
    if len(parts) != expected:
        raise TokenizationError(f"{label}: expected {expected} comma-separated values, got {len(parts)}")
    try:
        return tuple(float(p) for p in parts)
    except ValueError as exc:
        raise TokenizationError(f"{label}: non-numeric value: {exc}") from exc


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


def _cmd_trajectory_integrate(args: argparse.Namespace) -> int:
    try:
        start_values = _parse_floats(args.start, 6, "--start")
        actions_raw = json.loads(Path(args.actions).read_text(encoding="utf-8"))
        actions = [tuple(a) for a in actions_raw]
        start = Pose(*start_values, gripper=args.start_gripper)
        poses = integrate_trajectory(start, actions)
    except (TokenizationError, TrajectoryError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for i, pose in enumerate(poses):
        print(f"step {i}: x={pose.x:.6f} y={pose.y:.6f} z={pose.z:.6f} "
              f"roll={pose.roll:.6f} pitch={pose.pitch:.6f} yaw={pose.yaw:.6f} gripper={pose.gripper:.6f}")
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
    integrate.set_defaults(func=_cmd_trajectory_integrate)

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
