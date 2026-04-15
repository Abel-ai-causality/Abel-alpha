# Experiment Loop

## Quick Start

```bash
python scripts/research_narrative.py init-session --ticker <TICKER> --exp-id <exp-id>
python scripts/research_narrative.py init-branch --session research/<ticker>/<exp_id> --branch-id graph-v1
# edit research/<ticker>/<exp_id>/branches/graph-v1/strategy.py
python scripts/research_narrative.py run-branch --branch research/<ticker>/<exp_id>/branches/graph-v1 -d "baseline"
# iterate...
```

`causal-edge evaluate` handles raw validation facts. `Abel-alpha` handles keep/discard,
round recording, and session/branch summaries. You only write strategy.py and decide WHAT to try next.

## Session Structure

1. One exploration session lives at `research/<ticker>/<exp_id>/`.
2. One session can branch into multiple candidate branches under `branches/<branch-id>/`.
3. One `run-branch` call equals one recorded round and stores raw edge facts plus alpha-owned narrative records.
4. The session also appends `events.tsv` so branch creation and round execution stay traceable.
5. `Abel-alpha check --strict` verifies narrative completeness.

## The KEEP Rule

```
KEEP if: causal-edge verdict == "PASS" AND key baseline metrics improve vs latest KEEP baseline
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

- **20+ consecutive discards** AND **3+ genuine explore dimensions tried** = honest failure.
- An honest "no signal" is a valid outcome. Don't burn compute on noise.
- "Pareto frontier reached" after 6 experiments is NOT honest failure (too few).

## Compounding Protocol

Each KEEP updates the baseline. Pre-defining 100 experiments kills compounding.
Serial execution preserves compounding; grid search destroys it.

## Additional Protocols

- **Borderline** (improvement < 5%): run 3x, take median (filters random seed noise)
- **Regime check**: every KEEP must pass bull + bear + recent sub-periods
- **Combination**: every 3 KEEPs, try combining top-2 improvements
