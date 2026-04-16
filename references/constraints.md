# Look-Ahead Constraints (Zero Tolerance)

These are STRUCTURAL constraints. They are not a checklist to run at the end —
they constrain every line of code the agent writes. A violation at ANY point
is an automatic FAIL, zero tolerance. The harness detects violations at two layers
(static + runtime), but the agent must internalize these rules to avoid writing
violations in the first place.

Any strategy code that uses future information is an automatic DISCARD,
regardless of how much Sharpe improves. These rules are non-negotiable.

## Feature Engineering Rules

1. **All features must use `shift(lag)` where lag >= 1**
   - `sstk_ret.shift(14)` ✓
   - `sstk_ret` (no shift) ✗

2. **`rolling().stat()` must be followed by `.shift(1)`**
   - `ret.rolling(5).mean().shift(1)` ✓
   - `ret.rolling(5).mean()` ✗ (includes today's value)

3. **No global statistics on full series**
   - `np.std(pnl[:i])` ✓ (expanding up to i)
   - `np.std(pnl)` ✗ (uses future data)

4. **Walk-forward slicing: `[:i]` only**
   - `s2_pos_arr[:i]` ✓
   - `s2_pos_arr[:i+1]` ✗ (includes current day)

5. **Normalize datetime semantics before aligning external series**
   - If strategy dates are UTC-aware, normalize auxiliary series to the same semantics before `reindex(...)`
   - Do not mix naive and UTC-aware indexes in date comparisons or alignment steps

## Trend Filter Rules

6. **Use yesterday's price and MA for today's decision**
   - `if eth_prices[i-1] < ma_vals[i-1]: pos[i] = 0` ✓
   - `if eth_prices[i] < ma_vals[i]: pos[i] = 0` ✗

## Position Sizing Rules

7. **Vol-targeting must use shifted rolling vol**
   - `rolling_vol.shift(1)` ✓
   - `rolling_vol` (includes today's vol) ✗

8. **Strategy output must satisfy `abs(position) <= 1`**
   - `np.clip(position, -1.0, 1.0)` ✓
   - `position = 1.4 * base_signal` without a final cap ✗
   - This is a structural leverage constraint on the final position series, not a suggestion.

## Target Variable Rules

9. **Only `shift(-1)` or `shift(-H)` for targets (predicting future)**
   - `(ret.shift(-1) > 0)` ✓ for H=1 target
   - These are prediction targets, not features

## Automated Detection

`evaluate.py` runs `check_look_ahead()` on `strategy.py` before execution.
Common patterns are caught automatically. But this is not exhaustive —
you must also manually verify any new feature engineering is lag-safe.

## Component PnL is Dangerous (Rule 10)

10. **Never use same-day component PnL as a signal**
   - `comp_pnls["S2"][T] = s2_pos[T] × eth_ret[T]` — contains TODAY's return
   - `sign(comp_pnls["S2"][T])` leaks today's return direction
   - Fix: use `np.roll(comp_pnl, 1)` to shift by 1 day, or use component POSITIONS instead
   - Caught 2026-03-29 by runtime look-ahead detection (autoresearch exp007)

## Two-Layer Detection

**Layer 1: Static analysis** (`check_look_ahead`)
- Scans strategy.py source code for regex patterns
- Catches: missing .shift(), np.std on full array, same-day price vs MA
- BLIND SPOT: cannot detect look-ahead hidden in pre-computed arrays

**Layer 2: Runtime analysis** (`check_look_ahead_runtime`)
- Tests empirical correlations after strategy runs
- Catches: position magnitude corr with same-day return, implausible hit rate
- Fills the blind spot of static analysis

Both must pass. Static catches code-level leaks. Runtime catches data-level leaks.

## Common Traps (from project history)

- `ford_5d = ford_ret.rolling(5).mean()` — missing `.shift(1)`, caught 2026-03-14
- `np.std(full_pnl_series)` for vol normalization — uses future
- CCA computed on full sample instead of expanding window
- DOW caps optimized on full sample instead of walk-forward
- `sign(comp_pnl[T])` contains today's return direction — caught 2026-03-29
