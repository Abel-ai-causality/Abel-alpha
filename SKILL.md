---
name: abel-alpha
version: 3.3.0
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

Use `Abel-alpha` as a workspace-first research skill.
The CLI commands are the tools this skill uses to get the user into the right
workspace and continue research there.

The point of this skill is not to make the workflow feel elaborate.
The point is to make exploration less blind.

Abel's causal graph is the opening prior, not the final answer.
Use it to narrow the search space, surface more plausible mechanisms, and make
each round compound on a smaller, more defensible set of ideas.

Alpha owns the research workspace layout. When you are inside an Abel-alpha
workspace, keep the work on the session/branch path under `research/`. If you
need a standalone `causal-edge init` project, create it outside the
Abel-alpha workspace instead of mixing the two modes.

There are two layers of environment:

In practice, this skill should help the agent:

- start causal-first instead of scanning a huge undirected space
- turn discovery into a small explicit branch definition, not a giant candidate dump
- preserve compounding inside a persistent workspace instead of restarting from scratch
- use the CLI as tooling in service of exploration quality, not as the end goal

Keep the mental model simple:

- one working area
- one default workspace: `abel-alpha-workspace`
- one canonical runtime: `<workspace>/.venv`
- repeated use should reuse the existing workspace before creating another one
- system Python matters only long enough to establish the workspace once

Do not improvise:

- workspace location
- workspace name
- runtime layout
- auth order

When an agent is launched, treat the launch working directory as the anchor for
workspace behavior.

Use this workspace resolution order:

1. if the current directory is already an Abel-alpha workspace, continue there
2. else if `<launch-root>/abel-alpha-workspace` exists, reuse it
3. else create `<launch-root>/abel-alpha-workspace`

Always pass an explicit `--path` when creating a workspace.
Do not invent a new workspace name unless the user asked for one explicitly.

Use this auth order:

1. reuse any existing auth already available in the process or workspace
2. reuse available `causal-abel` auth
3. only if reusable auth is unavailable, complete a new login

When `doctor` or the next required exploration step reports `auth_missing`,
treat that as the next workflow transition, not as background troubleshooting.
If no reusable auth was found, immediately start the explicit auth handoff from
the workspace runtime and only pause once the authorization URL is ready for
the user.

Think about the workflow in two phases, not one long command list.

On first contact with a new working area, the job is simply to establish the
workspace. If the default workspace does not exist yet, start there with system
Python and let Abel-alpha provision the real runtime inside the workspace:

```bash
LAUNCH_ROOT="$PWD"
WORKSPACE_PATH="$LAUNCH_ROOT/abel-alpha-workspace"
python3 /path/to/Abel-alpha/scripts/bootstrap_workspace.py --path "$WORKSPACE_PATH"
```

That is the setup moment, not the day-to-day loop.

Once the workspace exists, shift your attention into that directory and treat
its `abel-alpha` CLI and `.venv` as the normal place to continue research. The
ongoing flow should feel like continuation, not repeated setup:

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

That path is a useful orientation, not a rigid script. The important boundary
is that `branch.yaml` makes the branch inputs explicit, `prepare-branch`
resolves them before a recorded round, and the generated `engine.py` is only a
starter path check until the branch-specific mechanism exists.

If you re-enter from the parent launch directory instead of the workspace root,
reuse that same child workspace before creating anything new.

If `abel-alpha doctor` reports `auth_missing`, immediately run the workspace
runtime's explicit handoff command, surface the URL as soon as it appears, and
resume the branch flow after authorization succeeds.

Treat the generated `engine.py` as a runnable starter path check. It is there
to make the first branch path real and debuggable; once that path is proven,
swap it for the branch-specific thesis instead of treating the starter engine
as a finished idea.

If the packaged CLI is already available before first use, `abel-alpha
workspace bootstrap --path "$WORKSPACE_PATH"` is an equivalent setup path. It
is not the main story. The main story is: establish the workspace once, then
work from inside it.

When you reuse an existing workspace, say so explicitly.
When auth is needed and an authorization URL appears, tell the user
immediately. Do not silently wait in the terminal without surfacing the URL.

Read references as needed:

- workflow and ownership: `references/experiment-loop.md`
- branch authoring and research judgment: `references/branch-authoring.md`
- discovery guidance: `references/discovery-protocol.md`
- structural safety rules: `references/constraints.md`
- mechanism inspiration after a branch is runnable: `references/proven-patterns.md`
- first-principles rationale: `references/methodology.md`
