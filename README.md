# abel-alpha

Workspace-first research skill for agent-driven strategy exploration.

`Abel-alpha` is the orchestration layer around the branch workflow:

- create or reuse the default workspace
- open a causal-first session
- make branch inputs explicit
- prepare the branch runtime context
- run semantic preflight before recording evidence
- compound on the strongest branch result instead of restarting blind

The main product idea is simple: the agent should not write strategy code while
guessing what data world it is in.

## Default Mental Model

- one launch root
- one default workspace: `abel-alpha-workspace`
- one canonical runtime: `<workspace>/.venv`
- one active research path under `research/`
- one session-owned graph frontier in `frontier.json`
- one default branch contract centered on prepared runtime inputs plus
  `DecisionContext`

Before creating anything, identify whether the current directory is already the
workspace:

- if `./alpha.workspace.yaml` exists, this directory is already the workspace root
- else if `./abel-alpha-workspace/alpha.workspace.yaml` exists, reuse that child workspace
- only if neither manifest exists should you bootstrap a new `abel-alpha-workspace`

Do not decide workspace existence by checking only whether
`./abel-alpha-workspace/` exists. A working area can itself already be the
workspace root.

If you need a standalone `causal-edge init` project, create it outside the
Abel-alpha workspace. The branch workflow and the standalone framework scaffold
serve different purposes.

## Default Loop

```bash
cd "$WORKSPACE_PATH"
abel-alpha doctor
abel-alpha init-session --ticker TSLA --exp-id tsla-v1 --discover
abel-alpha frontier-status --session research/tsla/tsla-v1
abel-alpha probe-nodes --session research/tsla/tsla-v1 --node TSLA.volume
abel-alpha expand-frontier --session research/tsla/tsla-v1 --from-node TSLA.volume
abel-alpha init-branch --session research/tsla/tsla-v1 --branch-id graph-v1
abel-alpha select-inputs --branch research/tsla/tsla-v1/branches/graph-v1 --node TSLA.volume --replace
abel-alpha prepare-branch --branch research/tsla/tsla-v1/branches/graph-v1
abel-alpha debug-branch --branch research/tsla/tsla-v1/branches/graph-v1
abel-alpha run-branch --branch research/tsla/tsla-v1/branches/graph-v1 -d "baseline"
```

The important boundary is not the exact command list. The important boundary is
the order of information:

1. inspect or expand the session frontier
2. probe candidate nodes before committing to a branch thesis
3. make `selected_inputs` explicit
4. `prepare-branch` materializes the branch runtime contract
5. `debug-branch` runs semantic preflight
6. `run-branch` records evidence only after the branch is semantically valid

## What `prepare-branch` Produces

`prepare-branch` now writes a concrete branch contract under `inputs/`:

- `runtime_profile.json`
- `execution_constraints.json`
- `data_manifest.json`
- `window_availability.json`
- `context_guide.md`
- `probe_samples.json`
- `dependencies.json`

Those files are not bookkeeping theater. They are the visible contract the
agent writes against.

## What The Starter Engine Means

The generated `engine.py` is a runnable starter, not a finished thesis.

It should teach the branch-default authoring surface:

- `compute_decisions(self, ctx)`
- `ctx.target.series("close")`
- `ctx.input(name).asof_series(...)`
- `ctx.inputs_frame(...)`
- `ctx.feed(name)...`
- `ctx.points()`
- `ctx.decisions(next_position)`

The first real branch step is usually:

- replace the starter mechanism
- run `debug-branch`
- read semantic feedback
- then decide whether a full recorded round is justified

## Auth And Re-entry

If `abel-alpha doctor` reports `auth_missing`, treat that as the next workflow
transition. Reuse existing `causal-abel` auth when available; only fall back to
new login when reuse is unavailable.

If you re-enter from the parent launch directory instead of the workspace root,
Abel-alpha should reuse the same child workspace before creating anything new.
If `alpha.workspace.yaml` is already in the current directory, continue there
directly and do not create a nested child workspace.

## References

- skill behavior: [SKILL.md](SKILL.md)
- experiment loop: `references/experiment-loop.md`
- branch authoring: `references/branch-authoring.md`
- runtime safety and legality: `references/constraints.md`
- discovery guidance: `references/discovery-protocol.md`
- methodology: `references/methodology.md`
