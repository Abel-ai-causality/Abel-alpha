# abel-alpha

Workspace-first research skill for agents.

`Abel-alpha` should feel like one skill with one default workspace per working
area. The CLI commands are the tools the skill uses to detect or create that
workspace, prepare its runtime, and continue the research loop inside it.

The point is not to make the workflow feel elaborate. The point is to make
strategy exploration less blind.

Use Abel's causal graph as the opening prior: narrower search, clearer branch
hypotheses, and faster compounding from one round to the next.

## Default Model

- launch root: the current agent launch directory
- default workspace name: `abel-alpha-workspace`
- default workspace path: `<launch_root>/abel-alpha-workspace`
- canonical runtime: `<workspace>/.venv`
- repeated use: reuse the existing workspace before creating another one
- system Python should only matter for the first establishment step

## First Use And Re-entry

On first use in a new working area, the right move is to establish the default
workspace and let it create its own runtime. If only system Python is
available, use the thin bootstrap entrypoint:

```bash
LAUNCH_ROOT="$PWD"
WORKSPACE_PATH="$LAUNCH_ROOT/abel-alpha-workspace"

python scripts/bootstrap_workspace.py --path "$WORKSPACE_PATH"
```

After that, the workspace should take over. Re-enter the workspace and continue
there with its own CLI and `.venv`:

```bash
cd "$WORKSPACE_PATH"
abel-alpha doctor
abel-alpha init-session --ticker TSLA --exp-id tsla-v1 --discover
abel-alpha init-branch --session research/tsla/tsla-v1 --branch-id graph-v1
abel-alpha prepare-branch --branch research/tsla/tsla-v1/branches/graph-v1
abel-alpha run-branch --branch research/tsla/tsla-v1/branches/graph-v1 -d "baseline"
```

If you come back from the parent launch directory instead of the workspace
root, Abel-alpha should still resolve and reuse that same child workspace
before it creates anything new.

If the CLI is already available before the first workspace exists, `abel-alpha
workspace bootstrap --path "$WORKSPACE_PATH"` is an equivalent setup path, but
it is not the main mental model.

If auth is needed, reuse existing `causal-abel` auth first. Only fall back to a
new login when reusable auth is unavailable.

## References

- skill behavior: [SKILL.md](SKILL.md)
- experiment loop: `references/experiment-loop.md`
- branch authoring: `references/branch-authoring.md`
- discovery guidance: `references/discovery-protocol.md`
- structural constraints: `references/constraints.md`
