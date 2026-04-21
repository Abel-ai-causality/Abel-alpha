# Branch Authoring

Use this reference after the workspace is ready and you are moving from
workspace setup into session and branch work.

## Branch Model

- `discovery.json` is only the session candidate snapshot
- `readiness.json` is only the session coverage/advisory report
- `branch.yaml` defines the branch runtime intent
- `prepare-branch` resolves inputs and warms edge cache before a recorded round
- `run-branch` should consume prepared branch inputs, not invent them at runtime
- session `backtest_start` is the default research target; `branch.yaml.requested_start` may override it explicitly

Discovery gives leads, not answers. Readiness gives coverage clues, not
permission. A branch is where the research becomes a falsifiable bet.

## What To Do

- state a branch thesis clearly
- write `engine.py`
- prepare the branch inputs
- interpret the result honestly
- decide the next branch move

Alpha owns the bookkeeping so the branch can focus on mechanism, not file
management theater.

## Writing `engine.py`

- prefer injected `self.context`
- prefer explicit branch inputs over discovery-side inference
- use `self.research_target_ticker()` and `self.research_requested_start()`
- do not parse relative workspace files manually unless the context is missing

## Readiness

Keep readiness advisory:

- use it to understand coverage
- do not treat it as a hard permission system
- do not force all drivers to share the latest common start unless the branch thesis truly requires strict overlap
- do not confuse session start guidance with the branch's explicit requested start

## Research Judgment

- start causal-first; correlation-derived signals may help, but do not replace Abel discovery as the main search prior
- explore means new information, a new transmission path, or a genuinely different mechanism
- weird low-attention parents are not automatically noise; explain them before discarding them
- treat validation failure as direction, not as a prompt to hack metrics
- serial compounding beats pre-declaring a large experiment grid
- stop honestly when recent rounds are no longer improving and no high-quality new direction remains
