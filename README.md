# abel-alpha

Workspace-first strategy research for agents.

The current model is intentionally simple:

- session owns `discovery.json` and `readiness.json`
- edge owns the market-data cache
- branch owns `branch.yaml`
- `prepare-branch` resolves inputs before a recorded run

## Standard Flow

```bash
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# bash/zsh: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .

abel-alpha workspace init my-lab
cd my-lab
abel-alpha env init
abel-alpha doctor

# if auth is missing, install causal-abel and complete OAuth once
abel-alpha init-session --ticker TSLA --exp-id tsla-v1 --discover
abel-alpha init-branch --session research/tsla/tsla-v1 --branch-id graph-v1

# make branch inputs explicit
edit research/tsla/tsla-v1/branches/graph-v1/branch.yaml
edit research/tsla/tsla-v1/branches/graph-v1/engine.py

abel-alpha prepare-branch --branch research/tsla/tsla-v1/branches/graph-v1
abel-alpha debug-branch --branch research/tsla/tsla-v1/branches/graph-v1
abel-alpha run-branch --branch research/tsla/tsla-v1/branches/graph-v1 -d "baseline"
abel-alpha status --session research/tsla/tsla-v1
abel-alpha promote-branch --branch research/tsla/tsla-v1/branches/graph-v1
```

## Current Boundaries

### Session artifacts

- `discovery.json`: candidate universe only
- `readiness.json`: advisory coverage report only
- session `backtest_start`: default research target, not a mandatory branch runtime start

### Branch artifacts

- `branch.yaml`: target, requested start, overlap mode, selected drivers
- `inputs/dependencies.json`: prepared input/cache view
- `engine.py`: signal implementation

### Runtime

`run-branch` should use prepared branch inputs. It is not the place to invent
the branch definition.

`promote-branch` currently creates a clean promotion bundle, not a full formal
strategy scaffold.

## Rules For Agents

1. Do not invent your own workspace layout.
2. Edit `branch.yaml` before trying to wire `engine.py`.
3. Run `prepare-branch` before a recorded round.
4. Treat readiness as advisory, not as a hard branch filter.
5. Prefer injected context over hard-coded file paths.
6. Let `branch.yaml.requested_start` override the session default when the branch needs a narrower window.

## Auth

`abel-alpha` does not auto-install `causal-abel`.

If `doctor` reports missing auth, install `causal-abel`, complete OAuth once,
and rerun `doctor`. `causal-edge login` remains the standalone fallback.

## References

- `references/experiment-loop.md`
- `references/discovery-protocol.md`
- `references/constraints.md`
