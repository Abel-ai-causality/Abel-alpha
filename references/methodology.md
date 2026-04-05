# Methodology: Why Causal Discovery Is the Only Correct Way to Find Alpha

## The First Principle

**Correlation is a property of data. Causation is a property of the data generating process (DGP).**

This single distinction determines everything:

```
When regime changes:
  Data changes   -> correlations break   -> correlation signals die
  DGP persists   -> causal links survive -> causal signals live
```

Live trading always encounters regime changes (crises, policy shifts, structural breaks).
Therefore only causal signals are guaranteed to persist in live trading.

This follows directly from Pearl's definition of causation (1995):
**A causal relationship is one that remains invariant under intervention.**
Regime change is intervention on the market DGP. Only causal relationships survive.

## Three Dimensions of Proof

### Mathematical (Pearl do-calculus)

Correlation: `corr(X,Y) = f(joint distribution of X,Y)`. When the distribution shifts, correlation shifts. It is **conditional** on the current regime.

Causation: `X -> Y` means `do(X=x)` changes Y's distribution. This is **structural** -- it does not depend on the marginal distributions of X and Y.

Therefore: correlation is regime-conditional, causation is regime-invariant.

### Quantitative Finance

Three properties that directly translate to higher live Sharpe:

- **Persistence**: Causal signal half-life >> correlation signal half-life. Correlations reset at every regime shift. Causal links do not reset.
- **Crowding**: Causal discovery requires PCMCI / Abel (hard, specialized). Correlation scanning requires a for-loop (easy, everyone does it). Causal signals are uncrowded, not arbitraged, alpha lasts longer.
- **Stability**: Causal direction is structural (SSTK is always a parent of ETH, never reverses). Correlation can flip sign between regimes.

### AI Theory (OOD Generalization)

ML finds patterns: `f(X) -> Y`. But `f` is learned from training data. Training data != future data. ML breaks on distribution shift.

Causal ML constrains `f` to only use causal parents as inputs. This constraint guarantees that `f` remains valid under distribution shift (because causal parent effects are structural, not distributional). This is the **only known theoretical guarantee** for out-of-distribution generalization in AI.

## The Derivation Chain

```
Causation = DGP invariant (Pearl's definition)
  |
Live trading = guaranteed regime changes
  |
Only DGP invariants survive regime changes
  |
Only causal signals survive live trading
  |
Higher OOS persistence -> higher live Sharpe
  |
Causal structure constrains search space (K small)
  |
Small K -> DSR passes honestly
  |
Discoveries are real, not noise
```

K being small is a CONSEQUENCE, not the cause. The cause is regime invariance -- causal relationships are the only ones worth finding, because they are the only ones that will still be there when you trade.

## The K/DSR Consequence

Once you accept that only causal signals are worth finding, K drops automatically:

```
Blind scan:   K = 500 tickers x 25 lags x 3 windows = 37,500
              E[max(SR)] ~ 1.48 -> need Sharpe > 2.0 to pass DSR at 95%

Causal scan:  K = 1 parent x 5 lag variants = 5
              E[max(SR)] ~ 0.57 -> need Sharpe > 1.0 to pass DSR at 95%
```

Same signal with Sharpe 1.8:
- Blind: DSR = 41% -- "probably noise"
- Causal: DSR = 97% -- "almost certainly real"

K is small not because you searched less. K is small because you only searched for what can survive. What can survive = causal links = regime-invariant relationships. The honest search space is the causal search space.

## Axioms and Constraints — with Production Proofs

**Axioms** follow from math. They cannot be wrong.

**A1. Causal K < blind K → DSR honest.**
Abel gives ~10-25 mechanistically justified parents instead of scanning ~10,000 pairs. ETH: Abel identified SSTK as causal parent. K=5. DSR=97%. Sharpe 4.27 over 1,403 trading days. A blind scan of the same universe would need Sharpe > 2.0 to pass at K=37,500. This follows from Pearl + the DSR formula — not heuristic.

**A2. Look-ahead = invalid backtest.**
Definitional. Future data in features means the backtest is lying. Production proof: `rolling(5).mean()` without `.shift(1)` was caught — Sharpe dropped 4.03 → 4.00, PnL +375% → +342%. The honest number is always smaller.

**Constraints** are derived from 200+ experiments. Strong, theory-grounded, but questionable with evidence.

**C1. Multi-dimensional validation > single metric.**
Currently: Lo-adjusted Sharpe × IC × Omega. Three orthogonal, leverage-invariant spaces (ratio, rank, distribution shape). No known transformation improves all three except genuine signal. But the specific three metrics could evolve — the PRINCIPLE is permanent, the implementation is our current best. causal-edge owns the definition and computation.

Why these three work — the 38-experiment proof:

| Xcorr Scale | Lo-adj | IC | Sharpe | Verdict |
|-------------|--------|----|--------|---------|
| 1.25 / 0.75 | 2.302 | 0.441 | 4.218 | Baseline |
| 1.50 / 0.50 | 2.353 | 0.549 | 4.387 | Improving |
| **1.75 / 0.25** | **2.367** | **0.569** | **4.414** | **Optimal** |
| 2.00 / 0.00 | 2.375 | **0.403 ↓** | 4.425 | **IC crashed — triangle caught it** |

At 2.0/0.0, Lo and Sharpe still rose but IC collapsed 29%. This is concentration gaming (zeroing out low-correlation positions). Single-metric validation would have KEPT this. The triangle caught it.

**C2. Serial compounding > pre-defined grid.**
Each KEEP updates baseline. BNB: 158 serial → Sharpe 2.82. META: 55 experiments → 2.57. AAPL: 40 → 1.69. Compounding stopped when 14+ consecutive discards confirmed Pareto. Could theoretically fail on non-convex frontiers — hasn't in 200+ experiments.

**C3. Explore = genuinely new information.**
Removing features or changing params = exploit variant. Real explore: new data source, new causal depth, new relationships. BNB: 100 "explore" that subtracted → 0 keeps. Adding 8 crypto peers → IC +34%. Strong heuristic — an edge case where removing noise IS the right move could exist.

## The Closed Loop

Discover causal drivers via Abel. Build strategies from that structure. Validate with the metric triangle. Learn what worked (compounding KEEPs, memory updates). Discover again -- now with knowledge of which causal depths, which peer expansions, which signal patterns survive validation. This is self-authoring: the system extends itself through its own mechanism, each iteration starting where the last one ended. The loop is the method.
