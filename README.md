# abel-alpha

Workspace-first strategy research skill for agents.

Treat `Abel-alpha` as a skill, not as a repo-management task.
The CLI commands are the tools this skill uses to:

- detect or create a workspace for the current working area
- prepare that workspace runtime
- continue the research loop inside that workspace

For normal use, keep this mental model simple:

- one working area
- one default workspace: `abel-alpha-workspace`
- one canonical runtime: `<workspace>/.venv`
- reuse the existing workspace before creating another one

## Default Behavior

- launch root: the current agent launch directory
- default workspace path: `<launch_root>/abel-alpha-workspace`
- explicit creation path: always pass `--path`
- repeat entry: if the workspace already exists, continue there

## Skill Loop

1. Check whether the current directory is already an Abel workspace.
2. Otherwise, check whether `<launch_root>/abel-alpha-workspace` already exists.
3. Reuse that workspace if it exists.
4. Only create a new workspace when none exists yet, or when the user explicitly asks for another one.
5. Run `env init` and `doctor`.
6. Reuse existing `causal-abel` auth if available; only fall back to a new login when needed.
7. Continue with session, branch, and round work.

## Standard Flow

```bash
LAUNCH_ROOT="$PWD"
WORKSPACE_PATH="$LAUNCH_ROOT/abel-alpha-workspace"

abel-alpha workspace init abel-alpha-workspace --path "$WORKSPACE_PATH"  # first use only
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

After `abel-alpha env init`, the workspace `.venv` is the canonical runtime for
daily research work.

## Current Boundaries

- session owns `discovery.json` and `readiness.json`
- `branch.yaml`: target, requested start, overlap mode, selected drivers
- edge owns the market-data cache
- `prepare-branch` resolves inputs before a recorded run
- `run-branch` should use prepared branch inputs, not invent the branch definition at runtime

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
