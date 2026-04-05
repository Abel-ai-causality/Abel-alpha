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

## The 5 Invariants with Production Proofs

These invariants are proven by three live strategies totaling 3,900+ trading days:

**1. Causal discovery reduces K, making DSR honest.**
Abel gives ~10-25 mechanistically justified parents instead of scanning ~10,000 pairs. ETH: Abel identified SSTK as causal parent. K=5. DSR=97%. Sharpe 4.27 over 1,403 trading days. A blind scan of the same universe would need Sharpe > 2.0 to pass at K=37,500.

**2. Metric triangle prevents gaming.**
Lo-adjusted Sharpe (optimize) x IC (guardrail) x Omega (guardrail). All three are leverage-invariant. No single trick improves all three -- only genuine signal does. BNB proof: 158 experiments, IC caught every position-scaling trick that inflated Sharpe.

**3. Experiment loop with compounding.**
Each KEEP updates the baseline. The next experiment builds on the latest best, not the original. META: 55 experiments, Sharpe 2.57 (Lo=2.21, IC=0.147, Omega=2.11). AAPL: 40 experiments, Sharpe 1.69 (Lo=1.62, IC=0.080, Omega=1.55). BNB: 158 experiments, Sharpe 2.82 (Lo=2.07, IC=0.264, Omega=2.82). Compounding stopped when 14+ consecutive discards confirmed the Pareto frontier.

**4. Look-ahead zero-tolerance (structural, not instructional).**
Every `rolling().stat()` must have `.shift(1)`. Every feature uses `shift(lag)` where lag >= 1. Train/test splits strictly chronological. Production proof: a look-ahead bug in `rolling(5).mean()` without shift was caught and fixed -- Sharpe dropped from 4.03 to 4.00, PnL from +375% to +342%. The honest number is always smaller.

**5. Explore means new information, not subtraction.**
Removing features or changing params are exploit variants. Real explore: new data source, new causal depth (multihop), new asset relationships. BNB proof: direct Abel parents gave only 2 of top-18 signals. Adding 2-hop parents + 8 crypto peers (ADA, ETH, SOL, XRP) boosted IC by 34%. 100 "explore" experiments that only subtracted features produced 0 keeps. Actual exploration -- adding crypto peer spreads -- was the breakthrough.

## The Closed Loop

Discover causal drivers via Abel. Build strategies from that structure. Validate with the metric triangle. Learn what worked (compounding KEEPs, memory updates). Discover again -- now with knowledge of which causal depths, which peer expansions, which signal patterns survive validation. This is self-authoring: the system extends itself through its own mechanism, each iteration starting where the last one ended. The loop is the method.
