# Changelog: HYDRA-UMC-VLA-ENGINE 👁️

All notable changes to this project will be documented in this file. The
version number follows this ecosystem's "odometer" scheme: PATCH +1 on
every real build, rolling into MINOR past 9 (`0.0.9` -> `0.1.0`); MAJOR is
bumped manually only. See `bump_version.py`.

## [0.0.4]

- Build version synchronized with `hydra-umc.project.json` and the repository-native version source.

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
