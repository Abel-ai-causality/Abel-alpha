# Experiment Loop

## Quick Start

```bash
causal-edge research init <TICKER>    # Abel discovery + workspace
# edit strategy.py
causal-edge research run -d "baseline"
# iterate...
```

`causal-edge research run` handles validation, K computation, results recording.
You only write strategy.py and decide WHAT to try next.

## The KEEP Rule

```
KEEP if: causal-edge verdict == "PASS" AND triangle improved vs baseline
DISCARD: everything else
```

Each KEEP updates the baseline. The next experiment compounds on it.

## Explore vs Exploit

4:1 ratio — every 5th experiment is explore. Force explore after 10 consecutive discards.

**Explore = genuinely new information:**
- New data source (volume, on-chain, open interest)
- New causal graph depth (3-hop via Abel multihop)
- New asset relationships (cross-asset spreads, sector peers)
- New ML architecture (different model class)

**NOT explore (exploit variants):**
- Removing features, disabling overlays, changing thresholds
- Switching GBDT depth or learning rate
- Adjusting position sizing params
- Swapping ML framework (XGB for GBDT) without new features

## Addressing Validation Failures

Fix through signal improvement, not metric manipulation.

| Failure | Means | Legitimate fix |
|---------|-------|---------------|
| T6 DSR low | K too high or signal weak | Scan fewer lags, use Abel-justified only |
| T7 PBO high | Parameter selection overfits | Fewer params, wider WF window, fix lags |
| T12 OOS/IS low | IS inflated | More conservative IS selection |
| T13 NegRoll high | Regime-fragile | Add regime detection, diversify components |
| T15 MaxDD | Drawdown risk | Better risk signal, vol-scaling (NOT position cap) |
| T15 Lo low | Serial correlation | Persistence penalty, RSI contrarian |
| T15 Omega low | Negative skew | Better entry/exit, NOT return clipping |

## When to Stop

- **20+ consecutive discards** AND **3+ genuine explore dimensions tried** is the minimum threshold, not an automatic stop.
- Declare honest failure only when that threshold is met **and** the last 5 rounds show no material validation improvement **and** no new high-quality discovery lead remains.
- Repeating the same failure signature across recent rounds is evidence of exhaustion. A branch that is still improving but not yet KEEP is not exhausted.
- An honest "no signal" is a valid outcome. Don't burn compute on noise.
- "Pareto frontier reached" after 6 experiments is NOT honest failure (too few).

## Compounding Protocol

Each KEEP updates the baseline. Pre-defining 100 experiments kills compounding.
Serial execution preserves compounding; grid search destroys it.

## Additional Protocols

- **Borderline** (improvement < 5%): run 3x, take median (filters random seed noise)
- **Regime check**: every KEEP must pass bull + bear + recent sub-periods
- **Combination**: every 3 KEEPs, try combining top-2 improvements
