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
    homepage: https://github.com/cauchyturing/causal-alpha
---

Causation survives regime change. Correlation doesn't.

```bash
causal-edge research init <TICKER>    # creates workspace + runs Abel discovery
# edit strategy.py → implement run_strategy()
causal-edge research run              # validates, records, enforces everything
causal-edge research status           # progress summary
```

The CLI enforces validation, K tracking, look-ahead checks, and result recording.
Your job: write strategy.py. The references have the method.

## Judgment Calls (only you can make these)

- **Explore vs exploit?** New data dimension = explore. Parameter tweak = exploit. Swapping ML framework = exploit. See `references/experiment-loop.md`.
- **Micro-cap parents look weird?** That's the signal. Causal info transmits from low-attention assets. Abel's graph is mostly micro-caps by design.
- **Validation failure?** It's your next research direction, not an obstacle. DSR low = K too high. MaxDD bad = drawdown signal weak. Don't hack metrics — fix the signal. See `references/experiment-loop.md#addressing-validation-failures`.
- **When to stop?** 20+ consecutive discards AND 3+ genuine explore dimensions tried = honest failure. Report it. Don't burn compute on noise.

## References

| Need | Read |
|---|---|
| Experiment loop, explore/exploit, KEEP rule | `references/experiment-loop.md` |
| Discovery protocol, multihop, blanket | `references/discovery-protocol.md` |
| Look-ahead rules (8 constraints) | `references/constraints.md` |
| Feature patterns from 200+ experiments | `references/proven-patterns.md` |
| Why causal works (Pearl, DGP, axioms) | `references/methodology.md` |

**REQUIRED SKILL:** `causal-abel` for Abel API access (cap_probe.py, auth flow).
