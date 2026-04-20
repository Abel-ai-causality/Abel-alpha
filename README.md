# abel-alpha

Workspace-first research skill for agents.

`Abel-alpha` should feel like one skill with one default workspace per working
area. The CLI commands are the tools the skill uses to detect or create that
workspace, prepare its runtime, and continue the research loop inside it.

The point is to help agents use Abel's causal graph information as a stronger
exploration prior: narrower search, clearer branch hypotheses, and faster
compounding from one round to the next.

## Default Model

- launch root: the current agent launch directory
- default workspace name: `abel-alpha-workspace`
- default workspace path: `<launch_root>/abel-alpha-workspace`
- canonical runtime: `<workspace>/.venv`
- repeated use: reuse the existing workspace before creating another one

## Core Flow

```bash
LAUNCH_ROOT="$PWD"
WORKSPACE_PATH="$LAUNCH_ROOT/abel-alpha-workspace"

abel-alpha workspace init abel-alpha-workspace --path "$WORKSPACE_PATH"  # first use only
cd "$WORKSPACE_PATH"
abel-alpha env init
abel-alpha doctor
abel-alpha init-session --ticker TSLA --exp-id tsla-v1 --discover
abel-alpha init-branch --session research/tsla/tsla-v1 --branch-id graph-v1
abel-alpha prepare-branch --branch research/tsla/tsla-v1/branches/graph-v1
abel-alpha run-branch --branch research/tsla/tsla-v1/branches/graph-v1 -d "baseline"
```

If auth is needed, reuse existing `causal-abel` auth first. Only fall back to a
new login when reusable auth is unavailable.

## References

- skill behavior: [SKILL.md](SKILL.md)
- experiment loop: `references/experiment-loop.md`
- branch authoring: `references/branch-authoring.md`
- discovery guidance: `references/discovery-protocol.md`
- structural constraints: `references/constraints.md`
