---
name: abel-alpha
version: 3.2.0
description: >
  Use when: user wants to research what drives an asset, create a new Abel-alpha
  research workspace, or run an agent-guided strategy exploration loop.
  Requires the packaged abel-alpha CLI and causal-edge.
metadata:
  openclaw:
    requires:
      bins: [python]
      packages: [causal-edge]
    optionalEnv: [ABEL_API_KEY]
    homepage: https://github.com/Abel-ai-causality/Abel-alpha
---

Causation is the default prior because it is more likely to survive regime change
than blind correlation scans.

Use `Abel-alpha` as a workspace-first research CLI.
The point is not to make the workspace feel clever. The point is to help an
agent converge on a tradable mechanism with fewer wasted rounds.

For normal use, think in terms of one workspace and one canonical runtime:

- default workspace name: `abel-alpha-workspace`
- canonical runtime: `<workspace>/.venv`
- repeated use should reuse the existing workspace before creating another one

Assume the `abel-alpha` command is already available through the installed
skill/runtime. User-facing guidance should focus on workspace behavior, not on
how the repo itself is installed.

Do not improvise:

- environment setup
- workspace layout
- branch artifact locations
- runtime data loading paths

When an agent is launched, treat the agent launch working directory root as the
anchor point for workspace behavior.

Use this workspace resolution order:

1. if the current directory is already an Abel-alpha workspace, continue there
2. else if `<launch-root>/abel-alpha-workspace` exists, reuse it
3. else create `<launch-root>/abel-alpha-workspace`

Do not invent a new workspace name unless the user asked for one explicitly.
Do not silently pick a path from an internal cwd guess. Use the launch root and
an explicit `--path`.

Use this default flow:

```bash
LAUNCH_ROOT="$PWD"
WORKSPACE_PATH="$LAUNCH_ROOT/abel-alpha-workspace"

# create a workspace at an explicit path and prepare its runtime
abel-alpha workspace init abel-alpha-workspace --path "$WORKSPACE_PATH"
cd "$WORKSPACE_PATH"
abel-alpha env init
abel-alpha doctor

# before starting a new login, first try to reuse any existing causal-abel auth
# if no reusable auth is available, complete causal-abel OAuth once or use the standalone edge login fallback
abel-alpha init-session --ticker <TICKER> --exp-id <exp-id> --discover
abel-alpha init-branch --session research/<ticker>/<exp-id> --branch-id <branch-id>

# confirm branch inputs first
edit research/<ticker>/<exp-id>/branches/<branch-id>/branch.yaml
edit research/<ticker>/<exp-id>/branches/<branch-id>/engine.py

abel-alpha prepare-branch --branch research/<ticker>/<exp-id>/branches/<branch-id>
abel-alpha debug-branch --branch research/<ticker>/<exp-id>/branches/<branch-id>
abel-alpha run-branch --branch research/<ticker>/<exp-id>/branches/<branch-id> -d "baseline"
abel-alpha status --session research/<ticker>/<exp-id>
```

`abel-alpha env init` prepares the workspace runtime and installs
`causal-edge` there.

When you reuse an existing workspace, tell the user explicitly. Good examples:

- "Found existing workspace at `/path/to/abel-alpha-workspace`; I will continue there."
- "Current directory is already an Abel workspace; I will continue here."

When auth is needed and an authorization URL appears, tell the user
immediately. Do not silently wait in the terminal without surfacing the URL.

Current framework rules:

1. `discovery.json` is only the session candidate snapshot.
2. `readiness.json` is only the session coverage/advisory report.
3. `branch.yaml` defines the branch runtime intent.
4. `prepare-branch` resolves inputs and warms edge cache before a recorded round.
5. `run-branch` should consume prepared branch inputs, not invent them at runtime.
6. Session `backtest_start` is the default research target; `branch.yaml.requested_start` may override it explicitly.

Discovery gives leads, not answers. Readiness gives coverage clues, not
permission. A branch is where the research becomes a falsifiable bet.

Your job is not to invent a new process record system. Your job is to:

- state a branch thesis clearly
- write `engine.py`
- prepare the branch inputs
- interpret the result honestly
- decide the next branch move

Alpha owns the bookkeeping so the branch can focus on mechanism, not file
management theater.

When writing `engine.py`:

- prefer injected `self.context`
- prefer explicit branch inputs over discovery-side inference
- use `self.research_target_ticker()` and `self.research_requested_start()`
- do not parse relative workspace files manually unless the context is missing

Keep readiness advisory:

- use it to understand coverage
- do not treat it as a hard permission system
- do not force all drivers to share the latest common start unless the branch thesis truly requires strict overlap
- do not confuse session start guidance with the branch's explicit requested start

## Research Judgment

- Start causal-first. Correlation-derived signals are allowed when they add something truly orthogonal, but they do not replace Abel discovery as the main search prior.
- Explore means new information, a new transmission path, or a genuinely different mechanism. Parameter polish is exploit, not explore.
- Weird low-attention parents are not automatically noise. They are often where causal information first appears. Explain them before you discard them.
- Treat validation failure as direction, not as a prompt to hack metrics. If the mechanism is weak, change the mechanism.
- Serial compounding beats pre-declaring a large experiment grid. Let each credible round update the next move.
- Stop honestly when recent rounds are no longer improving and no high-quality new direction remains. Do not burn compute on noise just to keep the loop alive.

Default references:

- experiment flow: `references/experiment-loop.md`
- discovery role: `references/discovery-protocol.md`
- structural safety: `references/constraints.md`

Optional references:

- mechanism inspiration after a branch is runnable: `references/proven-patterns.md`
- first-principles research rationale: `references/methodology.md`
