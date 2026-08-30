# Changelog: HYDRA-UMC-VLA-ENGINE 👁️

All notable changes to this project will be documented in this file. The
version number follows this ecosystem's "odometer" scheme: PATCH +1 on
every real build, rolling into MINOR past 9 (`0.0.9` -> `0.1.0`); MAJOR is
bumped manually only. See `bump_version.py`.

## [Unreleased] - finite VLA trajectory input gate

- **`main.py` / `trajectory.py`** - command and library trajectories now
  reject `NaN`, infinity, booleans, strings and non-array JSON actions before
  accumulating pose values. Invalid model or file data cannot silently create
  a non-physical trajectory that a later integration might mistake as usable.
- Added CLI and trajectory tests for malformed and non-finite values.

## [0.0.7] - Fixed a real version-mirror drift

- **`src/hydra_umc_vla_engine/__init__.py`**'s `__version__` had fallen
  one real build behind `pyproject.toml`/the manifest - running only
  `bump_manifest_version.py` (which only touches its declared
  `native_version.file`, pyproject.toml) without this repo's separate
  `bump_version.py` (the one that keeps `__init__.py` mirrored) leaves
  the two drifting apart. Fixed via the real, intended sequence
  (`bump_version.py` then `bump_manifest_version.py --sync`).

## [0.0.6] - Fixed after a live ecosystem bug audit

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

### Added
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

### Changed
- `build.sh`/`build.bat` - added the real test-suite step and the
  no-autoclose-on-double-click behavior common to the rest of the
  ecosystem's scripts.
- `run.sh`/`run.bat` - now forward CLI arguments through to the entry
  point instead of ignoring them.

Still out of scope: real VLA model inference (OpenVLA/RT-2 quantized
for Hailo-10) - needs that real hardware and model weights.

## [0.0.3]
### Added
- Copyright/license header on every source file and build/run script.
- `CHANGELOG.md` (this file).
- Extended documentation across `README.md` and its 4 translations:
  advanced technical/architecture section, detailed build/run
  troubleshooting, and a full "Related Projects" section.

### Changed
- Inline comments explaining the *why* behind non-obvious decisions
  (versioning scheme, src-layout, why this child has no hardware/
  firmware/os/models of its own).

## [0.0.0]
### Added
- Initial Python scaffolding: `pyproject.toml` (setuptools, src-layout),
  `src/hydra_umc_vla_engine/__init__.py` + `main.py` (real entry point -
  prints identity/version/role, exits 0).
- `bump_version.py` - odometer-style version bump applied to
  `pyproject.toml` and mirrored into `__init__.py`.
- `build.sh` / `build.bat` - create/activate a venv, install the package
  editable, verify it compiles and imports.
- `run.sh` / `run.bat` - run the entry point.
