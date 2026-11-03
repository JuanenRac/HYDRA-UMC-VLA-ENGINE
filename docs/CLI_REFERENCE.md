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
usage: hydra-umc-vla-engine [-h] {tokens,trajectory,status,serve} ...

positional arguments:
  {tokens,trajectory,status,serve}
    tokens              Encode/decode VLA action tokens.
    trajectory          Generate a trajectory from an action sequence.
    status              Real, honest report of accelerator/model-weight
                        availability - never a fake ready state.
    serve               Run tokens encode/decode, trajectory integrate, and
                        status as a JSON/HTTP API (POST /tokens/encode, POST
                        /tokens/decode, POST /trajectory/integrate, GET
                        /status) - the exact same functions the CLI
                        subcommands above already run.

options:
  -h, --help            show this help message and exit
```

Bare invocation (no subcommand) prints identity/version/role and exits `0`:

```
$ hydra-umc-vla-engine
HYDRA-UMC-VLA-ENGINE v0.1.6
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

## Signed proposals

`POST /trajectory/integrate` answers with a `proposal` that is never an order (`authorized` is `false`) and carries the `fingerprint` of the poses. `serve --proposal-key-file FILE --robot-id ROBOT [--proposal-valid-seconds N]` (off by default; the key file lives in the installation, never in the repository, and holds at least 16 bytes) also puts `robot_id`, `issued_at_ms`, `expires_at_ms` and a `signature` in it: an HMAC-SHA256 over the fingerprint, the robot and the time window (60 seconds by default, 600 at most). The layer that executes checks it with `verify_proposal()`: a proposal that is altered, expired, issued in the future or meant for another robot is refused, so a trajectory approved once cannot be replayed later or on another robot. The key proves the proposal comes from a holder of the installation's key; it does not tell one holder from another.

`serve --model-version V` and an `instruction_sha256` (64 hex characters, the SHA-256 of the instruction) in the body of `POST /trajectory/integrate` add `model_version` and `instruction_sha256` to the proposal and to what is signed; `verify_proposal(..., expected_model_version=..., expected_instruction_sha256=...)` then also refuses a proposal of another model or for another instruction.

`configs/vla-engine.json` (`--config FILE` or `HYDRA_UMC_VLA_ENGINE_CONFIG`) also holds three switches that are off by default. `consistency.predictions` N above 1 makes `POST /trajectory/integrate` require `alternatives` (N-1 further action sequences as long as `actions`) and offer no trajectory (HTTP 422, `inconsistent_steps`) when any value differs from `actions` by more than `consistency.tolerance` (`linear` metres, `rotation` radians, `gripper`); a request without them is refused (HTTP 400). `shadow.enabled` turns on `POST /shadow/compare`, which takes `proposed` and `operator` action sequences and answers the difference per step and its mean and maximum per group; `shadow.log_file` appends one summary line per comparison. `confidence.minimum` above 0 (0 is off) makes `POST /trajectory/integrate` need one `confidences` value per action and offer no trajectory (HTTP 422, with the indices of the doubtful actions) when any is below the minimum; a request without the values is refused (HTTP 400). None of them moves anything.

**Rotation values.** The three rotation values of an action (`droll`, `dpitch`, `dyaw`) are a rotation vector (axis times angle, radians) that turns the tool exactly: the deltas are composed as quaternions, so the order of turns counts and the result is right for large angles and near pitch 90 degrees. A pose keeps its orientation as a unit quaternion (`Pose.orientation`; the angles are derived from it), and the guard cuts a turn that is too large.

## Kinematic check and confirmation of proposals (`serve`, off by default)

Both are sections of the configuration file (`--config`, or the file named by `HYDRA_UMC_VLA_ENGINE_CONFIG`; `configs/vla-engine.json` has them, off). Without them the engine behaves as before.

`kinematics` makes `POST /trajectory/integrate` try every pose of the trajectory with the `ik` command of HYDRA-UMC-PHYSICS-REPLICA before the proposal is offered:

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Must be `true`. |
| `command` | `["physics-replica"]` | The program (and at most 3 leading arguments), as a list; no shell is used. |
| `urdf`, `target_joint` | required | The URDF (relative to the configuration file or absolute) and the joint whose frame is moved to each pose. |
| `initial_joints` | `{}` | Joint positions to start from, `{"name": radians_or_meters}`; each next pose starts from the joints that reached the one before. |
| `origin` | `[0, 0, 0]` | Added to the position of every pose to put it in the frame of the robot. |
| `tolerance_m`, `max_iterations` | `0.002`, `200` | Passed to `ik`. |
| `max_joint_step` | `0.5` | The most a joint may turn between two poses; more is refused. |
| `timeout_seconds`, `max_waypoints` | `10`, `64` | Time for each call; a longer trajectory is `unavailable`. |
| `fail_closed` | `true` | No proposal when the check cannot run. |
| `service_url` | `""` (off) | The address of a running `serve` of HYDRA-UMC-PHYSICS-REPLICA (`http://127.0.0.1:8118`, no path); each pose is then asked to its `POST /ik` instead of a child process. That route is off in PHYSICS-REPLICA until its own configuration says `"ik": {"enabled": true}`. |
| `service_token_env` | `""` | The name of the environment variable that holds the bearer token of that service. The token is never read from the file. An address that is not on this machine is refused unless this is set. |
| `service_fallback` | `true` | When the service cannot be used (it does not answer, is off, refuses the token or answers something unreadable) the child process answers instead; `false` makes that `unavailable`. A goal the service says it did not reach is a verdict and is not asked again; a request that ran out of time is `unavailable`. |

The answer carries `kinematics` (`outcome` `reachable`, `unreachable` or `unavailable`, the reasons, how many poses were checked, the step that failed and the widest turn of a joint). `422` for `unreachable`, `503` for `unavailable` with `fail_closed`.
Only the position of the tool is checked, not its orientation nor the collisions of the arm.

`confirmation` (needs `--proposal-key-file` and `--robot-id`) makes every proposal wait for a person: `ttl_seconds` (60), `token_seconds` (30), `max_pending` (16, the oldest is dropped), `approval_validity_ms` (10000).
`proposal.confirmation` carries `pending_id`; `GET /confirmations/pending` lists what waits; `POST /confirmations/<id>/prepare` `{"operator"}` answers `summary`, `fingerprint` and `confirmationToken`;
`POST /confirmations/<id>/confirm` `{"operator", "confirmationToken"}` answers the signed approval; `POST /confirmations/<id>/reject` `{"operator"}` throws the proposal away. Errors: `404` no such proposal,
`409` not prepared, `403` a token that is not genuine, not the one issued or from another operator, `410` an expired token. `serve --max-threads N` limits the requests handled at the same time (32 by default).

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
