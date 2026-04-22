---
name: abel-alpha
version: 3.3.1
description: >
  Use when: the user wants to start or continue an Abel-alpha research workflow
  for an asset, detect or create the default workspace for the current launch
  root, reuse an existing Abel workspace, prepare that workspace runtime, check
  readiness, reuse existing causal-abel auth when available, use Abel causal
  discovery as the default exploration prior, or continue the session/branch
  exploration loop through the Abel-alpha CLI tools.
metadata:
  openclaw:
    requires:
      bins: [python]
      packages: [causal-edge]
    optionalEnv: [ABEL_API_KEY]
    homepage: https://github.com/Abel-ai-causality/Abel-alpha
---

Use `Abel-alpha` as the workspace-first orchestration skill for branch research.

The point is not to memorize commands. The point is to make the strategy world
explicit before the agent writes code.

Abel's causal graph is the opening prior, not the final answer. Use it to cut
down blind search, define narrower branch theses, and compound from the latest
credible branch instead of restarting from scratch.

Alpha owns the research workspace layout. Inside an Abel-alpha workspace, keep
the work on the session/branch path under `research/`. If you need a standalone
`causal-edge init` project, create it outside the workspace instead of mixing
the two modes.

Keep the mental model simple:

- one working area
- one default workspace: `abel-alpha-workspace`
- one canonical runtime: `<workspace>/.venv`
- one active research path under `research/`
- one default branch contract centered on prepared inputs plus `DecisionContext`

Do not improvise workspace location, workspace name, runtime layout, or auth
order.

When an agent is launched, treat the launch working directory as the anchor for
workspace behavior.

Do not determine workspace existence by checking only whether
`<launch-root>/abel-alpha-workspace` exists. The working area itself may
already be the workspace root.

Use this workspace resolution order:

1. if `<launch-root>/alpha.workspace.yaml` exists, continue in `<launch-root>`
2. else if `<launch-root>/abel-alpha-workspace/alpha.workspace.yaml` exists, reuse that child workspace
3. else create `<launch-root>/abel-alpha-workspace`

Always pass an explicit `--path` when creating a workspace. Do not invent a
new workspace name unless the user asked for one explicitly.
Never bootstrap a new workspace inside a directory that already contains
`alpha.workspace.yaml`.

Use this auth order:

1. reuse any existing auth already available in the process or workspace
2. reuse available `causal-abel` auth
3. only if reusable auth is unavailable, complete a new login

When `doctor` or the next required exploration step reports `auth_missing`,
treat that as the next workflow transition. If no reusable auth was found,
start the explicit auth handoff from the workspace runtime and surface the URL
as soon as it exists.

On first contact with a new working area, the job is simply to establish the
workspace. If the default workspace does not exist yet, start there with system
Python and let Abel-alpha provision the real runtime inside the workspace:

```bash
LAUNCH_ROOT="$PWD"
if [ -f "$LAUNCH_ROOT/alpha.workspace.yaml" ]; then
  WORKSPACE_PATH="$LAUNCH_ROOT"
elif [ -f "$LAUNCH_ROOT/abel-alpha-workspace/alpha.workspace.yaml" ]; then
  WORKSPACE_PATH="$LAUNCH_ROOT/abel-alpha-workspace"
else
  WORKSPACE_PATH="$LAUNCH_ROOT/abel-alpha-workspace"
  python3 /path/to/Abel-alpha/scripts/bootstrap_workspace.py --path "$WORKSPACE_PATH"
fi
```

That is the setup moment, not the day-to-day loop. Once the workspace exists,
work from inside it:

```bash
cd "$WORKSPACE_PATH"
abel-alpha doctor
abel-alpha init-session --ticker <TICKER> --exp-id <exp-id> --discover
abel-alpha init-branch --session research/<ticker>/<exp-id> --branch-id <branch-id>
edit research/<ticker>/<exp-id>/branches/<branch-id>/branch.yaml
abel-alpha prepare-branch --branch research/<ticker>/<exp-id>/branches/<branch-id>
abel-alpha debug-branch --branch research/<ticker>/<exp-id>/branches/<branch-id>
abel-alpha run-branch --branch research/<ticker>/<exp-id>/branches/<branch-id> -d "baseline"
```

That path is orientation, not ritual. The important information order is:

1. `branch.yaml` states the branch intent.
2. `prepare-branch` writes the branch runtime contract under `inputs/`.
3. `engine.py` is authored against `DecisionContext`, not raw loaders.
4. `debug-branch` runs semantic preflight before a recorded round.
5. `run-branch` records evidence only after the branch is semantically valid.

`prepare-branch` now writes the concrete authoring contract:

- `inputs/runtime_profile.json`
- `inputs/execution_constraints.json`
- `inputs/data_manifest.json`
- `inputs/context_guide.md`
- `inputs/probe_samples.json`
- `inputs/dependencies.json`

Those files are not bookkeeping. They are the visible runtime world the agent
should inspect before writing or revising strategy code.

Treat the generated `engine.py` as a runnable starter, not a finished thesis.
The default authoring surface is:

- `compute_decisions(self, ctx)`
- `ctx.target.series("close")`
- `ctx.feed(name).native_series(...)`
- `ctx.feed(name).asof_series(...)`
- `ctx.points()`
- `ctx.decisions(next_position)`

Do not teach yourself that legality means "remember to add `.shift(1)`". The
legality contract is runtime-owned:

- only read market data through `DecisionContext`
- only emit next-position intent through `ctx.decisions(...)`
- let semantic preflight tell you when visibility or timing assumptions are wrong

If you re-enter from the parent launch directory instead of the workspace root,
reuse that same child workspace before creating anything new.
If `alpha.workspace.yaml` is already present in the current directory, that
directory is the workspace root and you should not create a nested child.

When you reuse an existing workspace, say so explicitly. When auth is needed
and an authorization URL appears, tell the user immediately.

Read references as needed:

- workflow and ownership: `references/experiment-loop.md`
- branch authoring and research judgment: `references/branch-authoring.md`
- discovery guidance: `references/discovery-protocol.md`
- runtime legality and safety: `references/constraints.md`
- mechanism inspiration after a branch is runnable: `references/proven-patterns.md`
- first-principles rationale: `references/methodology.md`
