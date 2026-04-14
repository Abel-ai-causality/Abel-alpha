# causal-alpha

**Causal alpha discovery for AI agents. Three layers: code enforces, skill guides, agent discovers.**

```bash
pip install git+https://github.com/Abel-ai-causality/Abel-edge.git
causal-edge init my-portfolio
cd my-portfolio
causal-edge discover TSLA          # Abel discovery
causal-edge run                    # execute strategies
causal-edge validate               # validate and enforce quality gate
causal-edge status                 # progress summary
```

If that `git+https` install path fails in your network environment, use the same public repo via zip:

```bash
pip install https://github.com/Abel-ai-causality/Abel-edge/archive/refs/heads/main.zip
```

```mermaid
flowchart TD
    D["DISCOVER — Abel CAP parents + blanket"]
    B["BUILD — agent writes strategy.py"]
    V{"VALIDATE — causal-edge 13-test"}
    L["LEARN — compound on baseline"]

    D -->|"K honest"| B
    B -->|"no look-ahead"| V
    V -->|"PASS = KEEP"| L
    V -.->|"FAIL = DISCARD"| B
    L -->|"next cycle"| D
```

## Three-Layer Design

```
L1: Code enforce (LLM-agnostic)     → causal-edge CLI
    K auto-computed from strategy.py AST
    validate_strategy() runs every experiment
    KEEP requires PASS (code refuses otherwise)
    Look-ahead static check before execution

L2: Judgment guidance (skill text)   → SKILL.md (280 words)
    Explore vs exploit distinction
    Micro-cap parents = the signal
    Validation failures = research direction
    When to declare honest failure

L3: Agent autonomy (留白)            → strategy.py
    What architecture, what features, what ML
    Every asset is different
```

**L1 protects all models. L2 improves strong models. L3 is where alpha lives.**

## Why Causal

Correlation breaks when regimes change. Causation doesn't (Pearl, 1995).

- **K is small** — Abel gives ~10 justified parents vs ~10,000 blind scan → DSR honest
- **Signals persist** — causal links survive bull→bear transitions
- **Discovery is automated** — Abel CAP over 11K nodes, agent handles the rest

## Production Proof

| | Sharpe | Validation | Backtest |
|---|--------|------------|----------|
| Crypto A | 4.27 | 15/15 PASS | 1,400+ days |
| Crypto B | 2.82 | 15/15 PASS | 1,500+ days |
| Crypto C | 2.10 | 13/13 PASS | 1,100+ days |
| Equity A | 2.57 | 15/15 PASS | 1,000+ days |
| Equity B | 1.69 | 15/15 PASS | 1,200+ days |
| Crypto D | 2.06 | 13/13 PASS | 1,300+ days |

All DSR-deflated (honest K from Abel, not blind scan). All pass [causal-edge](https://github.com/Abel-ai-causality/Abel-edge) full validation. 200+ serial experiments across 6 assets. Zero loss years on best strategies.

Build your own: install `Abel-edge`, then run `causal-edge init <name>` and `causal-edge discover <TICKER>`.

## Abel-Pro Mapping

- Abel-alpha worktree for the Abel-Pro integration: `D:\codes\causal-alpha\.tree\abel-pro`
- Abel-alpha branch for that worktree: `abel-pro`
- Paired Abel-edge worktree for validation and execution: `D:\codes\open_source\causal-edge\.tree\abel-pro-demo`
- Paired Abel-edge branch: `abel-pro-demo`
- Abel auth and data environment defaults to prod

## Files

```
SKILL.md                  ← Agent reads this. 280 words. 4 judgment calls.
references/
  experiment-loop.md      ← KEEP rule, explore/exploit, when to stop
  discovery-protocol.md   ← Multihop, blanket, fallback
  constraints.md          ← Look-ahead rules (8 constraints)
  proven-patterns.md      ← Battle evidence for inspiration
  methodology.md          ← Axioms vs constraints
```

## The Ecosystem

```
Abel CAP       → causal graph (discovery)
causal-alpha   → research methodology (this skill)
causal-edge    → validation + enforcement (L1 code)
causal-abel    → Abel API access (cap_probe.py)
```

## License

MIT. Built by [Abel AI](https://github.com/Abel-ai-causality/).
