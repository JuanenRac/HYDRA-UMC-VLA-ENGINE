# Changelog

All notable changes to this project are documented here.

## [Unreleased]

- **The notes of the project manifest no longer carry a hand-written test count:** the counts went out of date at every change; the number of tests is stated by the README, which is checked against the code.
- **README in the universal layout:** the README and its seven translations follow the layout that the four families share (22 sections in a fixed order), with an architecture picture and a repository-structure picture drawn from `docs/architecture.json` and `docs/structure.json`; the CI validator checks both pictures and the file tree.

- **The layout of the README is checked in the CI:** the validator runs `tools/universal_readme_check.py` and lists, as a warning, what differs from the universal layout of the README.

## [0.1.8] - A trajectory guard and optional Bearer token for the HTTP API

- **A trajectory guard** (`guard.py`): the trajectory a model proposes is checked against a work volume, a longest linear and angular step, a limit on how much a step differs from the one before, the range of the gripper and the zones of HYDRA-UMC-SAFETY-ZONES in their own JSON (a move that enters or crosses a `danger` zone rejects it; a step in a `warning` zone is held to a fraction). Outcomes `ok`, `clamped` (cut back and re-integrated from the cut, so it stays continuous) and `rejected` (no poses; HTTP 422). `serve --guard-file` / `HYDRA_UMC_VLA_GUARD_FILE` turns it on for `POST /trajectory/integrate`, whose answer now carries a `guard` section (`not_configured` when there is none); `--require-guard` offers no trajectory without a guard; `trajectory integrate --guard-file` does the same on the command line. The READMEs now mark the camera-frame and SEMANTIC-PLANNER flows as planned: nothing feeds the engine frames today and nothing but the generic proxy of the server reads its output. Tested with synthetic trajectories.
- **Optional Bearer token for the HTTP API.** `serve --token-file FILE` (or `HYDRA_UMC_VLA_ENGINE_TOKEN`, at least 16 characters) makes every request carry `Authorization: Bearer <token>` (constant-time comparison); only `GET /health`, the health path of the manifest, stays open. On loopback no token is needed; any other address is refused at start without one.
- The manifest declares the health path of the service (`service.health_path: /health`), so the ecosystem status and the service registry of the SDK can probe it over HTTP and not only by its port.
- Building no longer changes the version; raising it is the explicit `bump` command (`python tools/hydra_project_tool.py bump`). The build scripts only report the version they built, and CI fails if a build script runs a bump.
- The build and run scripts use the Python of the `.venv` directly instead of an activate script, and create the venv with the `py` launcher when there is one; CI fails if a script activates a venv.
- The banner follows the animated style of the ecosystem banners, with the name, the kind and the technologies of the project.
- Added `tools/hydra_project_tool.py`: the same `validate`, `test`, `version`, `status` and `bump` commands in every repository. The checks run with `HYDRA_UMC_CI=1` and fail if the version changes; only `bump` changes it.

## [0.1.7]

- Maturity is functional: nothing here has been verified on real hardware yet.
- The READMEs say, in the eight languages, what is planned and what has only been tested against fakes, emulators or fixtures, and carry a short safety and security status note.

## [0.1.6] - Model output limited to the action space, zero token without drift, hardened service

- **Model output is checked against the action space:** `integrate_trajectory` only used the length of the action space, so a delta of 10 m or a gripper value of 7 was integrated into a trajectory with a fingerprint. Every delta must now be inside the action-space bounds (0.05 m, 0.1 rad per step, gripper within 0 to 1) and a sequence may have at most 1000 steps; otherwise the API and the CLI answer with an error.
- **"No movement" no longer drifts:** with an even vocabulary the zero token decoded to a small positive value, accumulating about 0.2 m per axis over 1000 still predictions. The symmetric axes now decode it to exactly 0.0 (`snap_zero`, on by default).
- **HTTP hardening:** the handler drops connections that stay silent (15 s), oversized bodies are discarded in 64 KiB pieces instead of one buffer of up to 16 MiB, `?workspace=` must stay inside the workspace the server was started with, and the numeric fields of `/tokens/encode`, `/tokens/decode` and `/trajectory/integrate` reject booleans, strings and non-integer tokens or vocabulary sizes. `GET /health` is new.
- **Hardware probes work under systemd:** the unit used `PrivateDevices=true`, which hides `/dev/hailo0`; it now keeps the real `/dev` with `DevicePolicy=closed` and the accelerator allowed.
- **Container workspace and model check:** the image reads `HYDRA_UMC_WORKSPACE`, and "model weights present" now needs a non-empty `.hef` file (symlinks are not followed) instead of any file such as a `.gitkeep`.
- **Corrupt Hailo output:** NaN, infinite or out-of-range tokens and confidence values raise `TokenizationError` instead of a bare `ValueError` or a giant integer.
- **Tests and docs:** `assert False` in the API tests is replaced by `pytest.raises`, the CLI reference shows the real `-h` output (including `status` and `serve`), the README (all languages) lists the known limits (98 tests).

## [0.1.5] - A NaN model output is refused instead of becoming the maximum movement

- `encode_action` rejects NaN and infinity: clamping a NaN picked the upper bound, so a model that produced NaN was encoded as token 255 on all 7 axes, which decodes to +0.0498 m on dx/dy/dz, +0.0996 rad on the rotations and a gripper at 0.998 - the maximum movement.
- A `vocab_size` outside 2-65536 (0, negative, a boolean, a float) is refused by `encode_action` and `decode_action`; it used to give wrong bins or an uncaught ZeroDivisionError that killed the handler thread.
- The HTTP API rejects the JSON literals `NaN`/`Infinity`/`-Infinity` (which `json.loads` accepts although they are not JSON) and the strings `"nan"`/`"inf"` with `400`.
- 14 new tests (85 in total) cover every axis, the API literals and strings, and a handler that keeps serving after a bad `vocab_size`; the 7 READMEs say so, plus a Portuguese README.

## [0.1.4] - Trajectory proposal marker

- POST /trajectory/integrate now returns a proposal block next to the poses: authorized is always false, the fingerprint (SHA-256 of exactly those poses) lets an approval elsewhere name the trajectory it covers, and it states that an authenticated control must approve before any execution.

## [0.1.3] - finite VLA trajectory input gate, and a real Content-Length cap on the HTTP API

- **`api.py`'s `_read_json_body()` no longer trusts a caller-controlled `Content-Length` with no upper
  bound** - a lying/oversized header could force unbounded memory buffering (the same real DoS/OOM class
  already closed in this family's sibling `api.py` modules, e.g. HYDRA-UMC-ANOMALY-DETECTOR's own). Now
  capped at 1 MiB with a clean `400` instead of blocking on an unbounded read. New regression test proves
  a real just-over-the-limit POST is rejected.
- **New `Dockerfile`**, closing the real gap HYDRA-UMC-COGNITIVE-NODE's
  own `docker-compose.yml` named ("do not have published Dockerfiles
  yet"). Same `--addr`/`--port` CLI the real CM5 systemd unit
  (`systemd/hydra-umc-vla-engine.service`) already runs, bound to
  `0.0.0.0` instead of `127.0.0.1` - a container's own network namespace
  is the real isolation boundary here, not the loopback bind, and
  `127.0.0.1` inside a container would be unreachable from
  HYDRA-UMC-COGNITIVE-NODE's own container over the compose network.
  Deliberately installs the base package only, not the optional
  `[hailo]` extra - `hailort` is not on PyPI and `hailo_runtime.py`'s own
  import is already lazy, so the encode/decode/trajectory/status HTTP
  surface this image serves works without it. Non-root. Not
  build-tested (no Docker runtime on this dev machine) - every
  path/flag matches the one already verified live on the real CM5.
- **`trajectory.py`'s `integrate_trajectory()` now wraps accumulated
  roll/pitch/yaw** to `(-pi, pi]` - it used to accumulate angles by plain
  addition with no wraparound, unlike sibling
  HYDRA-UMC-VISUAL-SERVOING-API's own shortest-turn wrapping (`pose.py`/
  `servo.py`). A long action sequence (continuous wrist rotation) used to
  hand a downstream motor an ever-growing raw radian value instead of the
  canonical angle for the same physical orientation. New regression tests
  cover both the wraparound itself and that the wrapped angle is still
  the same real orientation (`sin`/`cos` match the unwrapped total).
- **`.github/workflows/ci.yml`** - the real `tests/` pytest suite is now
  actually installed and run in CI, matching the fix already landed in
  sibling repos this session. This repo's own baseline workflow only ever
  compile-checked (`py_compile`) `.py` files - it never ran `pytest`, so a
  regression in `tests/` could be merged without CI ever failing. CI-only
  fix, no runtime code changed, no version bump.
- **`main.py` / `trajectory.py`** - command and library trajectories now
  reject `NaN`, infinity, booleans, strings and non-array JSON actions before
  accumulating pose values. Invalid model or file data cannot silently create
  a non-physical trajectory that a later integration might mistake as usable.
- Added CLI and trajectory tests for malformed and non-finite values.

## [0.1.2] - The decode/trajectory example was incomplete in 6 languages

- The `tokens decode` -> `trajectory integrate` walkthrough (all 6
  translated READMEs) jumped straight from the decoded numbers to
  `trajectory integrate --actions actions.json` without ever creating
  that file, and without the English README's own explanation of why
  the decoded values differ from the encode input (the 256-bin
  discretization is lossy by design; decode recovers the bin's
  midpoint, not the exact original value). A reader following any
  non-English README had no way to know where `actions.json` came from.
  Added the missing `echo '[[...]]' > actions.json` line and a
  translated version of the midpoint explanation to all 6 languages,
  matching the English README exactly.

## [0.1.1] - An overflowing accumulation no longer returns an infinite pose

A code-quality review found that `_require_finite`
only ever validated the RAW inputs (`start`'s own fields, each action's own
7 values) - two individually finite values (e.g. `start.x=1e308`,
`dx=1e308`) can still silently overflow to `inf` when accumulated (`float
+ float` never raises on overflow, unlike `float ** 2`), and that
accumulated result was never re-checked before being appended to the
trajectory. `integrate_trajectory` now validates the raw accumulated x/y/z/
roll/pitch/yaw at every single step - before `_wrap_angle`, so an
already-infinite angle can no longer reach `math.sin`/`math.cos` there and
raise an unlabeled "math domain error" instead of the same clear message
every other field gets - and raises immediately on the first step that
overflows, rejecting the whole sequence atomically rather than ever
returning a trajectory truncated (or worse, silently corrupted) partway
through.

3 new tests: the exact overflow-to-infinite linear accumulation, the
angular case (confirms the clear message, not a raw math-domain error),
and a 4-step sequence where 2 genuinely valid steps accumulate fine before
step 3 overflows - confirming the whole sequence is rejected, not just the
one bad step.

Verified with `pytest tests/` (69/69 PASS, this repo's own real test
command).

## [0.1.0] - The 0.0.9 workspace approach was unreadable by its own service account

- **`systemd/hydra-umc-vla-engine.service`** - `--workspace` no longer
  symlinks to the real sibling-checkout root. Live-verified failure on
  the real CM5 this was first installed on: that checkout root lives
  under the operator's own home directory, itself `0700` (Debian's own
  default) - unreadable by this service's own unprivileged account no
  matter how `ProtectHome` is set (see HYDRA-UMC-VISION-NODE's own
  CHANGELOG, 0.0.6, for the full writeup - same real bug, found there
  first). `install_vla_engine.sh` now creates a real `root:root 0755`
  `workspace/HYDRA-UMC-COGNITIVE-NODE/models/` directly under `/opt`
  instead - `ProtectHome` reverts to this family's usual `true`.

## [0.0.9] - Real v0: JSON/HTTP server mode, plus CM5 deployment

- **`api.py`** (new) - `POST /tokens/encode`, `POST /tokens/decode`,
  `POST /trajectory/integrate`, and `GET /status` reach the exact same
  `action_tokens.py`/`trajectory.py`/`hardware.py` functions the CLI's
  own subcommands already run. `POST /trajectory/integrate` takes the
  action sequence directly in the JSON body rather than a server-side
  file path - the CLI's own `--actions PATH` only made sense on the same
  machine as that file. Real gap this closes: this project's own
  tokenization/trajectory math was only ever reachable as a one-shot CLI.
- **`main.py`** - new `serve` subcommand (`--workspace`/`--addr`/`--port`,
  default `127.0.0.1:8098`).
- **`systemd/hydra-umc-vla-engine.service`** (new) - unit for
  `HYDRA-UMC-OS/provisioning/install_vla_engine.sh` (new, that repo).
  `--workspace` symlinks to the real sibling-checkout root already on the
  CM5, the same layout `check_engine_status()` already expects
  (`workspace/HYDRA-UMC-COGNITIVE-NODE/models/`) - `ProtectHome` is
  `read-only`, not the family's usual `true`, since that root lives
  under the operator's home directory (same real lesson from
  HYDRA-UMC-VISION-NODE's own install).
- 11 new tests (`tests/test_api.py`, real end-to-end HTTP) - 64 total.

## [0.0.8] - Real HailoRT integration boundary, prepared ahead of the Hailo-10 module

- **Added `src/hydra_umc_vla_engine/hailo_runtime.py`** (new) - a real
  HailoRT (`hailo_platform`) integration boundary, so this engine is
  ready to actually run inference the moment a real Hailo-10 M.2 module
  is attached, rather than starting that work from zero then. `open_vdevice()`
  and `load_hailo_vla_model()` are written against the real, confirmed
  HailoRT Python API (`VDevice`, `HEF`, `ConfigureParams.create_from_hef(...,
  interface=HailoStreamInterface.PCIe)`, `InputVStreamParams.make()`/
  `OutputVStreamParams.make()`), lazily imported (same pattern as this
  ecosystem's other real hardware transports - `serial_transport.py`,
  `mavlink_transport.py`, `spi_bridge/transport.py`) so this development
  machine, which has no `hailort` installed, degrades to a clear
  `HailoNotAvailableError` instead of a bare `ImportError`.
  `hailo_output_to_tokens()` adapts a real `InferVStreams` inference
  result into this engine's own `{"tokens": [...], "confidence": ...}`
  contract (`model_manifest.validate_inference_output()`) and needs no
  real hailort to exercise - fully unit-tested against plain-list fakes
  standing in for a real numpy-backed result. `hailort` added as a new
  `[project.optional-dependencies]` extra (`pip install .[hailo]`);
  never a required dependency, since importing/testing this package must
  keep working on any machine without a Hailo module attached. 7 new
  tests (53 total). Actually running inference still needs a real
  compiled `.hef` model (no specific VLA model has been chosen yet - see
  `model_manifest.py`'s own note) and a physical Hailo-10 module, both
  future work - but loading one, once it exists, is no longer a blank
  page.

## [0.0.7] - Fixed a real version-mirror drift

- **`src/hydra_umc_vla_engine/__init__.py`**'s `__version__` had fallen
  one real build behind `pyproject.toml`/the manifest - running only
  `bump_manifest_version.py` (which only touches its declared
  `native_version.file`, pyproject.toml) without this repo's separate
  `bump_version.py` (the one that keeps `__init__.py` mirrored) leaves
  the two drifting apart. Fixed via the real, intended sequence
  (`bump_version.py` then `bump_manifest_version.py --sync`).

## [0.0.6] - Fixed a README example that did not match the real code

- **`README.md`** - the `tokens decode` example's shown output didn't
  reproduce with the real code: decoding the exact tokens from the
  `tokens encode` example two lines above (verified by actually running
  it) produces a different result than the README claimed (5 of 7 values
  wrong, one off by 12 bins). Replaced with the real, verified output,
  plus a short note that decode isn't a perfect inverse of encode by
  design (256-bin discretization recovers the bin midpoint, not the
  original value). Also added the missing `actions.json` creation step
  for the `trajectory integrate` example right after it, which
  referenced a file the README never showed how to create - the whole
  three-command example now runs end-to-end exactly as written,
  verified by actually running it.

## [0.0.5] - Model manifest contract, shape/confidence validation, honest safe mode

- **A real, versioned model manifest contract** (`model_manifest.py`, new) - `EXPECTED_MODEL_MANIFEST` mirrors `action_tokens.py`'s own real `VLA_ACTION_SPACE`/`DEFAULT_VOCAB_SIZE` directly (never a separately-maintained literal, so it can't silently drift from the tokenizer it describes), and restricts `hailo_arch` to this ecosystem's own real, closed Hailo chip family (the same set `HYDRA-UMC-DETECTION-HEF` already validates its model registry against). No specific OpenVLA/RT-2 variant has been chosen yet - this is honestly a shape/target contract, not a model loader.
- **Real shape + confidence validation for a future model's inference output** (`validate_inference_output()`) - checks `tokens` is exactly the right length with every value a real in-range integer, and `confidence` is a real number in `[0.0, 1.0]`. The real contract any VLA model integration would have to satisfy before its output is trusted enough to decode and execute.
- **A real, honest `status` subcommand** (`hardware.py`, new) - probes the real Hailo-10 device node (`/dev/hailo0`) and the parent `HYDRA-UMC-COGNITIVE-NODE`'s own real shared `models/` directory (this project has none of its own), and reports one of three real, honest modes: `no_accelerator`, `no_model_weights`, or `hardware_ready_no_inference` - never a fourth "ready" state, since no real inference code exists yet regardless of what hardware is present.
- 21 new tests (`test_model_manifest.py`, `test_hardware.py` new, plus a `test_cli.py` addition) = 40 total.
- Real verification: ran `status` live against this machine's real ecosystem checkout - correctly and honestly reported both the missing Hailo-10 device and the real, empty parent `models/` directory.

## [0.0.4] - Real v0: action tokenization and trajectory generation

- `src/hydra_umc_vla_engine/action_tokens.py` - the "Action Tokens" step
  from README.md's VLA inference flow: `ActionSpec`/`VLA_ACTION_SPACE`
  (the 7-DOF space real VLA papers train on - 6-DOF end-effector pose
  delta + gripper), `encode_action()` (continuous values -> 256-bin
  discrete tokens per dimension, clamping out-of-range input rather than
  rejecting it), `decode_action()` (tokens -> bin-center continuous
  values). This is the OpenVLA/RT-2-style discretization scheme - fixed
  math independent of which model or Hailo-10 NPU would produce/consume
  the tokens.
- `src/hydra_umc_vla_engine/trajectory.py` - the "Trajectory Generator"
  step: `integrate_trajectory()` turns a sequence of decoded per-step
  deltas into an absolute pose sequence (cumulative sum for the 6-DOF
  pose, last-value - not summed - for the gripper's absolute open/close
  state).
- `main.py` - new `tokens encode --action X [--vocab-size N]`, `tokens
  decode --tokens X [--vocab-size N]`, and `trajectory integrate --start
  X --actions PATH` subcommands.
- 19 tests (`test_action_tokens.py`, `test_trajectory.py`, `test_cli.py`).
- `pyproject.toml` - added a `dev` extra (`pytest`).

- `build.sh`/`build.bat` - added the real test-suite step and the
  no-autoclose-on-double-click behavior common to the rest of the
  ecosystem's scripts.
- `run.sh`/`run.bat` - now forward CLI arguments through to the entry
  point instead of ignoring them.

Still out of scope: real VLA model inference (OpenVLA/RT-2 quantized
for Hailo-10) - needs that real hardware and model weights.

## [0.0.3]
- Copyright/license header on every source file and build/run script.
- `CHANGELOG.md` (this file).
- Extended documentation across `README.md` and its 4 translations:
  advanced technical/architecture section, detailed build/run
  troubleshooting, and a full "Related Projects" section.

- Inline comments explaining the *why* behind non-obvious decisions
  (versioning scheme, src-layout, why this child has no hardware/
  firmware/os/models of its own).

## [0.0.0]
- Initial Python scaffolding: `pyproject.toml` (setuptools, src-layout),
  `src/hydra_umc_vla_engine/__init__.py` + `main.py` (real entry point -
  prints identity/version/role, exits 0).
- `bump_version.py` - version bump applied to
  `pyproject.toml` and mirrored into `__init__.py`.
- `build.sh` / `build.bat` - create/activate a venv, install the package
  editable, verify it compiles and imports.
- `run.sh` / `run.bat` - run the entry point.
