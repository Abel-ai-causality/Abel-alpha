"""Abel-alpha research narrative layer.

Organizes exploration sessions, records experimental process, and renders narrative
summaries on top of raw causal-edge evaluation outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


EVENTS_HEADER = [
    "timestamp",
    "event",
    "branch_id",
    "round_id",
    "mode",
    "verdict",
    "decision",
    "description",
    "artifact_path",
]

RESULTS_HEADER = [
    "exp_id",
    "ticker",
    "branch_id",
    "round_id",
    "decision",
    "lo_adj",
    "ic",
    "omega",
    "sharpe",
    "max_dd",
    "pnl",
    "K",
    "score",
    "verdict",
    "mode",
    "description",
    "result_path",
    "report_path",
]

STRATEGY_TEMPLATE = '''"""Strategy for {ticker}. Fill in run_strategy()."""

import numpy as np
import pandas as pd


def run_strategy():
    raise NotImplementedError("Fill in run_strategy()")
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Abel-alpha narrative layer")
    sub = parser.add_subparsers(dest="command", required=True)

    init_session = sub.add_parser("init-session", help="Create a narrative session")
    init_session.add_argument("--ticker", required=True)
    init_session.add_argument("--exp-id", required=True)
    init_session.add_argument("--root", default="research")

    init_branch = sub.add_parser("init-branch", help="Create a branch under a session")
    init_branch.add_argument("--session", required=True)
    init_branch.add_argument("--branch-id", required=True)

    run_branch = sub.add_parser(
        "run-branch", help="Run edge evaluate and record a branch round"
    )
    run_branch.add_argument("--branch", required=True)
    run_branch.add_argument("--mode", default="explore", choices=["explore", "exploit"])
    run_branch.add_argument("-d", "--description", required=True)
    run_branch.add_argument("--input-note", default="")
    run_branch.add_argument("--hypothesis", default="")
    run_branch.add_argument("--expected-signal", default="")
    run_branch.add_argument("--summary", default="")
    run_branch.add_argument("--next-step", default="")
    run_branch.add_argument("--action", action="append", default=[])
    run_branch.add_argument("--python-bin", default=sys.executable)

    render = sub.add_parser("render", help="Render summaries for a session")
    render.add_argument("--session", required=True)

    status = sub.add_parser("status", help="Print session status")
    status.add_argument("--session", required=True)

    check = sub.add_parser("check", help="Check narrative completeness")
    check.add_argument("--session", required=True)
    check.add_argument("--strict", action="store_true")

    args = parser.parse_args()

    if args.command == "init-session":
        init_session_dir(args.ticker, args.exp_id, Path(args.root))
        return 0
    if args.command == "init-branch":
        init_branch_dir(Path(args.session), args.branch_id)
        return 0
    if args.command == "run-branch":
        return run_branch_round(args)
    if args.command == "render":
        render_session(Path(args.session))
        return 0
    if args.command == "status":
        print_status(Path(args.session))
        return 0
    if args.command == "check":
        return check_session(Path(args.session), strict=args.strict)
    return 1


def init_session_dir(ticker: str, exp_id: str, root: Path) -> Path:
    session = root / ticker.lower() / exp_id
    session.mkdir(parents=True, exist_ok=True)
    with SessionLock(session):
        write_tsv_header(session / "events.tsv", EVENTS_HEADER)
        discovery_path = session / "discovery.json"
        if not discovery_path.exists():
            discovery_path.write_text(
                json.dumps(
                    {
                        "ticker": ticker.upper(),
                        "source": "pending",
                        "parents": [],
                        "blanket_new": [],
                        "children": [],
                        "K_discovery": 0,
                        "created_at": _now(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "session_created",
                "branch_id": "",
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": "Initialized Abel-alpha narrative session",
                "artifact_path": "",
            },
        )
        render_session(session)
    return session


def init_branch_dir(session: Path, branch_id: str) -> Path:
    with SessionLock(session):
        discovery = load_discovery(session)
        branch = session / "branches" / branch_id
        branch.mkdir(parents=True, exist_ok=True)
        (branch / "rounds").mkdir(parents=True, exist_ok=True)
        (branch / "outputs").mkdir(parents=True, exist_ok=True)
        write_tsv_header(branch / "results.tsv", RESULTS_HEADER)
        strategy = branch / "strategy.py"
        if not strategy.exists():
            strategy.write_text(
                STRATEGY_TEMPLATE.format(
                    ticker=discovery.get("ticker", session.parent.name.upper())
                ),
                encoding="utf-8",
            )
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "branch_created",
                "branch_id": branch_id,
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": "Initialized Abel-alpha branch",
                "artifact_path": "",
            },
        )
        render_session(session)
    return branch


def run_branch_round(args: argparse.Namespace) -> int:
    branch = Path(args.branch).resolve()
    session = branch.parent.parent
    discovery = load_discovery(session)
    rows = read_tsv_rows(branch / "results.tsv")
    round_id = f"round-{len(rows) + 1:03d}"
    result_path = branch / "outputs" / f"{round_id}-edge-result.json"
    report_path = branch / "outputs" / f"{round_id}-edge-validation.md"

    command = [
        args.python_bin,
        "-m",
        "causal_edge.cli",
        "evaluate",
        "--workdir",
        str(branch),
        "--output-json",
        str(result_path),
        "--output-md",
        str(report_path),
    ]
    completed = subprocess.run(command, cwd=session, capture_output=True, text=True)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    decision = alpha_decision(rows, result)

    round_note = branch / "rounds" / f"{round_id}.md"
    round_note.write_text(
        render_round_note(
            ticker=discovery.get("ticker", session.parent.name.upper()),
            exp_id=session.name,
            branch_id=branch.name,
            round_id=round_id,
            mode=args.mode,
            decision=decision,
            description=args.description,
            result=result,
            input_note=args.input_note,
            hypothesis=args.hypothesis,
            expected_signal=args.expected_signal,
            summary=args.summary,
            next_step=args.next_step,
            actions=args.action,
        ),
        encoding="utf-8",
    )

    metrics = result.get("metrics", {})
    with SessionLock(session):
        append_tsv_row(
            branch / "results.tsv",
            RESULTS_HEADER,
            {
                "exp_id": session.name,
                "ticker": discovery.get("ticker", session.parent.name.upper()),
                "branch_id": branch.name,
                "round_id": round_id,
                "decision": decision,
                "lo_adj": f"{metrics.get('lo_adjusted', 0):.3f}",
                "ic": f"{metrics.get('position_ic', 0):.4f}",
                "omega": f"{metrics.get('omega', 0):.3f}",
                "sharpe": f"{metrics.get('sharpe', 0):.3f}",
                "max_dd": f"{metrics.get('max_dd', 0):.4f}",
                "pnl": f"{metrics.get('total_return', 0) * 100:.1f}",
                "K": str(result.get("K", "?")),
                "score": result.get("score", "?/?"),
                "verdict": result.get("verdict", "ERROR"),
                "mode": args.mode,
                "description": args.description,
                "result_path": str(result_path.relative_to(session)),
                "report_path": str(report_path.relative_to(session)),
            },
        )
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "round_recorded",
                "branch_id": branch.name,
                "round_id": round_id,
                "mode": args.mode,
                "verdict": result.get("verdict", "ERROR"),
                "decision": decision,
                "description": args.description,
                "artifact_path": str(result_path.relative_to(session)),
            },
        )
        render_session(session)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return 0 if result.get("verdict") == "PASS" else 1


def render_session(session: Path) -> None:
    discovery = load_discovery(session)
    branches = load_branches(session)
    for branch in branches:
        render_branch(branch, discovery, session.name)
    session_readme = build_session_readme(session, discovery, branches)
    (session / "README.md").write_text(session_readme, encoding="utf-8")


def render_branch(branch: dict, discovery: dict, exp_id: str) -> None:
    branch_dir = branch["branch_dir"]
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    latest_note = (
        read_round_note(branch_dir, latest.get("round_id", "")) if latest else {}
    )

    (branch_dir / "README.md").write_text(
        build_branch_readme(branch, latest_note, exp_id), encoding="utf-8"
    )
    (branch_dir / "memory.md").write_text(
        build_memory(branch, discovery), encoding="utf-8"
    )
    (branch_dir / "thesis.md").write_text(
        build_thesis(branch, discovery), encoding="utf-8"
    )


def print_status(session: Path) -> None:
    discovery = load_discovery(session)
    branches = load_branches(session)
    print(
        f"Session: {session.name} ({discovery.get('ticker', session.parent.name.upper())})"
    )
    print(f"Branches: {len(branches)}")
    print(f"Total rounds: {sum(len(branch['rows']) for branch in branches)}")
    for branch in branches:
        latest = branch["rows"][-1] if branch["rows"] else {}
        keep_count = sum(1 for row in branch["rows"] if row.get("decision") == "keep")
        discard_count = sum(
            1 for row in branch["rows"] if row.get("decision") == "discard"
        )
        print(
            f"  {branch['branch_id']:20s} rounds={len(branch['rows']):2d} keep={keep_count:2d} "
            f"discard={discard_count:2d} latest={latest.get('round_id', 'none')} {latest.get('decision', 'pending')}"
        )


def check_session(session: Path, *, strict: bool) -> int:
    failures: list[str] = []
    if not (session / "events.tsv").exists():
        failures.append("Missing events.tsv")
    if not (session / "README.md").exists():
        failures.append("Missing session README.md")

    branches = load_branches(session)
    if not branches:
        failures.append("No branches found")

    for branch in branches:
        branch_dir = branch["branch_dir"]
        rows = branch["rows"]
        for required in (
            "README.md",
            "thesis.md",
            "memory.md",
            "strategy.py",
            "results.tsv",
        ):
            if not (branch_dir / required).exists():
                failures.append(f"{branch_dir.name}: missing {required}")
        for row in rows:
            round_id = row.get("round_id", "")
            if not round_id:
                failures.append(f"{branch_dir.name}: row missing round_id")
                continue
            if not (branch_dir / "rounds" / f"{round_id}.md").exists():
                failures.append(f"{branch_dir.name}: missing round note {round_id}.md")
            if not (session / row.get("result_path", "")).exists():
                failures.append(
                    f"{branch_dir.name}: missing edge result {row.get('result_path', '')}"
                )
            if not (session / row.get("report_path", "")).exists():
                failures.append(
                    f"{branch_dir.name}: missing edge report {row.get('report_path', '')}"
                )
        if strict:
            for text_path in (
                branch_dir / "README.md",
                branch_dir / "thesis.md",
                branch_dir / "memory.md",
            ):
                text = text_path.read_text(encoding="utf-8")
                if "not recorded" in text or "Fill in" in text:
                    failures.append(
                        f"{branch_dir.name}: unresolved placeholder in {text_path.name}"
                    )

    if failures:
        print("Narrative check failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"Narrative check passed for {session}")
    return 0


def build_session_readme(session: Path, discovery: dict, branches: list[dict]) -> str:
    keep_branches = [
        branch
        for branch in branches
        if branch["rows"] and branch["rows"][-1].get("decision") == "keep"
    ]
    discard_branches = [
        branch
        for branch in branches
        if branch["rows"] and branch["rows"][-1].get("decision") == "discard"
    ]
    leader = keep_branches[-1] if keep_branches else (branches[0] if branches else None)
    executive = "No validated rounds yet. Start the first branch to establish the session baseline."
    if leader and leader["rows"]:
        latest = leader["rows"][-1]
        executive = (
            f"Session has {len(branches)} branch(es): {len(keep_branches)} keep and {len(discard_branches)} discard. "
            f"Current lead is `{leader['branch_id']}` at `{latest.get('round_id', 'none')}` with Lo {float(latest.get('lo_adj') or 0):.3f}, "
            f"Sharpe {float(latest.get('sharpe') or 0):.3f}, PnL {float(latest.get('pnl') or 0):.1f}%."
        )

    branch_lines = (
        "\n".join(
            f"1. `{branch['branch_id']}` - {len(branch['rows'])} rounds, latest `{branch['rows'][-1].get('round_id', 'none')}` {branch['rows'][-1].get('decision', 'pending')}"
            for branch in branches
            if branch["rows"]
        )
        or "1. `No branches yet.`"
    )

    snapshot_lines = (
        "\n".join(
            build_branch_snapshot_line(branch) for branch in branches if branch["rows"]
        )
        or "1. `No branch outcomes yet.`"
    )
    activity_lines = (
        "\n".join(
            format_event_line(row) for row in read_tsv_rows(session / "events.tsv")[-5:]
        )
        or "1. `No events yet.`"
    )

    return f"""# {discovery.get("ticker", session.parent.name.upper())} Exploration Session {session.name}

generated by Abel-alpha narrative layer

## Executive Summary

{executive}

## Session Summary

- ticker: `{discovery.get("ticker", session.parent.name.upper())}`
- exp_id: `{session.name}`
- started_at: `{discovery.get("created_at", "unknown")}`
- discovery_source: `{discovery.get("source", "unknown")}`
- current_status: `{"has_keep" if keep_branches else "active" if branches else "exploring"}`
- branch_count: `{len(branches)}`

## Session Goal

Explore {discovery.get("ticker", session.parent.name.upper())} in session `{session.name}` using discovery source `{discovery.get("source", "unknown")}` and compare candidate branches through validated rounds.

## Selection Narrative

This session tracks {len(branches)} branch(es). Current outcomes: {len(keep_branches)} keep, {len(discard_branches)} discard, {len(branches) - len(keep_branches) - len(discard_branches)} pending.

## Branches

{branch_lines}

## Branch Outcome Snapshot

{snapshot_lines}

## Recent Activity

{activity_lines}

## Next Step

{session_next_step(branches)}
"""


def build_branch_readme(branch: dict, latest_note: dict[str, str], exp_id: str) -> str:
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    keep_rows = [row for row in rows if row.get("decision") == "keep"]
    ledger = (
        "\n".join(
            f"1. `{row.get('round_id', '?')}` - {row.get('description', '?')} [{row.get('score', '?')}] {row.get('decision', '?')}"
            for row in rows
        )
        or "`No rounds yet.`"
    )
    return f"""# {branch["branch_id"]}

generated by Abel-alpha narrative layer

## Basic Info

- branch_id: `{branch["branch_id"]}`
- ticker: `{latest.get("ticker", branch["ticker"])}`
- exp_id: `{exp_id}`
- current_status: `{latest.get("decision", "exploring")}`
- total_rounds: `{len(rows)}`
- latest_round: `{latest.get("round_id", "none")}`
- validation_status: `{latest.get("verdict", "not_validated")}`

## Branch Thesis

See `thesis.md` for the branch hypothesis.

## Latest Conclusion

- decision: `{latest.get("decision", "pending")}`
- summary: `{latest.get("description", "No rounds recorded yet.")}`
- next_step: `{latest_note.get("next_step", "Review the latest round note for the next move.")}`

## Decision Rationale

1. latest_hypothesis: `{latest_note.get("hypothesis", "not recorded")}`
1. latest_summary: `{latest_note.get("summary", latest.get("description", "not recorded"))}`
1. latest_failures: `{latest_note.get("failures", "none")}`

## Round Ledger

{ledger}

## Metric Progression

{branch_progression(rows)}

## Baseline

- keep_rounds: `{len(keep_rows)}`
- latest_keep: `{keep_rows[-1].get("round_id", "none") if keep_rows else "none"}`
"""


def build_memory(branch: dict, discovery: dict) -> str:
    rows = branch["rows"]
    keep_rows = [row for row in rows if row.get("decision") == "keep"]
    discard_rows = [row for row in rows if row.get("decision") == "discard"]
    baseline = (
        f"- latest KEEP: {keep_rows[-1].get('round_id', 'none')} ({keep_rows[-1].get('description', 'n/a')})"
        if keep_rows
        else "- No KEEP baseline yet."
    )
    exhausted = (
        "\n".join(
            f"- {row.get('round_id', '?')} {row.get('description', 'discarded')}"
            for row in discard_rows[-5:]
        )
        or "- none recorded yet"
    )
    worked = (
        "\n".join(
            f"- {row.get('round_id', '?')} {row.get('description', 'kept')}"
            for row in keep_rows[-5:]
        )
        or "- none recorded yet"
    )
    return f"""# {discovery.get("ticker", branch["ticker"])} Research Memory

generated by Abel-alpha narrative layer

## K Budget
- Discovery: K={discovery.get("K_discovery", 0)} via {discovery.get("source", "unknown")}

## Baseline
{baseline}

## Exhausted Directions
{exhausted}

## What Worked
{worked}

## Ideas Not Yet Tried
- record the next untested branch idea here
"""


def build_thesis(branch: dict, discovery: dict) -> str:
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    hypothesis = latest_recorded_hypothesis(branch)
    latest_note = (
        read_round_note(branch["branch_dir"], latest.get("round_id", ""))
        if latest
        else {}
    )
    parents = ", ".join(discovery.get("parents", [])[:5]) or "none recorded"
    blanket = ", ".join(discovery.get("blanket_new", [])[:5]) or "none recorded"
    return f"""# {branch["branch_id"]} Thesis

generated by Abel-alpha narrative layer

## Alpha Source

Branch `{branch["branch_id"]}` currently assumes: `{hypothesis or latest.get("description", "Initial branch hypothesis not recorded yet")}`.
Latest decision is `{latest.get("decision", "pending")}` with verdict `{latest.get("verdict", "not_validated")}`.

## Input Universe

- target: `{discovery.get("ticker", branch["ticker"])}`
- discovery_source: `{discovery.get("source", "unknown")}`
- direct_parents: `{parents}`
- blanket_candidates: `{blanket}`

## Main Risks

{format_risks(latest_note.get("failures", "none"))}
"""


def alpha_decision(rows: list[dict[str, str]], result: dict) -> str:
    if result.get("verdict") != "PASS":
        return "discard"

    baseline = None
    for row in reversed(rows):
        if row.get("decision") == "keep":
            baseline = row
            break
    if baseline is None:
        return "keep"

    current = result.get("metrics", {})
    lo_ok = current.get("lo_adjusted", 0) >= float(baseline.get("lo_adj") or 0)
    sharpe_ok = current.get("sharpe", 0) >= float(baseline.get("sharpe") or 0)
    pnl_ok = current.get("total_return", 0) * 100 >= float(baseline.get("pnl") or 0)
    strictly_better = (
        current.get("lo_adjusted", 0) > float(baseline.get("lo_adj") or 0)
        or current.get("sharpe", 0) > float(baseline.get("sharpe") or 0)
        or current.get("total_return", 0) * 100 > float(baseline.get("pnl") or 0)
    )
    return "keep" if lo_ok and sharpe_ok and pnl_ok and strictly_better else "discard"


def branch_progression(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "`No metric progression yet.`"
    lines = []
    previous = None
    for row in rows:
        lo_adj = float(row.get("lo_adj") or 0)
        sharpe = float(row.get("sharpe") or 0)
        pnl = float(row.get("pnl") or 0)
        delta = ""
        if previous is not None:
            delta = (
                f" | dLo {lo_adj - previous['lo_adj']:+.3f}"
                f" | dSharpe {sharpe - previous['sharpe']:+.3f}"
                f" | dPnL {pnl - previous['pnl']:+.1f}%"
            )
        lines.append(
            f"1. `{row.get('round_id', '?')}` {row.get('decision', '?')} | Lo {lo_adj:.3f} | Sharpe {sharpe:.3f} | PnL {pnl:.1f}%{delta}"
        )
        previous = {"lo_adj": lo_adj, "sharpe": sharpe, "pnl": pnl}
    return "\n".join(lines)


def build_branch_snapshot_line(branch: dict) -> str:
    rows = branch["rows"]
    latest = rows[-1]
    first = rows[0]
    note = read_round_note(branch["branch_dir"], latest.get("round_id", ""))
    reason = (
        note.get("hypothesis") or note.get("failures") or latest.get("description", "")
    )
    return (
        f"1. `{branch['branch_id']}` -> `{latest.get('decision', 'pending')}` after {len(rows)} round(s). "
        f"Why: `{reason or 'not recorded'}`. Trend: Lo {float(first.get('lo_adj') or 0):.3f} -> {float(latest.get('lo_adj') or 0):.3f}, "
        f"Sharpe {float(first.get('sharpe') or 0):.3f} -> {float(latest.get('sharpe') or 0):.3f}, PnL {float(first.get('pnl') or 0):.1f}% -> {float(latest.get('pnl') or 0):.1f}%."
    )


def session_next_step(branches: list[dict]) -> str:
    keep = [
        branch
        for branch in branches
        if branch["rows"] and branch["rows"][-1].get("decision") == "keep"
    ]
    discard = [
        branch
        for branch in branches
        if branch["rows"] and branch["rows"][-1].get("decision") == "discard"
    ]
    if keep and discard:
        return f"Continue improving `{keep[-1]['branch_id']}` or branch from the discarded ideas now that both keep and discard outcomes are recorded."
    if keep:
        return f"Continue improving `{keep[-1]['branch_id']}` or open a sibling branch from its latest KEEP baseline."
    return "Revise the discarded branches or open a new branch with a different hypothesis before the next validation round."


def latest_recorded_hypothesis(branch: dict) -> str:
    for row in reversed(branch["rows"]):
        note = read_round_note(branch["branch_dir"], row.get("round_id", ""))
        hypothesis = (note.get("hypothesis") or "").strip()
        if hypothesis and hypothesis != "No hypothesis supplied.":
            return hypothesis
    return ""


def format_risks(risks: str) -> str:
    cleaned = (risks or "").strip()
    if not cleaned or cleaned == "none":
        return "- no acute validation failures recorded yet"
    return "\n".join(f"- {part.strip()}" for part in cleaned.split(";") if part.strip())


def load_branches(session: Path) -> list[dict]:
    branches_dir = session / "branches"
    branches = []
    if not branches_dir.exists():
        return branches
    discovery = load_discovery(session)
    for branch_dir in sorted(
        child for child in branches_dir.iterdir() if child.is_dir()
    ):
        branches.append(
            {
                "branch_id": branch_dir.name,
                "branch_dir": branch_dir,
                "ticker": discovery.get("ticker", session.parent.name.upper()),
                "rows": read_tsv_rows(branch_dir / "results.tsv"),
            }
        )
    return branches


def load_discovery(session: Path) -> dict:
    path = session / "discovery.json"
    if not path.exists():
        return {
            "ticker": session.parent.name.upper(),
            "source": "unknown",
            "parents": [],
            "blanket_new": [],
            "K_discovery": 0,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def read_round_note(branch_dir: Path, round_id: str) -> dict[str, str]:
    if not round_id:
        return {}
    path = branch_dir / "rounds" / f"{round_id}.md"
    if not path.exists():
        return {}
    fields: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        for key in (
            "hypothesis",
            "expected_signal",
            "failures",
            "summary",
            "next_step",
        ):
            prefix = f"- {key}: `"
            if line.startswith(prefix) and line.endswith("`"):
                fields[key] = line[len(prefix) : -1]
    return fields


def render_round_note(**kwargs) -> str:
    result = kwargs["result"]
    metrics = result.get("metrics", {})
    actions = kwargs.get("actions") or ["Executed raw causal-edge evaluation"]
    action_lines = "\n".join(f"1. {action}" for action in actions)
    return f"""# {kwargs["round_id"]}

## Basic Info

- date: `{_today()}`
- ticker: `{kwargs["ticker"]}`
- exp_id: `{kwargs["exp_id"]}`
- branch_id: `{kwargs["branch_id"]}`
- mode: `{kwargs["mode"]}`
- decision: `{kwargs["decision"]}`
- score: `{result.get("score", "?/?")}`
- verdict: `{result.get("verdict", "ERROR")}`

## Goal

`{kwargs["description"]}`

## Inputs And Hypothesis

- input: `{kwargs.get("input_note") or f"Branch {kwargs['branch_id']} entering {kwargs['round_id']}."}`
- hypothesis: `{kwargs.get("hypothesis") or "No hypothesis supplied."}`
- expected_signal: `{kwargs.get("expected_signal") or "Improve evaluation outcome versus the current working baseline."}`

## Actions

{action_lines}

## Key Results

- lo_adjusted: `{metrics.get("lo_adjusted", 0):.3f}`
- position_ic: `{metrics.get("position_ic", 0):.4f}`
- omega: `{metrics.get("omega", 0):.3f}`
- sharpe: `{metrics.get("sharpe", 0):.3f}`
- total_return: `{metrics.get("total_return", 0) * 100:.1f}%`
- max_dd: `{metrics.get("max_dd", 0) * 100:.1f}%`
- failures: `{"; ".join(result.get("failures", [])) or "none"}`

## Conclusion

- summary: `{kwargs.get("summary") or f"Recorded {result.get('verdict', 'ERROR')} {result.get('score', '?/?')}."}`
- next_step: `{kwargs.get("next_step") or "Review the branch README and decide whether to keep refining or open a new branch."}`
"""


def read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv_header(path: Path, header: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
        writer.writeheader()


def append_tsv_row(path: Path, header: list[str], row: dict[str, str]) -> None:
    write_tsv_header(path, header)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t")
        writer.writerow(row)


def format_event_line(row: dict[str, str]) -> str:
    tail = " ".join(
        part
        for part in (
            row.get("branch_id", ""),
            row.get("round_id", ""),
            row.get("decision", ""),
        )
        if part
    )
    return f"1. `{row.get('timestamp', '')}` {row.get('event', '')} {tail} - {row.get('description', '')}".rstrip()


class SessionLock:
    def __init__(self, session: Path, timeout: float = 30.0):
        self.lock_path = session / ".alpha.lock"
        self.timeout = timeout
        self.fd: int | None = None

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(
                    str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR
                )
                os.write(self.fd, str(os.getpid()).encode("utf-8"))
                return self
            except FileExistsError:
                if time.time() >= deadline:
                    raise TimeoutError(f"Timed out waiting for lock {self.lock_path}")
                time.sleep(0.1)

    def __exit__(self, exc_type, exc, tb):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


if __name__ == "__main__":
    raise SystemExit(main())
