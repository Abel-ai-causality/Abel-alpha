---
name: abel-alpha
version: 3.1.0
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

Use `Abel-alpha` as a workspace-first research CLI.

Do not improvise:

- environment setup
- workspace layout
- branch artifact locations
- runtime data loading paths

Use this default flow:

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

# if auth is missing, install causal-abel and finish OAuth once
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

Current framework rules:

1. `discovery.json` is only the session candidate snapshot.
2. `readiness.json` is only the session coverage/advisory report.
3. `branch.yaml` defines the branch runtime intent.
4. `prepare-branch` resolves inputs and warms edge cache before a recorded round.
5. `run-branch` should consume prepared branch inputs, not invent them at runtime.

When writing `engine.py`:

- prefer injected `self.context`
- prefer explicit branch inputs over discovery-side inference
- use `self.research_target_ticker()` and `self.research_requested_start()`
- do not parse relative workspace files manually unless the context is missing

Keep readiness advisory:

- use it to understand coverage
- do not treat it as a hard permission system
- do not force all drivers to share the latest common start unless the branch thesis truly requires strict overlap

Default references:

- experiment flow: `references/experiment-loop.md`
- discovery role: `references/discovery-protocol.md`
- structural safety: `references/constraints.md`
