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

Main install entrypoint: install `Abel-edge` first, then use the `causal-edge` CLI. If live Abel discovery needs auth, install `causal-abel` and complete its OAuth flow.

```bash
pip install git+https://github.com/Abel-ai-causality/Abel-edge.git
causal-edge init <name>               # creates workspace
causal-edge discover <TICKER>         # runs Abel discovery
causal-edge run                       # executes strategies
causal-edge validate                  # validates and enforces quality gates
causal-edge status                    # progress summary
```

The CLI enforces validation, look-ahead checks, and result recording.
Your job: write the strategy implementation. The references have the method.

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
- Dashboard generation: each strategy's charts are independent
- Backfill: multiple strategies can backfill concurrently

**Sequential (dependent — compounding requires order):**
- Experiment loop: exp002 depends on exp001's result. Serial, not parallel.
- KEEP decision: validate THEN record. Cannot record before verdict.

**In practice:** use Agent tool to dispatch parallel research across assets. Within each asset, experiments are serial. `causal-edge` handles IO parallelism (discovery, dashboard) internally.

## References

| Need | Read |
|---|---|
| Experiment loop, explore/exploit, KEEP rule | `references/experiment-loop.md` |
| Discovery protocol, multihop, blanket | `references/discovery-protocol.md` |
| Look-ahead rules (8 constraints) | `references/constraints.md` |
| Feature patterns from 200+ experiments | `references/proven-patterns.md` |
| Why causal works (Pearl, DGP, axioms) | `references/methodology.md` |

**REQUIRED SKILL:** `causal-abel` for Abel API access (cap_probe.py, auth flow).

## Abel-Pro Mapping

- Abel-alpha worktree for the Abel-Pro integration: `D:\codes\causal-alpha\.tree\abel-pro`
- Abel-alpha branch for that worktree: `abel-pro`
- Paired Abel-edge worktree for validation and execution: `D:\codes\open_source\causal-edge\.tree\abel-pro-demo`
- Paired Abel-edge branch: `abel-pro-demo`
- Abel auth and data environment defaults to prod
