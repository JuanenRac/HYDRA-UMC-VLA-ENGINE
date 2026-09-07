# HYDRA-UMC-VLA-ENGINE — CLI Reference

`hydra-umc-vla-engine` is a Python console script
(`src/hydra_umc_vla_engine/main.py`, installed as an entry point via
`pyproject.toml`). What's real in v0: action tokenization (the "Action
Tokens" box in the README's diagram — continuous 7-DOF action values in
discretized bins, and back) and trajectory generation (the "Trajectory
Generator" box — integrating a sequence of per-step action deltas into
an absolute pose sequence). Both are fixed math, independent of which
VLA model or Hailo-10 NPU would actually produce the tokens; real model
inference still needs that hardware and lands later. Every example below
was captured from a real run of the installed CLI — not written from
memory.

## Usage

```
$ hydra-umc-vla-engine -h
usage: hydra-umc-vla-engine [-h] {tokens,trajectory} ...

positional arguments:
  {tokens,trajectory}
    tokens             Encode/decode VLA action tokens.
    trajectory         Generate a trajectory from an action sequence.

options:
  -h, --help           show this help message and exit
```

Bare invocation (no subcommand) prints identity/version/role and exits `0`:

```
$ hydra-umc-vla-engine
HYDRA-UMC-VLA-ENGINE v0.0.4
Vision-Language-Action engine (Hailo-10) - translates camera frames and text instructions into robotic action sequences.
```

The real 7-DOF action space (`dx,dy,dz,droll,dpitch,dyaw,gripper`) every
`tokens`/`trajectory` action refers to: per-step deltas in meters/radians
for the first six dims (`dx,dy,dz` bounded to ±0.05m, `droll,dpitch,dyaw`
to ±0.1rad), and an absolute open/close command in `[0.0, 1.0]` for
`gripper` — matching the action space real VLA papers (OpenVLA, RT-2)
train on.

## Commands

### `tokens encode --action VALUES [--vocab-size N]`

```
$ hydra-umc-vla-engine tokens encode -h
usage: hydra-umc-vla-engine tokens encode [-h] --action ACTION
                                          [--vocab-size VOCAB_SIZE]

options:
  -h, --help            show this help message and exit
  --action ACTION       dx,dy,dz,droll,dpitch,dyaw,gripper
  --vocab-size VOCAB_SIZE
```

Continuous 7-DOF action values → discrete bin-id tokens (default
`--vocab-size 256`, one uniformly-binned token per dimension, matching a
real 8-bit VLA action vocabulary):

```
$ hydra-umc-vla-engine tokens encode --action 0.02,0.00,-0.01,0.0,0.0,0.05,1.0
179,128,102,128,128,192,255
$ echo $?
0
```

Out-of-range values are clamped, not rejected — a real model's raw
prediction can slightly overshoot a bound, and clamping still returns a
usable saturated action instead of a hard failure. `0.50` (dx, bounded to
±0.05) and `2.0` (gripper, bounded to `[0,1]`) both saturate to the top
bin (`255`):

```
$ hydra-umc-vla-engine tokens encode --action 0.50,0.00,0.00,0.0,0.0,0.0,2.0
255,128,128,128,128,128,255
$ echo $?
0
```

Wrong dimensionality (real validation, exit code `1`):

```
$ hydra-umc-vla-engine tokens encode --action 0.02,0.00,-0.01
error: --action: expected 7 comma-separated values, got 3
$ echo $?
1
```

### `tokens decode --tokens IDS [--vocab-size N]`

```
$ hydra-umc-vla-engine tokens decode -h
usage: hydra-umc-vla-engine tokens decode [-h] --tokens TOKENS
                                          [--vocab-size VOCAB_SIZE]

options:
  -h, --help            show this help message and exit
  --tokens TOKENS       7 comma-separated bin ids
  --vocab-size VOCAB_SIZE
```

Discrete bin-id tokens → continuous action values (each dimension's bin
*center*, so decoding is lossy — this is a real round trip of the
`tokens encode` example above, not an exact inverse):

```
$ hydra-umc-vla-engine tokens decode --tokens 179,128,102,128,128,192,255
0.020117,0.000195,-0.009961,0.000391,0.000391,0.050391,0.998047
$ echo $?
0
```

An out-of-range token id (exit code `1`):

```
$ hydra-umc-vla-engine tokens decode --tokens 300,0,0,0,0,0,0
error: dx: token 300 out of range [0, 256)
$ echo $?
1
```

### `trajectory integrate --start POSE [--start-gripper G] --actions FILE`

```
$ hydra-umc-vla-engine trajectory integrate -h
usage: hydra-umc-vla-engine trajectory integrate [-h] --start START
                                                 [--start-gripper START_GRIPPER]
                                                 --actions ACTIONS

options:
  -h, --help            show this help message and exit
  --start START         x,y,z,roll,pitch,yaw
  --start-gripper START_GRIPPER
  --actions ACTIONS     Path to a JSON array of
                        [dx,dy,dz,droll,dpitch,dyaw,gripper] arrays
```

Integrates a real JSON sequence of 7-DOF action deltas into an absolute
pose trajectory: the first six dimensions accumulate onto the running
pose (cumulative sum), while `gripper` is taken as-is at each step
(absolute command, not a delta — summing it would make the gripper drift
further open/closed even when the model predicts "no change"). Fixture
used below:

```json
// actions.json
[
  [0.02, 0.00, -0.01, 0.0, 0.0, 0.05, 1.0],
  [0.01, 0.01, 0.00, 0.0, 0.0, 0.00, 1.0],
  [0.00, 0.00, 0.02, 0.0, 0.05, 0.00, 0.0]
]
```

```
$ hydra-umc-vla-engine trajectory integrate --start 0.0,0.0,0.0,0.0,0.0,0.0 --start-gripper 0.0 --actions actions.json
step 0: x=0.000000 y=0.000000 z=0.000000 roll=0.000000 pitch=0.000000 yaw=0.000000 gripper=0.000000
step 1: x=0.020000 y=0.000000 z=-0.010000 roll=0.000000 pitch=0.000000 yaw=0.050000 gripper=1.000000
step 2: x=0.030000 y=0.010000 z=-0.010000 roll=0.000000 pitch=0.000000 yaw=0.050000 gripper=1.000000
step 3: x=0.030000 y=0.010000 z=0.010000 roll=0.000000 pitch=0.050000 yaw=0.050000 gripper=0.000000
$ echo $?
0
```

Step 0 is always the real, unmodified `--start` pose; each following step
is the real cumulative result after that action.

A malformed action (wrong dimensionality inside the JSON array):

```
$ hydra-umc-vla-engine trajectory integrate --start 0.0,0.0,0.0,0.0,0.0,0.0 --actions actions_bad.json
error: action 0: expected 7 values (6 deltas + gripper), got 3
$ echo $?
1
```

A missing `--actions` file (real OS error, not a crash):

```
$ hydra-umc-vla-engine trajectory integrate --start 0.0,0.0,0.0,0.0,0.0,0.0 --actions does_not_exist.json
error: [Errno 2] No such file or directory: 'does_not_exist.json'
$ echo $?
1
```

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | ok |
| `1` | a real, reported failure: malformed `--action`/`--tokens`/`--start` argument, an out-of-range token, a malformed action inside `--actions`' JSON, or a missing/unreadable `--actions` file |

## Out of scope for this CLI

Real VLA model inference (OpenVLA/RT-2-style) on the Hailo-10 NPU —
turning camera frames and text instructions into the action tokens this
CLI encodes/decodes — is described in the project README's own roadmap
but is not implemented yet; it needs real Hailo-10 hardware this
environment does not have. This CLI only ever consumes action
values/tokens supplied directly on the command line or via a JSON file.
