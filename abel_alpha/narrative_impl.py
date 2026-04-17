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

from abel_alpha.doctor import render_doctor_report, run_doctor
from abel_alpha.env import init_workspace_env
from abel_alpha.workspace import (
    build_default_manifest,
    default_activate_command,
    find_workspace_root,
    load_workspace_manifest,
    resolve_runtime_python,
    render_workspace_status,
    resolve_workspace_paths,
    scaffold_workspace,
)

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

DEFAULT_BACKTEST_START = "2020-01-01"

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
    "handoff_path",
]

STRATEGY_TEMPLATE = '''"""Strategy for {ticker}. Fill in run_strategy().

Final strategy output must satisfy abs(position) <= 1.
Default backtest behavior should use the provided start date and treat end=None as the latest available date.
If provided, context contains workspace/session/branch/discovery metadata from Abel-alpha.
"""

import numpy as np
import pandas as pd


def run_strategy(*, start=None, end=None, context=None):
    raise NotImplementedError("Fill in run_strategy()")
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Abel-alpha workspace CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    workspace = sub.add_parser("workspace", help="Create or inspect an Abel-alpha workspace")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)

    workspace_init = workspace_sub.add_parser("init", help="Create a new workspace scaffold")
    workspace_init.add_argument("name", help="Workspace directory name")
    workspace_init.add_argument(
        "--path",
        default=None,
        help="Explicit workspace directory path (defaults to ./<name>)",
    )

    workspace_status = workspace_sub.add_parser("status", help="Show current workspace status")
    workspace_status.add_argument(
        "--path",
        default=".",
        help="Directory to inspect for the nearest workspace root",
    )

    env_parser = sub.add_parser("env", help="Manage the local workspace Python environment")
    env_sub = env_parser.add_subparsers(dest="env_command", required=True)
    env_init = env_sub.add_parser("init", help="Create the workspace venv and install dependencies")
    env_init.add_argument(
        "--path",
        default=".",
        help="Directory inside the target workspace",
    )
    env_init.add_argument(
        "--python",
        dest="base_python",
        default=None,
        help="Base interpreter used to create the workspace venv",
    )
    env_init.add_argument(
        "--alpha-source",
        default=None,
        help="Local Abel-alpha source tree used for installation",
    )
    env_init.add_argument(
        "--edge-spec",
        default=None,
        help="Pip-installable Abel-edge target (defaults to the workspace GitHub main spec)",
    )
    env_init.add_argument(
        "--edge-source",
        default=None,
        help="Optional local Abel-edge source tree override for development",
    )
    env_init.add_argument(
        "--no-editable",
        action="store_true",
        help="Install Abel-alpha from local source in regular mode instead of editable mode",
    )

    doctor = sub.add_parser("doctor", help="Check workspace readiness")
    doctor.add_argument(
        "--path",
        default=".",
        help="Directory inside the target workspace",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output",
    )

    init_session = sub.add_parser("init-session", help="Create a narrative session")
    init_session.add_argument("--ticker", required=True)
    init_session.add_argument("--exp-id", required=True)
    init_session.add_argument("--root", default=None)
    init_session.add_argument(
        "--backtest-start",
        default=DEFAULT_BACKTEST_START,
        help="Session-level backtest start date passed to causal-edge evaluate",
    )
    init_session.add_argument(
        "--discover",
        action="store_true",
        help="Run live Abel discovery and persist it into discovery.json",
    )
    init_session.add_argument(
        "--discover-limit",
        type=int,
        default=10,
        help="Maximum Abel nodes to record per discovery call",
    )

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
    run_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run causal-edge evaluate (defaults to the workspace python when available)",
    )

    render = sub.add_parser("render", help="Render summaries for a session")
    render.add_argument("--session", required=True)

    status = sub.add_parser("status", help="Print session status")
    status.add_argument("--session", required=True)

    check = sub.add_parser("check", help="Check narrative completeness")
    check.add_argument("--session", required=True)
    check.add_argument("--strict", action="store_true")

    args = parser.parse_args()

    if args.command == "workspace":
        return handle_workspace_command(args)
    if args.command == "env":
        return handle_env_command(args)
    if args.command == "doctor":
        return handle_doctor_command(args)
    if args.command == "init-session":
        init_session_dir(
            args.ticker,
            args.exp_id,
            resolve_session_root(args.root),
            discover=args.discover,
            discover_limit=args.discover_limit,
            backtest_start=args.backtest_start,
        )
        return 0
    if args.command == "init-branch":
        init_branch_dir(resolve_workspace_arg_path(args.session), args.branch_id)
        return 0
    if args.command == "run-branch":
        return run_branch_round(args)
    if args.command == "render":
        render_session(resolve_workspace_arg_path(args.session))
        return 0
    if args.command == "status":
        print_status(resolve_workspace_arg_path(args.session))
        return 0
    if args.command == "check":
        return check_session(resolve_workspace_arg_path(args.session), strict=args.strict)
    return 1


def handle_workspace_command(args: argparse.Namespace) -> int:
    if args.workspace_command == "init":
        target_root = Path(args.path).expanduser() if args.path else None
        root = scaffold_workspace(args.name, target_root=target_root)
        manifest = build_default_manifest(args.name)
        resolved = resolve_workspace_paths(root, manifest)
        print(f"Created Abel-alpha workspace at {root}")
        print(f"  manifest: {root / 'alpha.workspace.yaml'}")
        print(f"  research: {resolved['research_root']}")
        print(f"  docs: {resolved['docs_root']}")
        print("")
        print("Next:")
        print(f"  cd {root}")
        print("  abel-alpha workspace status")
        print("  abel-alpha env init")
        print("  abel-alpha doctor")
        return 0
    if args.workspace_command == "status":
        start = Path(args.path).expanduser().resolve()
        root = find_workspace_root(start)
        if root is None:
            print(f"No Abel-alpha workspace found at or above {start}")
            return 1
        manifest = load_workspace_manifest(root)
        print(render_workspace_status(root, manifest))
        return 0
    return 1


def handle_env_command(args: argparse.Namespace) -> int:
    if args.env_command != "init":
        return 1
    result = init_workspace_env(
        start=Path(args.path).expanduser(),
        base_python=args.base_python,
        alpha_source=args.alpha_source,
        edge_spec=args.edge_spec,
        edge_source=args.edge_source,
        alpha_editable=not args.no_editable,
    )
    print(f"Workspace environment ready at {result.workspace_root}")
    print(f"  venv: {result.venv_path}")
    print(f"  python: {result.python_path}")
    print(f"  alpha_source: {result.alpha_source}")
    print(f"  edge_install_mode: {result.edge_install_mode}")
    print(f"  edge_install_target: {result.edge_install_target}")
    print(f"  alpha_install_mode: {'editable' if result.alpha_editable else 'regular'}")
    print("")
    print("Next:")
    print("  abel-alpha doctor")
    print(f"  {default_activate_command()}")
    return 0


def handle_doctor_command(args: argparse.Namespace) -> int:
    result = run_doctor(Path(args.path).expanduser())
    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(render_doctor_report(result))
    return 0 if result.get("status") == "ready" else 1


def resolve_session_root(root_arg: str | None) -> Path:
    """Resolve the session root from an explicit argument or current workspace."""
    if root_arg:
        return resolve_workspace_arg_path(root_arg)
    workspace_root = find_workspace_root()
    if workspace_root is not None:
        manifest = load_workspace_manifest(workspace_root)
        return resolve_workspace_paths(workspace_root, manifest)["research_root"]
    return Path("research")


def resolve_workspace_arg_path(value: str) -> Path:
    """Resolve a CLI path argument relative to the current workspace when possible."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    workspace_root = find_workspace_root()
    if workspace_root is not None:
        return workspace_root / path
    return path


def resolve_default_python_bin(branch: Path) -> str:
    """Resolve the interpreter used for edge evaluation."""
    workspace_root = find_workspace_root(branch)
    if workspace_root is not None:
        manifest = load_workspace_manifest(workspace_root)
        python_path = resolve_runtime_python(workspace_root, manifest)
        if python_path.exists():
            return str(python_path)
    return sys.executable


def init_session_dir(
    ticker: str,
    exp_id: str,
    root: Path,
    *,
    discover: bool = False,
    discover_limit: int = 10,
    backtest_start: str = DEFAULT_BACKTEST_START,
) -> Path:
    session = root / ticker.lower() / exp_id
    session.mkdir(parents=True, exist_ok=True)
    discovery_data = None
    if discover:
        discovery_data = fetch_live_discovery(ticker, limit=discover_limit)
    with SessionLock(session):
        write_tsv_header(session / "events.tsv", EVENTS_HEADER)
        discovery_path = session / "discovery.json"
        if discovery_data is not None:
            discovery_data["backtest"] = {"start": backtest_start}
            discovery_path.write_text(
                json.dumps(discovery_data, indent=2),
                encoding="utf-8",
            )
        elif not discovery_path.exists():
            discovery_path.write_text(
                json.dumps(
                    {
                        "ticker": ticker.upper(),
                        "source": "pending",
                        "parents": [],
                        "blanket_new": [],
                        "children": [],
                        "K_discovery": 0,
                        "backtest": {"start": backtest_start},
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
                "description": f"Initialized Abel-alpha narrative session (backtest start {backtest_start})",
                "artifact_path": "",
            },
        )
        if discovery_data is not None:
            append_tsv_row(
                session / "events.tsv",
                EVENTS_HEADER,
                {
                    "timestamp": _now(),
                    "event": "discovery_recorded",
                    "branch_id": "",
                    "round_id": "",
                    "mode": "",
                    "verdict": "",
                    "decision": "",
                    "description": (
                        f"Recorded live Abel discovery with K={discovery_data['K_discovery']}"
                    ),
                    "artifact_path": str(discovery_path.relative_to(session)),
                },
            )
        render_session(session)
    return session


def fetch_live_discovery(ticker: str, *, limit: int) -> dict:
    try:
        from causal_edge.plugins.abel.credentials import (
            MissingAbelApiKeyError,
            require_api_key,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Live Abel discovery requires causal-edge with the Abel plugin installed. "
            "Create a virtual environment, install causal-edge, then retry."
        ) from exc

    from causal_edge.plugins.abel.discover import discover_graph_nodes

    try:
        require_api_key()
    except MissingAbelApiKeyError as exc:
        raise RuntimeError(
            "init-session --discover requires Abel auth before live discovery. "
            "Install `causal-abel` from `https://github.com/Abel-ai-causality/Abel-skills/tree/main/skills` and complete its OAuth flow, or run `causal-edge login` for the standalone fallback, "
            "then retry `abel-alpha init-session --ticker "
            f"{ticker.upper()} --exp-id <exp-id> --discover`."
        ) from exc

    try:
        from causal_edge.plugins.abel.discover import discover_graph_payload

        payload = discover_graph_payload(ticker.upper(), mode="all", limit=limit)
        payload["backtest"] = {"start": DEFAULT_BACKTEST_START}
        payload.setdefault("created_at", _now())
        return payload
    except ImportError:
        pass
    except AttributeError:
        pass

    # Fallback for older causal-edge builds that still expose text-only discovery.
    parents_output = discover_graph_nodes(ticker.upper(), mode="parents", limit=limit)
    blanket_output = discover_graph_nodes(ticker.upper(), mode="mb", limit=limit)
    return build_discovery_payload_from_text(
        ticker=ticker.upper(),
        parents_output=parents_output,
        blanket_output=blanket_output,
    )


def build_discovery_payload_from_text(
    *,
    ticker: str,
    parents_output: str,
    blanket_output: str,
) -> dict:
    """Build the standard discovery payload from legacy text output."""
    parents = parse_discovery_items(parents_output)
    blanket_items = parse_discovery_items(blanket_output)
    parent_keys = {(item["ticker"], item["field"]) for item in parents}

    children = []
    blanket_new = []
    seen_children = set()
    seen_blanket = set()

    for item in blanket_items:
        key = (item["ticker"], item["field"])
        roles = item.get("roles", [])
        if "child" in roles and key not in seen_children:
            children.append({"ticker": item["ticker"], "field": item["field"]})
            seen_children.add(key)
            continue
        if key in parent_keys or key in seen_blanket:
            continue
        blanket_new.append(
            {
                "ticker": item["ticker"],
                "field": item["field"],
                "roles": roles,
            }
        )
        seen_blanket.add(key)

    return {
        "ticker": ticker.upper(),
        "source": "abel_live",
        "parents": parents,
        "blanket_new": blanket_new,
        "children": children,
        "K_discovery": len(parents),
        "backtest": {"start": DEFAULT_BACKTEST_START},
        "created_at": _now(),
    }


def parse_discovery_items(output: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if line.startswith("  - ticker: "):
            if current is not None:
                items.append(current)
            current = {"ticker": line.split(": ", 1)[1].strip(), "roles": []}
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("field: "):
            current["field"] = stripped.split(": ", 1)[1].strip()
            continue
        if stripped.startswith("roles: [") and stripped.endswith("]"):
            roles_text = stripped[len("roles: [") : -1].strip()
            current["roles"] = [
                role.strip() for role in roles_text.split(",") if role.strip()
            ]

    if current is not None:
        items.append(current)

    normalized = []
    for item in items:
        ticker = str(item.get("ticker", "")).strip()
        field = str(item.get("field", "")).strip()
        if not ticker or not field:
            continue
        normalized.append(
            {
                "ticker": ticker,
                "field": field,
                "roles": list(item.get("roles", [])),
            }
        )
    return normalized


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
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    discovery = load_discovery(session)
    rows = read_tsv_rows(branch / "results.tsv")
    round_id = f"round-{len(rows) + 1:03d}"
    result_path = branch / "outputs" / f"{round_id}-edge-result.json"
    report_path = branch / "outputs" / f"{round_id}-edge-validation.md"
    handoff_path = branch / "outputs" / f"{round_id}-edge-handoff.json"
    context_path = branch / "outputs" / f"{round_id}-alpha-context.json"
    backtest_start = _get_backtest_start(discovery)
    context_path.write_text(
        json.dumps(
            build_branch_context(
                branch=branch,
                session=session,
                discovery=discovery,
                backtest_start=backtest_start,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    python_bin = args.python_bin or resolve_default_python_bin(branch)
    command = [
        python_bin,
        "-m",
        "causal_edge.cli",
        "evaluate",
        "--workdir",
        str(branch),
        "--context-json",
        str(context_path),
        "--output-json",
        str(result_path),
        "--output-md",
        str(report_path),
        "--output-handoff",
        str(handoff_path),
        "--start",
        backtest_start,
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
            backtest_start=backtest_start,
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
                "handoff_path": str(handoff_path.relative_to(session)),
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
            if not (session / row.get("handoff_path", "")).exists():
                failures.append(
                    f"{branch_dir.name}: missing edge handoff {row.get('handoff_path', '')}"
                )
            if strict:
                validate_edge_handoff(session, branch_dir.name, row, failures)
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
- backtest_start: `{_get_backtest_start(discovery)}`
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
    parents = format_discovery_nodes(discovery.get("parents", []), limit=5)
    blanket = format_discovery_nodes(discovery.get("blanket_new", []), limit=5)
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


def format_discovery_nodes(items: list[object], *, limit: int = 5) -> str:
    rendered = []
    for item in items[:limit]:
        if isinstance(item, str):
            rendered.append(item)
            continue
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker", "")).strip()
        field = str(item.get("field", "")).strip()
        roles = [
            str(role).strip() for role in item.get("roles", []) if str(role).strip()
        ]
        label = ".".join(part for part in (ticker, field) if part)
        if not label:
            continue
        if roles:
            label = f"{label} ({', '.join(roles)})"
        rendered.append(label)
    return ", ".join(rendered) or "none recorded"


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

    from causal_edge.validation.gate_logic import decide_keep_discard
    from causal_edge.validation.metrics import load_profile

    profile_name = str(result.get("profile") or "").strip()
    if not profile_name:
        raise RuntimeError(
            "edge evaluation did not provide a profile for baseline compare"
        )

    decision = decide_keep_discard(
        result.get("metrics", {}),
        {
            "lo_adjusted": float(baseline.get("lo_adj") or 0),
            "position_ic": float(baseline.get("ic") or 0),
            "omega": float(baseline.get("omega") or 0),
            "sharpe": float(baseline.get("sharpe") or 0),
            "total_return": float(baseline.get("pnl") or 0) / 100.0,
            "max_dd": float(baseline.get("max_dd") or 0),
        },
        load_profile(profile_name),
    )
    return "keep" if decision == "KEEP" else "discard"


def build_branch_context(
    *,
    branch: Path,
    session: Path,
    discovery: dict,
    backtest_start: str,
) -> dict:
    """Build the structured context passed into causal-edge evaluate."""
    workspace_root = find_workspace_root(branch)
    return {
        "workspace_root": str(workspace_root) if workspace_root is not None else None,
        "session_dir": str(session.resolve()),
        "branch_dir": str(branch.resolve()),
        "discovery_path": str((session / "discovery.json").resolve()),
        "ticker": discovery.get("ticker", session.parent.name.upper()),
        "backtest_start": backtest_start,
    }


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
    requested_window = result.get("requested_window", {})
    effective_window = result.get("effective_window", {})
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
- requested_start: `{requested_window.get("start", kwargs.get("backtest_start", DEFAULT_BACKTEST_START))}`
- requested_end: `{requested_window.get("end") or "latest"}`
- effective_window: `{effective_window.get("start", "unknown")} -> {effective_window.get("end", "unknown")}`

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


def validate_edge_handoff(
    session: Path,
    branch_name: str,
    row: dict[str, str],
    failures: list[str],
) -> None:
    handoff_rel = row.get("handoff_path", "")
    if not handoff_rel:
        failures.append(f"{branch_name}: missing edge handoff path")
        return
    handoff_path = session / handoff_rel
    if not handoff_path.exists():
        return
    try:
        from causal_edge.research.handoff import (
            load_strategy_handoff,
            validate_strategy_handoff,
        )
    except Exception as exc:
        failures.append(
            f"{branch_name}: unable to import edge handoff validator: {exc}"
        )
        return
    try:
        payload = load_strategy_handoff(handoff_path)
    except Exception as exc:
        failures.append(f"{branch_name}: invalid edge handoff JSON: {exc}")
        return
    for reason in validate_strategy_handoff(payload, handoff_path=handoff_path):
        failures.append(f"{branch_name}: edge handoff rejected - {reason}")


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


def _get_backtest_start(discovery: dict) -> str:
    backtest = discovery.get("backtest") or {}
    if isinstance(backtest, dict):
        start = backtest.get("start")
        if start:
            return str(start)
    return DEFAULT_BACKTEST_START


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
