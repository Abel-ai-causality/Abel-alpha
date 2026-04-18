# Experiment Loop

## Standard Path

```bash
abel-alpha init-session --ticker <TICKER> --exp-id <exp-id> --discover
abel-alpha init-branch --session research/<ticker>/<exp_id> --branch-id graph-v1

# first make the branch explicit
edit research/<ticker>/<exp_id>/branches/graph-v1/branch.yaml
edit research/<ticker>/<exp_id>/branches/graph-v1/engine.py

abel-alpha prepare-branch --branch research/<ticker>/<exp_id>/branches/graph-v1
abel-alpha debug-branch --branch research/<ticker>/<exp_id>/branches/graph-v1
abel-alpha run-branch --branch research/<ticker>/<exp_id>/branches/graph-v1 -d "baseline"
```

Before this loop, the workspace should already exist and `abel-alpha doctor`
should already be acceptable.
This is a compounding search loop, not a checklist of unrelated backtests.
Each round should answer a question about mechanism, not just consume compute.

## What Each Layer Owns

- session: discovery and readiness
- branch: branch spec and engine
- edge cache: market data reuse
- prepare step: branch input resolution
- run step: evaluation and recording

Session `backtest_start` is the default exploration target. When
`branch.yaml.requested_start` is set explicitly, that branch start should drive
prepare/debug/run for the branch.

## Branch Rules

Before a recorded round, the branch should already have:

- `branch.yaml`
- `engine.py`
- `inputs/dependencies.json` from `prepare-branch`

`run-branch` is not the place to decide the branch universe implicitly.

## KEEP Rule

```
KEEP if: causal-edge verdict == "PASS" AND metrics improve vs latest KEEP baseline
DISCARD: everything else
```

Each KEEP updates the baseline. The next round should compound on the latest
credible result rather than on a pre-declared static experiment grid.
DISCARD is not wasted motion when it narrows the mechanism honestly.

## Explore vs Exploit

- explore: genuinely new information or a different causal angle
- exploit: parameter tuning, threshold tuning, or local refinement on the same idea

Use branch history to compound on the latest credible baseline instead of
pre-defining a large static experiment grid.
If multiple exploit variants die the same death, stop polishing and force a
real explore move.

## Failure Interpretation

Treat failures as localization signals:

- data/setup failure: fix branch spec or prepare step
- runtime failure: fix engine implementation
- validation failure: change the strategy idea

Do not mix these categories together. A branch that fails validation is still a
useful research result if it tells you which mechanism is weak.
The wrong lesson is "the branch failed." The useful lesson is "what failed:
data path, implementation, or idea?"

## Compounding Rule

Serial execution preserves learning. Static grids destroy it.

- if a round reveals a stronger mechanism, compound from that mechanism
- if a round only reveals a local implementation defect, fix the defect before changing the thesis
- if repeated exploit variants keep failing the same way, force a genuine explore move
- if the failure signature changes after a branch edit, that change is itself evidence about the mechanism

## Honest Stop

Do not stop at the first dry patch, and do not keep searching just to avoid
reporting failure.

- repeated discards are acceptable when the branch is still exploring real new dimensions
- repeated versions of the same weak idea are not progress
- a clean "no usable signal yet" conclusion is better than a noisy pseudo-KEEP
- honest failure is part of research discipline, not an embarrassment to hide
