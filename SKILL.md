---
name: causal-alpha
version: 3.0.0
description: >
  Use when: user wants to find alpha, discover what drives an asset, research
  a new asset, run autoresearch, or asks "what drives X?" / "find signals for X".
  Requires causal-edge package and optionally Abel API key.
metadata:
  openclaw:
    requires:
      bins: [python]
      packages: [causal-edge]
    optionalEnv: [ABEL_API_KEY]
    homepage: https://github.com/Abel-ai-causality/Abel-alpha
---

Causation is the default prior because it survives regime change more often than correlation.

Main install entrypoint: create and activate a virtual environment, install `Abel-edge`, then use the `causal-edge` CLI. `Abel-alpha` does not auto-install `causal-abel`. If live Abel discovery needs auth, install `causal-abel` from `Abel-skills/tree/main/skills`, finish its OAuth flow, and let `causal-edge` reuse that shared auth before falling back to `causal-edge login`. If it still reports a missing key, check `python <causal-abel-skill-root>/scripts/cap_probe.py auth-status --compact` or point `ABEL_AUTH_ENV_FILE` at the exported auth file.

```bash
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# bash/zsh: source .venv/bin/activate
python -m pip install --upgrade pip
pip install git+https://github.com/Abel-ai-causality/Abel-edge.git
python scripts/research_narrative.py init-session --ticker <TICKER> --exp-id <exp-id>
npx --yes skills add https://github.com/Abel-ai-causality/Abel-skills/tree/main/skills --skill causal-abel -y
# use -g for a global install in the current agent platform
# then complete causal-abel OAuth once and let causal-edge reuse it
python scripts/research_narrative.py init-session --ticker <TICKER> --exp-id <exp-id> --discover
python scripts/research_narrative.py init-branch --session research/<ticker>/<exp-id> --branch-id <branch-id>
python scripts/research_narrative.py run-branch --branch research/<ticker>/<exp-id>/branches/<branch-id> -d "baseline"
python scripts/research_narrative.py status --session research/<ticker>/<exp-id>
python scripts/research_narrative.py check --session research/<ticker>/<exp-id> --strict
```

`Abel-edge` emits raw validation facts. `Abel-alpha` owns session/branch organization,
keep/discard, process records, and narrative summaries. Use `init-session --discover`
when you want the live Abel discovery persisted into `discovery.json` and the event trail.
Your job: write the strategy implementation.

Default to causal-first research. Correlation-derived signals are allowed as supplements when they add orthogonal information, but they do not replace Abel-driven discovery as the main search path.

## Judgment Calls (only you can make these)

- **Explore vs exploit?** New data dimension = explore. Parameter tweak = exploit. Swapping ML framework = exploit. See `references/experiment-loop.md`.
- **Discovery priority?** Keep exploration open, but default to direct parents first. Inside the Markov blanket, prioritize parents over children, and children over spouses/co-parents. Treat crypto peers as low-priority supplements. See `references/discovery-protocol.md`.
- **Micro-cap parents look weird?** That's the signal. Causal info transmits from low-attention assets. Abel's graph is mostly micro-caps by design.
- **Validation failure?** It's your next research direction, not an obstacle. DSR low = K too high. MaxDD bad = drawdown signal weak. Don't hack metrics — fix the signal. See `references/experiment-loop.md#addressing-validation-failures`.
- **When to stop?** Treat 20+ consecutive discards AND 3+ genuine explore dimensions as the floor, not the full rule. Stop only when recent rounds show no material validation improvement and no high-quality new direction remains. Report honest failure. Don't burn compute on noise.

## Parallelism (correctness first, then max throughput)

Parallelize everything that's independent. Never parallelize what's sequential.

**Parallel (independent):**
- Abel queries: parents + blanket + children are 3 independent API calls
- Data fetching: each ticker's price history is independent
- Multi-asset research: research SOL and TSLA simultaneously (separate workspaces)
- Multi-branch research: one exploration session can branch into multiple candidate branches
- Dashboard generation: each strategy's charts are independent
- Backfill: multiple strategies can backfill concurrently

**Sequential (dependent — compounding requires order):**
- Experiment loop: exp002 depends on exp001's result. Serial, not parallel.
- KEEP decision: validate, compare vs baseline, THEN record. Cannot record before verdict.
- Process record: use the Abel-alpha script to keep `events.tsv`, round notes, README, thesis, and memory in sync.

**In practice:** use Agent tool to dispatch parallel research across assets. Within each asset, experiments are serial. `causal-edge` handles IO parallelism (discovery, dashboard) internally.

## References

| Need | Read |
|---|---|
| Experiment loop, explore/exploit, KEEP rule | `references/experiment-loop.md` |
| Discovery protocol, multihop, blanket | `references/discovery-protocol.md` |
| Structural strategy constraints | `references/constraints.md` |
| Feature patterns from 200+ experiments | `references/proven-patterns.md` |
| Why causal works (Pearl, DGP, axioms) | `references/methodology.md` |

**REQUIRED SKILL:** `causal-abel` for Abel API access (cap_probe.py, auth flow). Install it from `https://github.com/Abel-ai-causality/Abel-skills/tree/main/skills`.

## Abel-Pro Mapping

- Abel-alpha worktree for the Abel-Pro integration: `D:\codes\causal-alpha\.tree\abel-pro`
- Abel-alpha branch for that worktree: `abel-pro`
- Paired Abel-edge worktree for validation and execution: `D:\codes\open_source\causal-edge\.tree\abel-pro-demo`
- Paired Abel-edge branch: `abel-pro-demo`
- Abel auth and data environment defaults to prod
