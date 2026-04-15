# Discovery Protocol

## Quick Start

```bash
python scripts/research_narrative.py init-session --ticker <TICKER> --exp-id <exp-id>
# → research/<ticker>/<exp_id>/discovery.json created for Abel-alpha organization
```

## The Multihop Protocol

Direct Abel parents are often not the best predictors. Multihop consistently outperforms.

```
Direct parents:    Abel says X → TARGET
Markov blanket:    co-parents, spouses (graph.markov_blanket)
Hop-2 parents:     X → CHILD → TARGET (via children's parents)
Sector peers:      same industry as direct parents, liquid
Crypto peers:      for crypto targets, check paths from BTC/ETH/BNB/etc.
```

Production proof:
- AAPL: 5 direct → 25 multihop → Sharpe 1.69, 15/15 PASS
- BNB: 10 direct, only 2 in final top-18. +6 hop-2 + 7 sector peers → IC +34%
- TON: 4 of top 7 from Markov blanket, not direct parents

**Rule: every new asset starts with parents + blanket + multihop. Decide architecture after.**

## 5-Step Core

1. **Parents** — `graph.neighbors(node, scope=parents)`
2. **Blanket** — `extensions.abel.markov_blanket(node)` — includes co-parents
3. **Children** — `graph.neighbors(node, scope=children)` — for hop-2 expansion
4. **Multihop** — for each child ≠ target, get its parents. Add novel ones as hop-2
5. **Crypto peers** — for crypto targets, check `graph.paths` from major crypto assets

K is auto-computed by `causal-edge evaluate` from strategy.py source.
You don't need to track K manually.

Discovery belongs to the exploration session first, not to only one branch file. Use the
session README to explain how discovery led to one or more candidate branches, then keep the
branch-specific thesis and rounds inside each `branches/<branch-id>/` directory.

## Enrichment

- **Verify paths** — confirm causal transmission for top candidates
- **Sector peers** — 2-3 same-sector liquid equities per direct parent
- **Crypto peers** — asset-dependent. BNB: +8 crypto peers was #1 breakthrough. TON: crypto peers all failed OOS. Test, don't assume.

## Selection

Rank candidates by `data_availability × causal_proximity`:
- `data_availability`: 1.0 daily, 0.5 weekly, 0 unavailable
- `causal_proximity`: 1/hop_depth (direct=1.0, hop-2=0.5, hop-3=0.33)
- `blanket_bonus`: +0.3 for Markov blanket nodes

Select top 15-25 for equities, 15-20 for crypto.

## Fallback Without Abel

If no API key: sector heuristics — liquid sector peers + market factors.
Higher K, lower quality, but the experiment loop still works.
SOL had zero Abel coverage; fallback crypto peer voting still produced Sharpe 2.06 (13/13 PASS).

## Caching

Cache parent lists to disk. Abel's graph is structurally stable (DGP, not transient).
Refresh quarterly, not daily.
