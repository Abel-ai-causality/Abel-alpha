# Experiment Loop Protocol

## Cold-Start Sequence

Zero-knowledge user says "research SOL." Agent goes from nothing to first experiment in under 5 minutes. Five steps, fully autonomous.

### Step 1: Get Abel Key

Check for `ABEL_API_KEY` in environment, then `<skill-root>/.env.skill`, then shared `causal-abel` skill `.env.skill`. If missing, run the agent OAuth flow (one click from user):

```
GET https://api.abel.ai/echo/web/credentials/oauth/google/authorize/agent
Show user data.authUrl → they approve in browser
Poll data.resultUrl → get data.apiKey
Store to .env.skill as ABEL_API_KEY=<key>
```

Or: user sets `ABEL_API_KEY` env var directly, or gets a key at https://abel.ai/skill

### Step 2: Discover Parents

Read Abel CAP capability card (`cap.abel.ai/.well-known/cap.json`) to find current API verbs. Query for causal parents of target asset. Run multihop expansion: 2-hop and 3-hop parents, sector peers. Direct parents are often not the strongest -- BNB had only 2 of its top-18 signals from direct parents. Multihop + peers almost always outperform.

Output: `parent_tickers` -- list of ticker + lag pairs, with K accounting for DSR.

### Step 3: Fetch Price Data

Auth budget: ZERO additional clicks. yfinance is default (free, no key). FMP API if `FMP_API_KEY` available (upgrade path).

```python
import yfinance as yf
data = yf.download(["SOL-USD"] + parent_tickers, period="5y")["Close"]
```

Crypto = calendar days, equity = trading days. Forward-fill equity to align. Track staleness. Never ask "where is your data?" -- just fetch it.

### Step 4: Bootstrap Harness

```
pip install causal-edge    # required for validation
Create: strategy.py, evaluate.py, results.tsv, memory.md
```

`evaluate.py` contract (immutable -- agent never modifies):
1. Load prices
2. Static look-ahead check via `causal_edge`
3. Run `strategy.run_strategy(data)` -> `(pnl, dates, positions)`
4. Validate via `causal_edge.validation.gate.validate_strategy(csv)`
5. Print grep-friendly: `lo_adjusted / ic / omega / sharpe / validation`

### Step 5: First Experiment

Agent writes `strategy.py` from scratch using discovered parents. Runs `evaluate.py` -> first metrics. Records baseline in `results.tsv`. Reports to user:

> "Found N parents (K=M including multihop). First backtest: Sharpe X.XX. Starting loop."

**An agent that asks "where is your data?" has failed. Auth budget: ONE click.**

## Setup for Existing Projects

If data and harness already exist, skip cold-start. Verify `evaluate.py` uses `causal-edge` for validation and prints grep-friendly metrics. Read `results.tsv` and `memory.md` to resume from latest baseline. Start the loop at the last KEEP.

## 7-Step Experiment Lifecycle

Each iteration of the loop follows exactly 7 steps:

1. **Idea** -- read `memory.md`. Choose explore or exploit based on balance ratio.
2. **Implement** -- modify `strategy.py` with one clear, isolated change.
3. **Commit** -- `git commit` BEFORE running. Persist before crash. Every experiment has a recoverable commit.
4. **Run** -- `python evaluate.py` -> metrics to stdout.
5. **Validate** -- apply metric triangle: Lo-adjusted Sharpe IMPROVED, AND IC >= baseline, AND Omega >= baseline, AND validation PASS. Everything else -> DISCARD.
6. **Record** -- append to `results.tsv` (KEEP or DISCARD, with all metrics).
7. **Memory** -- every 10 experiments, analyze `results.tsv` patterns and update `memory.md`.

One change per experiment. This is non-negotiable -- multi-change experiments make attribution impossible.

## Compounding Protocol

**Each KEEP updates the baseline. The next experiment builds on the latest best.**

```
baseline:       w_lag=0.50, xcorr=1.25
exp001 KEEP:    w_lag=0.40 → best becomes w_lag=0.40, xcorr=1.25
exp002 KEEP:    xcorr=1.30 → best becomes w_lag=0.40, xcorr=1.30
exp003 exploits from (w_lag=0.40, xcorr=1.30), NOT from original baseline
```

Pre-defining 100 experiments at start kills compounding. The agent cannot know what exp003 should be until exp002's result is known. Serial execution preserves compounding; grid search destroys it.

BNB proof: 158 serial experiments -> Sharpe 2.82. A grid search over the same parameter space would find a lower optimum because improvements cannot compound across independent runs.

## Explore/Exploit Balance

4:1 ratio -- every 5th experiment is explore. Force explore after 10 consecutive discards.

**EXPLORE = new information the strategy did not have before:**
- New data source (volume, open interest, on-chain metrics)
- New causal graph depth (3-hop parents via Abel multihop)
- New asset relationships (cross-asset spreads, sector peer momentum)
- New ML architecture (different model class, not just param changes)
- New feature engineering (interaction terms, regime indicators)

**NOT explore (these are exploit variants):**
- Removing features, disabling overlays, changing thresholds
- Switching GBDT depth or learning rate
- Adjusting position sizing params

BNB proof: 16 "explore" experiments that only removed features -> 0 keeps. Real explore -- adding 8 crypto peer spreads (ADA, ETH, SOL, XRP) -- was the breakthrough that moved the Pareto frontier.

## Additional Protocols

- **Borderline**: improvement < 5% -> run 3x, take median (filters GBDT random seed noise).
- **Regime check**: every KEEP must pass bull / bear / recent sub-period Sharpes. An improvement that only works in one regime = DISCARD.
- **Combination**: every 3 KEEPs, try combining top-2 improvements as a single experiment.
- **Structured idea generation** (when stuck): re-read memory.md, analyze near-misses in results.tsv, query Abel for new parents, check cross-strategy transfer from other assets.
- **NEVER STOP**: run until interrupted. ~50 experiments/hour, ~600 overnight. The human reviews `results.tsv` and `memory.md` when they return.

## results.tsv Format

Tab-separated, 9 columns. Append-only, git-committed after each experiment.

```
commit	lo_adj	ic	omega	sharpe	pnl	status	mode	description
baseline	2.23	0.383	2.50	3.97	342.1	keep	-	initial strategy from discovered parents
exp001	2.19	0.381	2.48	3.83	339.5	discard	exploit	pos_threshold=0.15
exp002	2.31	0.390	2.55	4.05	345.2	keep	exploit	added xcorr feature lag-14
exp003	2.25	0.385	2.52	3.95	340.0	discard	explore	random forest instead of GBDT
```

## memory.md Template

```markdown
# Agent Memory

## Exhausted Directions (don't retry)
- pos_threshold sweep: 0.15/0.20/0.25 all tested, 0.20 optimal
- SMA window: 30/40/50/75 all tested, 50 optimal
- Return clipping: games metrics, never real improvement

## Promising Near-Misses
- exp #12: cross-correlation feature, Lo +0.03 but IC -0.005 (within noise?)
- exp #23: multi-horizon weights 40/35/25 vs 50/30/20

## Combinations to Try
- [pending]

## Ideas Not Yet Tried
- Abel 3-hop parents for new signal depth
- Regime-conditional position sizing
- Parent sector momentum spread
- Volume-based features (not yet fetched)

## Patterns
- Signal engineering changes tend to improve IC
- Sizing changes tend to improve Sharpe but not IC
- Filter changes improve MaxDD but lower Sharpe
```
