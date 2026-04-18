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

## What Each Layer Owns

- session: discovery and readiness
- branch: branch spec and engine
- edge cache: market data reuse
- prepare step: branch input resolution
- run step: evaluation and recording

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

## Explore vs Exploit

- explore: genuinely new information or a different causal angle
- exploit: parameter tuning, threshold tuning, or local refinement on the same idea

Use branch history to compound on the latest credible baseline instead of
pre-defining a large static experiment grid.

## Validation Failures

Treat failures as localization signals:

- data/setup failure: fix branch spec or prepare step
- runtime failure: fix engine implementation
- validation failure: change the strategy idea

Do not mix these categories together.
