# Discovery Protocol

## Purpose

Discovery answers one question only:

Which causal candidates are worth considering for this session?

It does not define the branch runtime by itself.

## Session Model

After live discovery, the session owns:

- `discovery.json`: candidate snapshot
- `readiness.json`: advisory coverage report

The branch then selects from that session context in `branch.yaml`.

## Default Selection Order

Use this as a priority order, not a hard formula:

1. direct parents
2. other Markov blanket nodes
3. children-derived hop-2 candidates
4. sector or market peers only when they add a real mechanism

## Branch Cut

When moving from session discovery into a branch:

- choose a small initial driver set
- write it explicitly into `branch.yaml`
- use readiness to understand coverage, not to auto-ban ideas
- run `prepare-branch` before a recorded round

## Readiness Role

Readiness is advisory.

Use it to answer:

- how early target data is observed
- which discovery tickers have partial or stronger coverage
- whether strict overlap is likely expensive

Do not use it to collapse every branch onto the latest common start unless the
branch really depends on strict overlap.

## Cache Role

Discovery does not own market data.

Prepared branch inputs should resolve through the edge-owned cache path, not
through ad hoc branch-local fetching conventions.
