# =============================================================================
# HYDRA-UMC-VLA-ENGINE - tests/fake_replica.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""A stand-in for the `ik` command of PHYSICS-REPLICA used by the tests of the kinematic check.

It answers like the real program: `name=value` lines on the standard output and exit code 0 when the goal can be reached, a message on the error output and exit
code 1 when it cannot, 2 for a wrong call. The "robot" is a two-joint arm: `base` turns towards the goal (atan2) and `reach` is the distance of the goal in the
horizontal plane; a goal further than 0.5 m, or higher than 0.4 m, is out of reach. Environment: FAKE_REPLICA_LOG (a file that gets the arguments of every call),
FAKE_REPLICA_MODE (`crash` leaves with code 3, `garbage` prints nothing readable, `slow` sleeps for 3 seconds).
"""
import json
import math
import os
import sys
import time

args = sys.argv[1:]
log = os.environ.get("FAKE_REPLICA_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(args) + "\n")
mode = os.environ.get("FAKE_REPLICA_MODE", "")
if mode == "crash":
    sys.stderr.write("ik: the model could not be loaded\n")
    sys.exit(3)
if mode == "garbage":
    print("this is not a joint position")
    sys.exit(0)
if mode == "slow":
    time.sleep(3)
if not args or args[0] != "ik" or "--goal" not in args or "--urdf" not in args:
    sys.stderr.write("ik: missing required arguments\n")
    sys.exit(2)
x, y, z = (float(v) for v in args[args.index("--goal") + 1].split(","))
reach = math.hypot(x, y)
if reach > 0.5 or z > 0.4:
    sys.stderr.write(f"ik: could not reach the goal (residual {max(reach - 0.5, z - 0.4):.6f} m after 200 iterations)\n")
    sys.exit(1)
print(f"base={math.atan2(y, x):.9f}")
print(f"reach={reach:.9f}")
sys.stderr.write("ik: reached within 0.000100 m in 5 iteration(s)\n")
