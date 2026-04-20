# abel-alpha

Workspace-first strategy research for agents.

The current model is intentionally simple:

- session owns `discovery.json` and `readiness.json`
- edge owns the market-data cache
- branch owns `branch.yaml`
- `prepare-branch` resolves inputs before a recorded run

For normal use, think in terms of one workspace and one runtime:

- default workspace name: `abel-alpha-workspace`
- canonical runtime: `<workspace>/.venv`
- default behavior on repeat entry: reuse the existing workspace before creating another one

When you are bootstrapping from an `Abel-alpha` source checkout, the checkout
`.venv` is only the installer environment for that checkout. After
`abel-alpha env init`, use the workspace `.venv` as the canonical runtime for
daily research work.

## Standard Flow

```bash
LAUNCH_ROOT="$PWD"
WORKSPACE_PATH="$LAUNCH_ROOT/abel-alpha-workspace"

# Current source-checkout flow:
# create a temporary installer environment for this checkout, then create the workspace explicitly
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# bash/zsh: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .

abel-alpha workspace init abel-alpha-workspace --path "$WORKSPACE_PATH"
cd "$WORKSPACE_PATH"
abel-alpha env init
abel-alpha doctor

# before starting a new login, first try to reuse existing causal-abel auth
# if no reusable auth is available, complete causal-abel OAuth once or use the standalone edge login fallback
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

## Re-entry

When you return to the same area later:

- if your current directory is already a workspace root, continue there
- otherwise, if `<current_dir>/abel-alpha-workspace` already exists, reuse it
- only create a new workspace when no reusable one exists or when you explicitly want a second workspace

After `abel-alpha env init`, the workspace `.venv` is the canonical runtime for
daily research work.

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
2. Derive the target workspace from the launch root and pass an explicit `--path`.
3. Reuse an existing workspace before creating a new one.
4. Use the fixed default workspace name `abel-alpha-workspace` unless the user asks for something else.
5. Tell the user explicitly when you are reusing an existing workspace.
6. Edit `branch.yaml` before trying to wire `engine.py`.
7. Run `prepare-branch` before a recorded round.
8. Treat readiness as advisory, not as a hard branch filter.
9. Prefer injected context over hard-coded file paths.
10. Let `branch.yaml.requested_start` override the session default when the branch needs a narrower window.

## Auth

`abel-alpha` does not auto-install `causal-abel`.

If reusable auth is already available through `causal-abel`, prefer reusing it.
If `doctor` still reports missing auth, complete `causal-abel` OAuth once and
rerun `doctor`. `causal-edge login` remains the standalone fallback when no
reusable auth is available.

## References

- `references/experiment-loop.md`
- `references/discovery-protocol.md`
- `references/constraints.md`
