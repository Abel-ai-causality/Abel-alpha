---
name: causal-alpha
version: 1.0.0
description: >
  Causal alpha discovery + autonomous research. Discovers what causally drives
  any asset via Abel CAP, then runs autonomous experiment loops with anti-gaming
  metric triangle. Method, not template — constraints enable emergence.
  Complements causal-edge (validation framework).
  Use when: user wants to find alpha, discover drivers, research a new asset,
  run autoresearch, or asks "what drives X?" / "find signals for X".
metadata:
  openclaw:
    requires:
      bins: [python]
    optionalEnv: [ABEL_API_KEY]
    homepage: https://github.com/Abel-ai-causality/Abel-skills
---

## Philosophy

Causation is the only edge that survives regime change. Correlation is a property of data; causation is a property of the data generating process — and the DGP persists when markets shift. This skill closes the loop: **discover** causal drivers via Abel CAP, **build** strategies from causal structure, **validate** with the metric triangle, **learn** what worked, and **discover** again. The loop compounds. Each iteration starts where the last one ended.

## Mode Dispatch

| User says | Mode | What happens | Read reference |
|---|---|---|---|
| "what drives X?" | **discover** | Query Abel CAP for causal parents/children, report structure | `references/discovery-protocol.md` |
| "research X" / "find alpha" / "autoresearch" | **research** | Autonomous experiment loop with KEEP/DISCARD | `references/experiment-loop.md` |
| "show results" / "what worked?" | **report** | Read `results.tsv` + `memory.md`, summarize | (direct file reads) |

## Axioms and Constraints

**Axioms** are derived from math. They cannot be wrong. Never question them.

1. **Causal K < blind K → DSR honest.** Follows from Pearl's definition of causation + the DSR formula. Abel gives ~10 mechanistically justified parents vs ~10,000 blind scan pairs. Same signal at Sharpe 1.8: DSR 97% (causal) vs 41% (blind).

2. **Look-ahead = invalid backtest.** Definitional. Future data in features = the backtest is lying. Every `rolling().stat()` must have `.shift(1)`. Violations = auto-FAIL, zero tolerance, no exceptions.

**Constraints** are derived from 200+ experiments across 6 assets. They are our current best — strong, grounded in theory, but an agent should understand WHY they exist (read `references/methodology.md`) and can question them with evidence.

3. **Multi-dimensional validation > single metric.** Currently: Lo-adjusted Sharpe × IC × Omega (three orthogonal, leverage-invariant dimensions). The SPECIFIC three could evolve. The PRINCIPLE that no single metric suffices is permanent. causal-edge defines + computes the triangle — this skill applies it.

4. **Serial compounding > pre-defined grid.** Each KEEP updates baseline. Next experiment builds on latest best. Could theoretically fail on non-convex Pareto frontiers — but in 200+ experiments across 6 assets, it hasn't. BNB proof: 158 serial → Sharpe 2.82; grid search of same space → noise.

5. **Explore = genuinely new information.** Removing features or changing params = exploit variant. Real explore: new data source, new causal depth, new asset relationships, new ML architecture. BNB proof: 100 "explore" that only subtracted → 0 keeps. Strong heuristic, not physics — an edge case where removing noise IS the right move could exist.

## Abel CAP — Causal Discovery Engine

Abel CAP gives agents causal inference capability over financial assets.

### Getting Started

- Docs: https://cap.abel.ai/docs/getting-started/
- Capability card (machine-readable, always current): https://cap.abel.ai/.well-known/cap.json
- **Read the capability card at runtime for available verbs. Do NOT hardcode endpoints** — the API iterates.

### Agent OAuth Flow

Auth budget: ONE user click. Check for key in order:

1. `ABEL_API_KEY` environment variable
2. `<skill-root>/.env.skill` file
3. Shared `causal-abel` skill `.env.skill`

If no key found:

1. `GET https://api.abel.ai/echo/web/credentials/oauth/google/authorize/agent`
2. Show the user `data.authUrl` (the Google auth link, not the API URL itself)
3. Wait for user to confirm they completed browser auth
4. Poll `GET data.resultUrl` until `data.status` = `authorized`, `failed`, or expired
5. Read `data.apiKey` from the authorized response
6. Store to `.env.skill` as `ABEL_API_KEY=<key>`

Or: set `ABEL_API_KEY` env var directly, or get a key at https://abel.ai/skill

### What Discovery Needs

Four capabilities (find the current verbs from `cap.json`):

| Capability | Purpose |
|---|---|
| Find parents | What causally DRIVES the target asset |
| Find children | What the target asset DRIVES (confirmation signals) |
| Verify paths | Check causal transmission between nodes |
| Screen connectivity | Validate multi-node causal structure |

### Node Format

All nodes use `<TICKER>.price` or `<TICKER>.volume` format. Bare tickers auto-normalize.

### Discovery Protocol (4-Step Core)

1. **Parents** — query Abel for causal parents of target asset
2. **Children** — query for downstream assets (used for signal confirmation)
3. **Multihop** — expand to 2-hop and 3-hop parents. Direct parents are often not the strongest signals; multihop + sector peers almost always outperform
4. **K accounting** — record total nodes tested. This K feeds DSR for honest significance

If the `causal-abel` skill is installed, use its `cap_probe.py` for API calls. Otherwise, read `cap.json` and call endpoints directly.

### Fallback Without Abel

If no API key and user declines auth: use sector heuristics (same-sector equities, correlated crypto pairs). Higher K, lower quality — but the experiment loop still works.

## Data Acquisition

Auth budget: ZERO (Abel OAuth is the only click). Everything else is free.

- **yfinance is DEFAULT** — free, no API key, zero setup, `pip install yfinance`
- **FMP API as upgrade** — if `FMP_API_KEY` available in env, use FMP for higher-quality data
- **Agent fetches autonomously.** Never ask "where is your data?" — just fetch it.
- **Calendar alignment**: crypto = every calendar day, equity = trading days only. Forward-fill equity prices to align with crypto calendar. Track staleness.

```python
import yfinance as yf
data = yf.download(["ETH-USD", "AAPL", "SSTK"], period="5y")["Close"]
```

## The Strategy Contract

```python
def run_strategy(data: dict) -> tuple[pd.Series, pd.DatetimeIndex, pd.Series]:
    """
    The ONE interface. Everything else is emergent.
    
    Args:
        data: dict of ticker -> DataFrame with at least 'close' column
    Returns:
        pnl: daily PnL series
        dates: corresponding dates
        positions: daily position series (0=flat, 1=long, fractional=partial)
    """
```

Agent modifies `strategy.py` only. `evaluate.py` is immutable — it runs the backtest and computes the metric triangle.

## The KEEP Rule

```
KEEP if:  Lo-adjusted Sharpe IMPROVED
          AND  IC >= baseline
          AND  Omega >= baseline
          AND  validation PASS (pip install causal-edge)

DISCARD:  everything else. No exceptions.
```

Each KEEP updates the baseline. The next experiment compounds on it.

Full KEEP report must include: triangle metrics + returns (Sharpe/Calmar/PF) + risk (MaxDD/VaR/CVaR/Hill) + distribution (skew/kurt) + robustness (DSR/PBO/OOS) + yearly breakdown.

## Machine-Readable Rules

```
AXIOM: Causal K < blind K → DSR honest. (Pearl + DSR formula. Cannot be wrong.)
AXIOM: Look-ahead = invalid backtest. (Definitional. Zero tolerance.)

CONSTRAINT: Multi-dimensional validation > single metric. (Currently Lo×IC×Omega via causal-edge.)
CONSTRAINT: Serial compounding > pre-defined grid. (KEEP updates baseline.)
CONSTRAINT: Explore = new information, not subtraction. (Questionable with evidence.)

PROTOCOL: strategy.py exports run_strategy(data) -> (pnl, dates, positions).
PROTOCOL: evaluate.py immutable — agent modifies only strategy.py.
PROTOCOL: results.tsv append-only, git-committed after each experiment.
PROTOCOL: memory.md updated every 10 experiments.
PROTOCOL: pip install causal-edge required for validation.
```

## When to Read References

| You need... | Read | Why |
|---|---|---|
| Why causal works (Pearl, DGP, axiom proofs, triangle rationale) | `references/methodology.md` | First-principles foundation + why 3 metrics |
| Abel CAP discovery protocol | `references/discovery-protocol.md` | Multihop, K accounting, caching, fallback |
| Experiment loop mechanics | `references/experiment-loop.md` | Cold-start, 7-step lifecycle, compounding, explore/exploit |
| Look-ahead rules | `references/constraints.md` | 8 rules, two-layer detection, common traps |
| Feature patterns that survived 200+ experiments | `references/proven-patterns.md` | Battle evidence for explore inspiration (NOT scaffold) |
| Metric triangle formulas + execution | `causal-edge` framework | `pip install causal-edge` — owns definition + validation |

**5 reference files + causal-edge.** SKILL.md gives capability. References give depth. causal-edge gives execution.
