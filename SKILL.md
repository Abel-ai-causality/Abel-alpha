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

## The 5 Invariants

1. **Causal discovery reduces K, making DSR honest.** Abel gives ~10 mechanistically justified parents instead of scanning ~10,000 pairs. Fewer trials = discoveries that survive deflation.

2. **Metric triangle prevents gaming.** Lo-adjusted Sharpe (optimize) x IC (guardrail) x Omega (guardrail). All three are leverage-invariant. No single trick improves all three — only genuine signal does.

3. **Experiment loop with compounding.** Each KEEP updates the baseline. The next experiment builds on the latest best, not the original. Improvements accumulate; pre-defining all experiments kills compounding.

4. **Look-ahead zero-tolerance (structural, not instructional).** Every `rolling().stat()` must have `.shift(1)`. Every feature uses `shift(lag)` where lag >= 1. Train/test splits strictly chronological. Violations = auto-FAIL, no exceptions.

5. **Explore means new information, not subtraction.** Removing features, disabling overlays, or changing params are exploit variants. Real explore: new data source, new causal depth (3-hop), new asset relationships, new ML architecture. BNB proof: 100 "explore" experiments that only subtracted features produced 0 keeps.

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

## Invariants and Constraints (Machine-Readable)

```
INVARIANT: All discoveries validated by metric triangle.
INVARIANT: K tracked for DSR honesty.
INVARIANT: Each KEEP compounds on latest baseline.
INVARIANT: Look-ahead violations = auto-FAIL.
INVARIANT: Explore = new information, not parameter tweaks.

CONSTRAINT: strategy.py exports run_strategy(data) -> (pnl, dates, positions).
CONSTRAINT: evaluate.py immutable — agent modifies only strategy.py.
CONSTRAINT: results.tsv append-only, git-committed after each experiment.
CONSTRAINT: memory.md updated every 10 experiments.
CONSTRAINT: pip install causal-edge required for validation.
```

## When to Read References

| You need... | Read | Why |
|---|---|---|
| The full causal argument (Pearl, DGP, regime invariance) | `references/methodology.md` | First-principles foundation |
| Step-by-step Abel CAP discovery protocol | `references/discovery-protocol.md` | Exact API call sequence, multihop expansion, K accounting |
| Autonomous experiment loop mechanics | `references/experiment-loop.md` | KEEP/DISCARD rules, compounding, explore/exploit, memory system |
| Look-ahead rules and structural constraints | `references/constraints.md` | shift/rolling rules, train/test splits, auto-FAIL conditions |
| Metric triangle deep dive | `references/metric-triangle.md` | Why Lo x IC x Omega, how each trick gets caught, leverage invariance |
| Feature patterns that survived 150+ experiments | `references/proven-patterns.md` | Dual-lag xcorr, binary thresholds, persistence penalty, RSI overlay |

SKILL.md gives you capability. References give you depth. Start here, go there when you need to.
