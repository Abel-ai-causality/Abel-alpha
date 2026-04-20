---
name: abel-alpha
version: 3.2.0
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

The purpose of this skill is not just to run a workflow. Its job is to turn
Abel's causal graph information into a better exploration prior so strategy
search becomes more targeted, more compounding, and less like blind feature
search.

In practice, this skill should help the agent:

- start causal-first instead of scanning a huge undirected space
- turn discovery into a small explicit branch definition, not a giant candidate dump
- compound each round inside a persistent workspace instead of restarting from scratch
- use the CLI as tooling in service of exploration quality, not as the end goal

Keep the mental model simple:

- one working area
- one default workspace: `abel-alpha-workspace`
- one canonical runtime: `<workspace>/.venv`
- repeated use should reuse the existing workspace before creating another one

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

Use this default tool flow:

```bash
LAUNCH_ROOT="$PWD"
WORKSPACE_PATH="$LAUNCH_ROOT/abel-alpha-workspace"

abel-alpha workspace init abel-alpha-workspace --path "$WORKSPACE_PATH"  # first use only
cd "$WORKSPACE_PATH"
abel-alpha env init
abel-alpha doctor
abel-alpha init-session --ticker <TICKER> --exp-id <exp-id> --discover
abel-alpha init-branch --session research/<ticker>/<exp-id> --branch-id <branch-id>
abel-alpha prepare-branch --branch research/<ticker>/<exp-id>/branches/<branch-id>
abel-alpha run-branch --branch research/<ticker>/<exp-id>/branches/<branch-id> -d "baseline"
```

When you reuse an existing workspace, tell the user explicitly.
When auth is needed and an authorization URL appears, tell the user
immediately. Do not silently wait in the terminal without surfacing the URL.

Read references as needed:

- workflow and ownership: `references/experiment-loop.md`
- branch authoring and research judgment: `references/branch-authoring.md`
- discovery guidance: `references/discovery-protocol.md`
- structural safety rules: `references/constraints.md`
- mechanism inspiration after a branch is runnable: `references/proven-patterns.md`
- first-principles rationale: `references/methodology.md`
