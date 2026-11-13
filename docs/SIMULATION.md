# Simulation bench

The engine can run without a model, an accelerator or a robot. The simulated model is a function that writes actions from a fixed seed in the ways a real one fails (smooth, noisy, runaway in one direction, saturated, walking toward a person's zone, out of range, not a number, the wrong length). The simulated cell is a work volume with a danger zone and a warning zone. The simulated operator is a script that prepares, confirms, confirms twice, confirms late, confirms as someone else or takes the token of another proposal. The real tokens, trajectory, guard and confirmation run against them, and the bench states what must hold for every proposal whatever the model does.

## Run it

```
python -m pytest -q tests/test_simulation_bench.py
```

## What the scenarios check

| Scenario | What it shows |
|----------|---------------|
| six kinds of model, fifteen proposals each | the tool never leaves the volume, never enters the danger zone and never takes a longer step than the limit; an accepted trajectory is the proposal as it came; a refused one has no poses and a reason |
| a runaway and a smooth model | the runaway is cut back or refused and the smooth one in the clear is left alone |
| a model that walks into the person | refused at the step where it gets there or before |
| a value that is not a number or out of range | never becomes a pose |
| actions of the wrong length | refused before anything moves |
| a start outside the volume, inside the danger zone or with the gripper out of range | refused at step zero |
| tokens at four vocabulary sizes | they decode to within half a bin and a token outside the vocabulary is refused |
| limits that do not describe a cell | refused |
| the operator that saw the summary approves | once; the approval is for that trajectory and that robot and no other |
| an approval that lasts or is from the future | refused |
| an approval edited after it was signed | refused, field by field |
| the wrong token, the wrong operator, a token of another proposal, a late token | each is refused with its own status |
| a second prepare | replaces the token of the first |
| a proposal nobody answers | expires, and the queue is bounded |
| a rejection | final and counted |

The workflow named "Simulation bench" runs the bench on every change, so the simulated path has its own visible job.

## What it cannot show

A real model, its real output on real images, the accelerator, the robot and the person who approves in front of it need the hardware. The status of the repository therefore stays at "simulated" for the hardware row until a person has run the service on the bench.
