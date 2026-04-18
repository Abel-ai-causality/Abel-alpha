"""Abel-alpha research narrative layer.

Organizes exploration sessions, records experimental process, and renders narrative
summaries on top of raw causal-edge evaluation outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from abel_alpha.doctor import doctor_exit_code, render_doctor_report, run_doctor
from abel_alpha.edge_runtime import build_workspace_runtime_env
from abel_alpha.env import init_workspace_env
from abel_alpha.workspace import (
    build_default_manifest,
    default_activate_command,
    find_workspace_root,
    load_workspace_manifest,
    resolve_workspace_env_file,
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
SESSION_STATE_FILENAME = "session_state.json"
BRANCH_STATE_FILENAME = "branch_state.json"
READINESS_FILENAME = "readiness.json"
BRANCH_SPEC_FILENAME = "branch.yaml"
DEPENDENCIES_FILENAME = "dependencies.json"

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

ENGINE_TEMPLATE = '''"""Research engine for {ticker}. Fill in BranchEngine.compute_signals().

Default backtest behavior should follow branch.yaml first and the injected context second.
If provided, self.context contains workspace/session/branch/discovery/readiness metadata from Abel-alpha.
Use branch.yaml to make the critical research choices explicit:
  - target
  - requested_start
  - selected_drivers
  - overlap_mode
Then use StrategyEngine research helpers as thin readers/executors:
  - self.research_target_ticker()
  - self.research_requested_start()
  - self.research_driver_tickers()
  - self.load_research_bars(...)
  - self.research_close_frame(...)
  - self.research_target_driver_frame(overlap="target_only")
If you fetch market data, pass an explicit `limit=...` instead of relying on API defaults.
Avoid blanket `dropna()` on a joined price frame before confirming the target ticker column still survives.
If data or runtime setup is broken, let the error surface and inspect it with `abel-alpha debug-branch`;
do not hide setup failures behind synthetic flat outputs.
Current readiness warning: {readiness_warning}
Coverage hints: {coverage_hints_text}
"""
 
from __future__ import annotations

from causal_edge.engine.base import StrategyEngine


class BranchEngine(StrategyEngine):
    def compute_signals(self):
        target = self.research_target_ticker() or "{ticker}"
        start = self.research_requested_start() or "2020-01-01"
        branch_spec = (self.context or {{}}).get("branch_spec") or {{}}
        selected_drivers = branch_spec.get("selected_drivers") or self.research_driver_tickers()
        # Example paved-road research flow:
        # bars = self.load_research_bars(
        #     driver_tickers=selected_drivers,
        #     limit=600,
        # )
        # close_frame = self.research_close_frame(
        #     driver_tickers=selected_drivers,
        #     limit=600,
        # )
        # target_close, driver_frame = self.research_target_driver_frame(
        #     driver_tickers=selected_drivers,
        #     overlap=branch_spec.get("overlap_mode") or "target_only",
        #     require_drivers=True,
        #     limit=600,
        # )
        # Start target-first, then tighten overlap only if the branch thesis truly needs it.
        # Build signals from those aligned bars, then return self.finalize_signals(...)
        readiness = self.research_data_readiness()
        coverage_hints = readiness.get("coverage_hints") or {{}}
        target_start = coverage_hints.get("target_safe_start")
        common_start = coverage_hints.get("dense_overlap_hint_start")
        raise NotImplementedError(
            "This branch is still using the default Abel-alpha scaffold. "
            "Replace the stub in engine.py before recording a real round. "
            f"requested_start={{start}}; target={{target}}; selected_drivers={{len(selected_drivers)}}; "
            f"target_safe_start={{target_start or 'n/a'}}; "
            f"dense_overlap_hint={{common_start or 'n/a'}}. "
            "Edit branch.yaml first if the default driver selection is not what this branch needs. "
            "Use `abel-alpha debug-branch` while wiring data helpers if you want a quick dry run."
        )

    def get_latest_signal(self):
        return {{"position": 0.0, "date": "not-run"}}
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
        "--runtime-python",
        default=None,
        help="Use an existing interpreter instead of creating the workspace venv",
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

    set_backtest_start = sub.add_parser(
        "set-backtest-start",
        help="Update the session-level backtest start and refresh readiness",
    )
    set_backtest_start.add_argument("--session", required=True)
    start_group = set_backtest_start.add_mutually_exclusive_group(required=True)
    start_group.add_argument(
        "--date",
        default=None,
        help="Explicit YYYY-MM-DD backtest start",
    )
    start_group.add_argument(
        "--target-safe",
        action="store_true",
        help="Use the target-safe start hint from readiness",
    )
    start_group.add_argument(
        "--coverage-hint",
        action="store_true",
        help="Use the dense-overlap coverage hint from readiness",
    )

    set_hypothesis = sub.add_parser(
        "set-hypothesis",
        help="Persist a branch-level hypothesis without recording a round",
    )
    set_hypothesis.add_argument("--branch", required=True)
    set_hypothesis.add_argument("--text", required=True)

    init_branch = sub.add_parser("init-branch", help="Create a branch under a session")
    init_branch.add_argument("--session", required=True)
    init_branch.add_argument("--branch-id", required=True)

    prepare_branch = sub.add_parser(
        "prepare-branch",
        help="Resolve branch data dependencies and warm the edge cache before evaluation",
    )
    prepare_branch.add_argument("--branch", required=True)
    prepare_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run causal-edge warm-cache (defaults to the workspace python when available)",
    )
    prepare_branch.add_argument(
        "--cache-limit",
        type=int,
        default=5000,
        help="Warm-cache fetch limit used for each requested symbol",
    )

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
    run_branch.add_argument(
        "--allow-untouched-template",
        action="store_true",
        help="Allow recording a round from the untouched default engine scaffold",
    )

    promote_branch = sub.add_parser(
        "promote-branch",
        help="Create a promotion bundle from a prepared research branch",
    )
    promote_branch.add_argument("--branch", required=True)
    promote_branch.add_argument(
        "--output-dir",
        default=None,
        help="Optional destination directory (defaults to <session>/promotions/<branch-id>)",
    )

    debug_branch = sub.add_parser(
        "debug-branch",
        help="Run edge debug-evaluate without recording a narrative round",
    )
    debug_branch.add_argument("--branch", required=True)
    debug_branch.add_argument(
        "--python-bin",
        default=None,
        help="Interpreter used to run causal-edge debug-evaluate (defaults to the workspace python when available)",
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
        session = init_session_dir(
            args.ticker,
            args.exp_id,
            resolve_session_root(args.root),
            discover=args.discover,
            discover_limit=args.discover_limit,
            backtest_start=args.backtest_start,
        )
        discovery = load_discovery(session)
        readiness = load_readiness(session)
        print(f"Created Abel-alpha session at {session}")
        print(f"  ticker: {discovery.get('ticker', args.ticker.upper())}")
        print(f"  discovery: {session / 'discovery.json'}")
        print(f"  events: {session / 'events.tsv'}")
        if readiness:
            print(f"  readiness: {session / READINESS_FILENAME}")
        if args.discover:
            print(
                f"  discovery_source: {discovery.get('source', 'unknown')} "
                f"(K={discovery.get('K_discovery', 0)})"
            )
            readiness_summary = format_data_readiness_summary(readiness)
            if readiness_summary:
                print(f"  data_readiness: {readiness_summary}")
            for line in readiness_recommendation_lines(readiness):
                print(f"  {line}")
            warning = build_readiness_warning(readiness)
            if warning:
                print(f"  warning: {warning}")
        else:
            print("  discovery_source: pending (live discovery not run)")
        print("")
        print("Next:")
        print(f"  abel-alpha init-branch --session {session} --branch-id graph-v1")
        return 0
    if args.command == "set-backtest-start":
        session = resolve_workspace_arg_path(args.session)
        backtest_start, source = resolve_backtest_start_request(
            session=session,
            explicit_date=args.date,
            use_target_safe=args.target_safe,
            use_coverage_hint=args.coverage_hint,
        )
        discovery, readiness = update_backtest_start(
            session=session,
            backtest_start=backtest_start,
            source=source,
        )
        print(f"Updated Abel-alpha session at {session}")
        print(f"  backtest_start: {backtest_start}")
        print(f"  source: {source}")
        readiness_summary = format_data_readiness_summary(readiness)
        if readiness_summary:
            print(f"  data_readiness: {readiness_summary}")
        for line in readiness_recommendation_lines(readiness):
            print(f"  {line}")
        warning = build_readiness_warning(readiness)
        if warning:
            print(f"  warning: {warning}")
        print("")
        print("Next:")
        print(f"  abel-alpha status --session {session}")
        return 0
    if args.command == "set-hypothesis":
        branch = resolve_workspace_arg_path(args.branch).resolve()
        session = branch.parent.parent
        hypothesis = str(args.text or "").strip()
        if not has_explicit_hypothesis(hypothesis):
            raise RuntimeError(
                "Hypothesis text must include a real causal claim, not an empty placeholder."
            )
        with SessionLock(session):
            persist_branch_hypothesis(branch, hypothesis, source="manual")
            append_tsv_row(
                session / "events.tsv",
                EVENTS_HEADER,
                {
                    "timestamp": _now(),
                    "event": "branch_hypothesis_updated",
                    "branch_id": branch.name,
                    "round_id": "",
                    "mode": "",
                    "verdict": "",
                    "decision": "",
                    "description": "Updated persistent branch hypothesis",
                    "artifact_path": str((branch / BRANCH_STATE_FILENAME).relative_to(session)),
                },
            )
            render_session(session)
        print(f"Updated branch hypothesis for {branch}")
        print(f"  hypothesis: {hypothesis}")
        print("")
        print("Next:")
        print(f"  abel-alpha debug-branch --branch {branch}")
        print(f"  abel-alpha run-branch --branch {branch} -d \"baseline\"")
        return 0
    if args.command == "init-branch":
        session = resolve_workspace_arg_path(args.session)
        discovery = load_discovery(session)
        readiness = load_readiness(session)
        branch = init_branch_dir(session, args.branch_id)
        print(f"Created Abel-alpha branch at {branch}")
        print(f"  branch_spec: {branch / BRANCH_SPEC_FILENAME}")
        print(f"  engine: {branch / 'engine.py'}")
        print(f"  rounds: {branch / 'rounds'}")
        print(f"  outputs: {branch / 'outputs'}")
        print("")
        warning = build_readiness_warning(readiness)
        if warning:
            print("Readiness:")
            print(f"  warning: {warning}")
            for line in readiness_recommendation_lines(readiness):
                print(f"  coverage_hint: {line}")
        print("")
        print("Reminders:")
        print("  Confirm branch.yaml before wiring engine.py so target/start/drivers stay explicit.")
        print("  If you fetch bars, pass an explicit `limit=...`.")
        print("  Avoid blanket `dropna()` on joined frames before confirming the target ticker remains present.")
        print("  Replace the default scaffold stub before recording the first real round.")
        print("")
        print("Next:")
        print(f"  edit {branch / BRANCH_SPEC_FILENAME}")
        print(f"  edit {branch / 'engine.py'}")
        print(f"  abel-alpha prepare-branch --branch {branch}")
        print(f"  abel-alpha debug-branch --branch {branch}")
        print(f"  abel-alpha run-branch --branch {branch} -d \"baseline\"")
        return 0
    if args.command == "prepare-branch":
        return prepare_branch_inputs(args)
    if args.command == "run-branch":
        return run_branch_round(args)
    if args.command == "promote-branch":
        return promote_branch_bundle(args)
    if args.command == "debug-branch":
        return debug_branch_run(args)
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
        runtime_python=args.runtime_python,
        alpha_editable=not args.no_editable,
    )
    print(f"Workspace environment ready at {result.workspace_root}")
    print(f"  venv: {result.venv_path}")
    print(f"  python: {result.python_path}")
    print(f"  alpha_source: {result.alpha_source}")
    print(f"  runtime_mode: {result.runtime_mode}")
    print(f"  venv_provider: {result.venv_provider}")
    print(f"  edge_install_mode: {result.edge_install_mode}")
    print(f"  edge_install_target: {result.edge_install_target}")
    print(f"  alpha_install_mode: {'editable' if result.alpha_editable else 'regular'}")
    print("  alpha_install_reason: installs the packaged abel-alpha CLI into this workspace runtime")
    if result.runtime_mode == "existing_python":
        print("  runtime_note: using an existing interpreter instead of creating the workspace .venv")
    if result.edge_discovery_payload_capable is not None:
        print(f"  edge_discovery_payload: {'yes' if result.edge_discovery_payload_capable else 'no'}")
    if result.edge_context_json_capable is not None:
        print(f"  edge_context_json: {'yes' if result.edge_context_json_capable else 'no'}")
    print("")
    if result.edge_discovery_payload_capable is False or result.edge_context_json_capable is False:
        print("Warning:")
        print("  Installed Abel-edge is missing required alpha contracts.")
        print("  Run `abel-alpha doctor` and upgrade the workspace runtime before starting research.")
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
    return doctor_exit_code(result)


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
    readiness_report = None
    if discover:
        discovery_data = fetch_live_discovery(ticker, limit=discover_limit)
        discovery_data["backtest"] = {"start": backtest_start}
        readiness_report = refresh_data_readiness(
            session=session,
            discovery_data=discovery_data,
            backtest_start=backtest_start,
        )
    with SessionLock(session):
        write_tsv_header(session / "events.tsv", EVENTS_HEADER)
        if not session_state_path(session).exists():
            write_session_state(session, {})
        discovery_path = session / "discovery.json"
        if discovery_data is not None:
            write_discovery(session, discovery_data)
        elif not discovery_path.exists():
            write_discovery(
                session,
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
            )
        if readiness_report is not None:
            write_readiness(session, readiness_report)
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
            if readiness_report:
                append_tsv_row(
                    session / "events.tsv",
                    EVENTS_HEADER,
                    {
                        "timestamp": _now(),
                        "event": "data_readiness_recorded",
                        "branch_id": "",
                        "round_id": "",
                        "mode": "",
                        "verdict": "",
                        "decision": "",
                        "description": (
                            "Recorded driver data readiness: "
                            f"{format_data_readiness_summary(readiness_report)}"
                        ),
                        "artifact_path": READINESS_FILENAME,
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
        from causal_edge.plugins.abel.discover import discover_graph_payload
    except ImportError as exc:
        raise RuntimeError(
            "Live Abel discovery requires causal-edge with the Abel plugin installed. "
            "Create a virtual environment, install causal-edge, then retry."
        ) from exc
    workspace_root = find_workspace_root()
    if workspace_root is not None:
        os.environ.setdefault(
            "ABEL_AUTH_ENV_FILE",
            str(resolve_workspace_env_file(workspace_root).resolve()),
        )

    try:
        require_api_key()
    except MissingAbelApiKeyError as exc:
        raise RuntimeError(
            "init-session --discover requires Abel auth before live discovery. "
            "Install `causal-abel` from `https://github.com/Abel-ai-causality/Abel-skills/tree/main/skills` and complete its OAuth flow, or run `causal-edge login` for the standalone fallback, "
            "then retry `abel-alpha init-session --ticker "
            f"{ticker.upper()} --exp-id <exp-id> --discover`."
        ) from exc

    payload = discover_graph_payload(ticker.upper(), mode="all", limit=limit)
    payload["backtest"] = {"start": DEFAULT_BACKTEST_START}
    payload.setdefault("created_at", _now())
    return payload


def write_discovery(session: Path, discovery_data: dict) -> None:
    (session / "discovery.json").write_text(
        json.dumps(discovery_data, indent=2),
        encoding="utf-8",
    )


def write_readiness(session: Path, readiness_report: dict) -> None:
    (session / READINESS_FILENAME).write_text(
        json.dumps(readiness_report, indent=2),
        encoding="utf-8",
    )


def refresh_data_readiness(
    *,
    session: Path,
    discovery_data: dict,
    backtest_start: str,
) -> dict | None:
    """Compute the edge-owned data readiness report for a live discovery payload."""
    fd, temp_name = tempfile.mkstemp(dir=session, suffix="-discovery.json")
    os.close(fd)
    discovery_path = Path(temp_name)
    discovery_path.write_text(json.dumps(discovery_data, indent=2), encoding="utf-8")
    try:
        report = run_edge_verify_data(
            session=session,
            discovery_path=discovery_path,
            backtest_start=backtest_start,
        )
    except RuntimeError:
        discovery_path.unlink(missing_ok=True)
        return None
    finally:
        discovery_path.unlink(missing_ok=True)
    return report


def run_edge_verify_data(
    *,
    session: Path,
    discovery_path: Path,
    backtest_start: str,
) -> dict | None:
    """Run edge verify-data against a discovery payload and parse the structured report."""
    python_bin = resolve_default_python_bin(session)
    workspace_root = find_workspace_root(session)
    runtime_env = (
        build_workspace_runtime_env(workspace_root)
        if workspace_root is not None
        else None
    )
    fd, temp_name = tempfile.mkstemp(suffix="-verify-data.json")
    os.close(fd)
    output_path = Path(temp_name)
    output_path.unlink(missing_ok=True)
    command = [
        python_bin,
        "-m",
        "causal_edge.cli",
        "verify-data",
        "--discovery-json",
        str(discovery_path),
        "--start",
        backtest_start,
        "--output-json",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        cwd=session,
        capture_output=True,
        text=True,
        env=runtime_env,
    )
    if not output_path.exists():
        if "No module named" in (completed.stderr or "") or "No such command" in (
            completed.stderr or completed.stdout or ""
        ):
            return None
        raise RuntimeError(
            "Abel-edge verify-data did not produce a readiness report. "
            "Upgrade the workspace runtime before depending on discovery readiness."
        )
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    finally:
        output_path.unlink(missing_ok=True)


def init_branch_dir(session: Path, branch_id: str) -> Path:
    with SessionLock(session):
        discovery = load_discovery(session)
        readiness = load_readiness(session)
        branch = session / "branches" / branch_id
        branch.mkdir(parents=True, exist_ok=True)
        (branch / "rounds").mkdir(parents=True, exist_ok=True)
        (branch / "outputs").mkdir(parents=True, exist_ok=True)
        write_tsv_header(branch / "results.tsv", RESULTS_HEADER)
        if not branch_state_path(branch).exists():
            write_branch_state(branch, {})
        if not branch_spec_path(branch).exists():
            write_branch_spec(
                branch,
                build_default_branch_spec(
                    branch=branch,
                    discovery=discovery,
                    readiness=readiness,
                ),
            )
        engine = branch / "engine.py"
        if not engine.exists():
            engine.write_text(
                render_default_engine_template(discovery, readiness, session),
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


def prepare_branch_inputs(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    workspace_root = find_workspace_root(branch)
    discovery = load_discovery(session)
    branch_spec = load_branch_spec(branch)
    if not branch_spec:
        raise RuntimeError(f"Missing {BRANCH_SPEC_FILENAME} under {branch}")

    target = str(branch_spec.get("target") or discovery.get("ticker") or "").strip().upper()
    if not target:
        raise RuntimeError("Branch spec is missing a target ticker.")
    selected_drivers = [
        str(item).strip().upper()
        for item in (branch_spec.get("selected_drivers") or [])
        if str(item).strip()
    ]
    symbols = [target]
    for ticker in selected_drivers:
        if ticker not in symbols:
            symbols.append(ticker)

    requested_start = str(
        branch_spec.get("requested_start") or _get_backtest_start(discovery)
    ).strip()
    advisory_lines = branch_runtime_advisory_lines(
        branch_requested_start=requested_start,
        discovery=discovery,
        readiness=load_readiness(session),
    )
    dependencies = branch_dependencies_payload(
        branch=branch,
        branch_spec=branch_spec,
        target=target,
        selected_drivers=selected_drivers,
        requested_start=requested_start,
    )

    python_bin = args.python_bin or resolve_default_python_bin(branch)
    output_path = dependencies_path(branch)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_env = (
        build_workspace_runtime_env(workspace_root)
        if workspace_root is not None
        else None
    )
    command = [
        python_bin,
        "-m",
        "causal_edge.cli",
        "warm-cache",
        "--adapter",
        "abel",
        "--start",
        requested_start,
        "--timeframe",
        str((branch_spec.get("data_requirements") or {}).get("timeframe") or "1d"),
        "--limit",
        str(args.cache_limit),
        "--output-json",
        str(output_path),
    ]
    for symbol in symbols:
        command.extend(["--symbol", symbol])
    completed = subprocess.run(
        command,
        cwd=session,
        capture_output=True,
        text=True,
        env=runtime_env,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if not output_path.exists():
        raise RuntimeError(
            "Abel-edge warm-cache did not produce dependencies output. "
            "Fix the runtime error above before continuing."
        )
    cache_payload = json.loads(output_path.read_text(encoding="utf-8"))
    dependencies["cache"] = cache_payload
    output_path.write_text(json.dumps(dependencies, indent=2), encoding="utf-8")

    with SessionLock(session):
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "branch_prepared",
                "branch_id": branch.name,
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": (
                    f"Prepared branch inputs for {branch.name} with {len(symbols)} symbol(s)"
                ),
                "artifact_path": str(output_path.relative_to(session)),
            },
        )
        render_session(session)
    print(f"Prepared branch inputs: {output_path.relative_to(session)}")
    print(f"  target: {target}")
    print(f"  selected_drivers: {len(selected_drivers)}")
    for line in advisory_lines:
        print(f"  {line}")
    print("")
    print("Next:")
    print(f"  abel-alpha debug-branch --branch {branch}")
    print(f"  abel-alpha run-branch --branch {branch} -d \"baseline\"")
    return completed.returncode


def branch_requested_start(branch: Path, discovery: dict) -> str:
    branch_spec = load_branch_spec(branch)
    requested = str(branch_spec.get("requested_start") or "").strip()
    if requested:
        return requested
    return _get_backtest_start(discovery)


def promote_branch_bundle(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    rows = read_tsv_rows(branch / "results.tsv")
    latest = rows[-1] if rows else {}
    branch_spec = load_branch_spec(branch)
    if not branch_spec:
        raise RuntimeError(f"Missing {BRANCH_SPEC_FILENAME} under {branch}")
    if args.output_dir:
        destination = resolve_workspace_arg_path(args.output_dir).resolve()
    else:
        destination = session / "promotions" / branch.name
    destination.mkdir(parents=True, exist_ok=True)

    shutil.copy2(branch / "engine.py", destination / "engine.py")
    shutil.copy2(branch_spec_path(branch), destination / BRANCH_SPEC_FILENAME)
    if dependencies_path(branch).exists():
        shutil.copy2(dependencies_path(branch), destination / DEPENDENCIES_FILENAME)

    bundle_readme = build_promotion_bundle_readme(
        branch=branch,
        branch_spec=branch_spec,
        latest=latest,
    )
    (destination / "PROMOTION.md").write_text(bundle_readme, encoding="utf-8")

    with SessionLock(session):
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "branch_promoted",
                "branch_id": branch.name,
                "round_id": latest.get("round_id", ""),
                "mode": latest.get("mode", ""),
                "verdict": latest.get("verdict", ""),
                "decision": latest.get("decision", ""),
                "description": f"Created promotion bundle for {branch.name}",
                "artifact_path": str(destination.relative_to(session)),
            },
        )
        render_session(session)
    print(f"Promotion bundle: {destination}")
    print("")
    print("Included:")
    print(f"  {destination / 'engine.py'}")
    print(f"  {destination / BRANCH_SPEC_FILENAME}")
    if (destination / DEPENDENCIES_FILENAME).exists():
        print(f"  {destination / DEPENDENCIES_FILENAME}")
    print(f"  {destination / 'PROMOTION.md'}")
    return 0


def run_branch_round(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    workspace_root = find_workspace_root(branch)
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    if not dependencies_path(branch).exists():
        print(
            "Branch inputs have not been prepared yet. "
            "Run `abel-alpha prepare-branch --branch ...` before recording a round.",
            file=sys.stderr,
        )
        return 2
    backtest_start = branch_requested_start(branch, discovery)
    advisory_lines = branch_runtime_advisory_lines(
        branch_requested_start=backtest_start,
        discovery=discovery,
        readiness=readiness,
    )
    warning = build_readiness_warning(readiness)
    if branch_uses_default_scaffold(branch, discovery, readiness, session) and not args.allow_untouched_template:
        print(
            "Refusing to record a round from the untouched default engine scaffold. "
            "Edit engine.py first, or use `abel-alpha debug-branch` while wiring the first real signal.",
            file=sys.stderr,
        )
        for line in advisory_lines:
            print(f"Runtime context: {line}", file=sys.stderr)
        if warning and backtest_start == _get_backtest_start(discovery):
            print(f"Readiness warning: {warning}", file=sys.stderr)
        for line in readiness_recommendation_lines(readiness):
            print(f"Coverage hint: {line}", file=sys.stderr)
        return 2
    rows = read_tsv_rows(branch / "results.tsv")
    round_id = f"round-{len(rows) + 1:03d}"
    effective_hypothesis, hypothesis_source = resolve_branch_hypothesis(
        branch,
        rows,
        args.hypothesis,
    )
    result_path = branch / "outputs" / f"{round_id}-edge-result.json"
    report_path = branch / "outputs" / f"{round_id}-edge-validation.md"
    handoff_path = branch / "outputs" / f"{round_id}-edge-handoff.json"
    context_path = branch / "outputs" / f"{round_id}-alpha-context.json"
    context_path.write_text(
        json.dumps(
            build_branch_context(
                branch=branch,
                session=session,
                discovery=discovery,
                readiness=readiness,
                round_id=round_id,
                backtest_start=backtest_start,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    emit_readiness_warning = False
    session_start = _get_backtest_start(discovery)
    if warning and backtest_start == session_start:
        with SessionLock(session):
            emit_readiness_warning = should_emit_readiness_warning(session, readiness)
    for line in advisory_lines:
        print(f"Runtime context: {line}", file=sys.stderr)
    if warning and emit_readiness_warning:
        print(
            f"Warning: {warning}",
            file=sys.stderr,
        )
        for line in readiness_recommendation_lines(readiness):
            print(f"Coverage hint: {line}", file=sys.stderr)

    python_bin = args.python_bin or resolve_default_python_bin(branch)
    command = [
        python_bin,
        "-m",
        "causal_edge.cli",
        "evaluate",
        "--workdir",
        str(branch),
        "--output-json",
        str(result_path),
        "--output-md",
        str(report_path),
        "--output-handoff",
        str(handoff_path),
        "--start",
        backtest_start,
        "--context-json",
        str(context_path),
    ]
    runtime_env = (
        build_workspace_runtime_env(workspace_root)
        if workspace_root is not None
        else None
    )
    completed = subprocess.run(
        command,
        cwd=session,
        capture_output=True,
        text=True,
        env=runtime_env,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if not result_path.exists():
        print(
            "Abel-edge did not produce the expected result JSON. "
            "Check the command output above and rerun after fixing the evaluation error.",
            file=sys.stderr,
        )
        if workspace_root is not None:
            print(
                f"Alpha expected workspace auth at {resolve_workspace_env_file(workspace_root)} "
                "and exported it through ABEL_AUTH_ENV_FILE for this run.",
                file=sys.stderr,
            )
        return completed.returncode or 1
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"Abel-edge wrote an unreadable result JSON at {result_path}: {exc}",
            file=sys.stderr,
        )
        return completed.returncode or 1
    emit_missing_hypothesis_warning = False
    if not has_explicit_hypothesis(effective_hypothesis):
        with SessionLock(session):
            emit_missing_hypothesis_warning = should_emit_missing_hypothesis_warning(branch)
    if emit_missing_hypothesis_warning:
        print(
            "Warning: recording a round without an explicit hypothesis. "
            "State the causal claim, expected sign, and invalidation condition before the next round.",
            file=sys.stderr,
        )
    decision = alpha_decision(rows, result, session=session)

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
            hypothesis=effective_hypothesis,
            expected_signal=args.expected_signal,
            summary=args.summary,
            next_step=args.next_step,
            actions=args.action + [f"hypothesis_source={hypothesis_source}"],
            context_mode="injected",
            context_path=str(context_path.relative_to(session)),
            result_path=str(result_path.relative_to(session)),
            report_path=str(report_path.relative_to(session)),
            handoff_path=str(handoff_path.relative_to(session)),
        ),
        encoding="utf-8",
    )

    metrics = result.get("metrics", {})
    with SessionLock(session):
        if has_explicit_hypothesis(effective_hypothesis):
            persist_branch_hypothesis(
                branch,
                effective_hypothesis,
                source=hypothesis_source,
            )
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
    print(f"Alpha context: {context_path.relative_to(session)}")
    print(f"Edge result: {result_path.relative_to(session)}")
    print(f"Edge validation: {report_path.relative_to(session)}")
    print(f"Edge handoff: {handoff_path.relative_to(session)}")
    return 0


def debug_branch_run(args: argparse.Namespace) -> int:
    branch = resolve_workspace_arg_path(args.branch).resolve()
    session = branch.parent.parent
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    workspace_root = find_workspace_root(branch)
    backtest_start = branch_requested_start(branch, discovery)
    advisory_lines = branch_runtime_advisory_lines(
        branch_requested_start=backtest_start,
        discovery=discovery,
        readiness=readiness,
    )
    context_path = branch / "outputs" / "debug-alpha-context.json"
    debug_result_path = branch / "outputs" / "debug-edge-result.json"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(
        json.dumps(
            build_branch_context(
                branch=branch,
                session=session,
                discovery=discovery,
                readiness=readiness,
                round_id="debug",
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
        "debug-evaluate",
        "--workdir",
        str(branch),
        "--start",
        backtest_start,
        "--context-json",
        str(context_path),
        "--output-json",
        str(debug_result_path),
    ]
    runtime_env = (
        build_workspace_runtime_env(workspace_root)
        if workspace_root is not None
        else None
    )
    completed = subprocess.run(
        command,
        cwd=session,
        capture_output=True,
        text=True,
        env=runtime_env,
    )
    debug_snapshot = build_debug_snapshot(
        completed=completed,
        session=session,
        context_path=context_path,
        debug_result_path=debug_result_path,
        backtest_start=backtest_start,
    )
    with SessionLock(session):
        persist_debug_snapshot(branch, debug_snapshot)
        render_session(session)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    for line in advisory_lines:
        print(f"Runtime context: {line}")
    print(f"Debug context: {context_path.relative_to(session)}")
    if debug_result_path.exists():
        print(f"Debug result: {debug_result_path.relative_to(session)}")
    print("No narrative round was recorded.")
    return completed.returncode


def render_session(session: Path) -> None:
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    branches = load_branches(session)
    for branch in branches:
        render_branch(branch, discovery, readiness, session.name)
    session_readme = build_session_readme(session, discovery, readiness, branches)
    (session / "README.md").write_text(session_readme, encoding="utf-8")


def render_branch(branch: dict, discovery: dict, readiness: dict, exp_id: str) -> None:
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
        build_thesis(branch, discovery, readiness), encoding="utf-8"
    )


def print_status(session: Path) -> None:
    discovery = load_discovery(session)
    readiness = load_readiness(session)
    branches = load_branches(session)
    print(
        f"Session: {session.name} ({discovery.get('ticker', session.parent.name.upper())})"
    )
    print(f"Branches: {len(branches)}")
    print(f"Total rounds: {sum(len(branch['rows']) for branch in branches)}")
    readiness_summary = format_data_readiness_summary(readiness)
    if readiness_summary:
        print(f"Discovery readiness: {readiness_summary}")
        warning = build_readiness_warning(readiness)
        if warning:
            print(f"Readiness warning: {warning}")
        for line in readiness_recommendation_lines(readiness):
            print(f"Coverage hint: {line}")
    leader = select_leader(branches)
    if leader and leader["rows"]:
        latest = leader["rows"][-1]
        latest_note = read_round_note(leader["branch_dir"], latest.get("round_id", ""))
        print(
            "Lead: "
            f"{leader['branch_id']} {latest.get('decision', 'pending')} {latest.get('verdict', 'n/a')} "
            f"{latest.get('score', '?/?')} {latest_note.get('failure_signature', 'unknown')} "
            f"active={latest_note.get('signal_activity', 'n/a')}"
        )
    for branch in branches:
        latest = branch["rows"][-1] if branch["rows"] else {}
        latest_note = (
            read_round_note(branch["branch_dir"], latest.get("round_id", "")) if latest else {}
        )
        if not latest_note:
            latest_note = latest_debug_snapshot(branch["branch_dir"])
        branch_hypothesis = current_branch_hypothesis(branch["branch_dir"], branch["rows"])
        keep_count = sum(1 for row in branch["rows"] if row.get("decision") == "keep")
        discard_count = sum(
            1 for row in branch["rows"] if row.get("decision") == "discard"
        )
        print(
            f"  {branch['branch_id']:20s} rounds={len(branch['rows']):2d} keep={keep_count:2d} "
            f"discard={discard_count:2d} latest={latest.get('round_id', 'none')} {latest.get('decision', 'pending')} "
            f"{latest.get('verdict', 'n/a')} {latest.get('score', '?/?')} "
            f"{latest_note.get('failure_signature', 'unknown')} "
            f"active={latest_note.get('signal_activity', 'n/a')} "
            f"hypothesis={'yes' if has_explicit_hypothesis(branch_hypothesis) else 'no'}"
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
            "engine.py",
            "results.tsv",
        ):
            if not (branch_dir / required).exists():
                failures.append(f"{branch_dir.name}: missing {required}")
        for row in rows:
            round_id = row.get("round_id", "")
            if not round_id:
                failures.append(f"{branch_dir.name}: row missing round_id")
                continue
            round_note_path = branch_dir / "rounds" / f"{round_id}.md"
            if not round_note_path.exists():
                failures.append(f"{branch_dir.name}: missing round note {round_id}.md")
                note = {}
            else:
                note = read_round_note(branch_dir, round_id)
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
            context_rel = note.get("context_path", "")
            expected_context = branch_dir / "outputs" / f"{round_id}-alpha-context.json"
            if context_rel:
                if not (session / context_rel).exists():
                    failures.append(
                        f"{branch_dir.name}: missing alpha context {context_rel}"
                    )
            elif strict and expected_context.exists():
                failures.append(
                    f"{branch_dir.name}: round note missing context_path for {round_id}"
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
                if "Fill in" in text or "{{" in text or "}}" in text:
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


def select_leader(branches: list[dict]) -> dict | None:
    ranked = ranked_branches(branches)
    return ranked[0] if ranked else None


def ranked_branches(branches: list[dict]) -> list[dict]:
    scored = [branch for branch in branches if branch["rows"]]
    return sorted(scored, key=branch_rank_key, reverse=True)


def branch_rank_key(branch: dict) -> tuple:
    rows = branch["rows"]
    latest = rows[-1]
    note = read_round_note(branch["branch_dir"], latest.get("round_id", ""))
    return (
        decision_rank(latest.get("decision", "")),
        verdict_rank(latest.get("verdict", "")),
        parse_score_ratio(latest.get("score", "")),
        float(latest.get("lo_adj") or 0),
        float(latest.get("sharpe") or 0),
        signal_activity_ratio(note.get("signal_activity", "")),
        len(rows),
    )


def decision_rank(decision: str) -> int:
    return {"keep": 3, "pending": 2, "discard": 1}.get(str(decision or "").strip(), 0)


def verdict_rank(verdict: str) -> int:
    return {"PASS": 3, "FAIL": 2, "ERROR": 1}.get(str(verdict or "").strip().upper(), 0)


def parse_score_ratio(score: str) -> float:
    text = str(score or "").strip()
    if "/" not in text:
        return 0.0
    left, right = text.split("/", 1)
    try:
        numerator = float(left)
        denominator = float(right)
    except ValueError:
        return 0.0
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def signal_activity_ratio(activity: str) -> float:
    text = str(activity or "").strip()
    if "/" not in text:
        return 0.0
    left, right = [part.strip() for part in text.split("/", 1)]
    try:
        active = float(left)
        total = float(right)
    except ValueError:
        return 0.0
    if total <= 0:
        return 0.0
    return active / total


def normalize_hypothesis_text(value: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return (
        "Hypothesis missing. Before the next round, state the causal claim, "
        "expected sign, and invalidation condition explicitly."
    )


def has_explicit_hypothesis(value: str) -> bool:
    text = str(value or "").strip()
    return bool(
        text
        and text != "No hypothesis supplied."
        and not text.startswith("Hypothesis missing.")
    )


def build_session_readme(
    session: Path,
    discovery: dict,
    readiness: dict,
    branches: list[dict],
) -> str:
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
    leader = select_leader(branches)
    debugged_branches = [
        branch for branch in branches if latest_debug_snapshot(branch["branch_dir"])
    ]
    executive = "No validated rounds yet. Start the first branch to establish the session baseline."
    if branches and not any(branch["rows"] for branch in branches):
        executive = f"{len(branches)} branch(es) have been initialized, but no validated rounds exist yet."
        if debugged_branches:
            latest_debug_branch = max(
                debugged_branches,
                key=lambda branch: latest_debug_snapshot(branch["branch_dir"]).get("updated_at", ""),
            )
            debug_note = latest_debug_snapshot(latest_debug_branch["branch_dir"])
            executive += (
                f" {len(debugged_branches)} branch(es) have already been debugged; "
                f"latest blocker is `{latest_debug_branch['branch_id']}` with signature "
                f"`{debug_note.get('failure_signature', 'unknown')}`."
            )
        else:
            executive += (
                f" Edit `{branches[0]['branch_id']}` and use `abel-alpha debug-branch` "
                "before recording the first round."
            )
    if leader and leader["rows"]:
        latest = leader["rows"][-1]
        leader_note = read_round_note(leader["branch_dir"], latest.get("round_id", ""))
        lead_label = "Current KEEP baseline"
        if latest.get("decision") != "keep":
            lead_label = "Current lead candidate (no KEEP baseline yet)"
        executive = (
            f"Session has {len(branches)} branch(es): {len(keep_branches)} keep and {len(discard_branches)} discard. "
            f"{lead_label} is `{leader['branch_id']}` at `{latest.get('round_id', 'none')}` with Lo {float(latest.get('lo_adj') or 0):.3f}, "
            f"Sharpe {float(latest.get('sharpe') or 0):.3f}, PnL {float(latest.get('pnl') or 0):.1f}%, "
            f"failure signature `{leader_note.get('failure_signature', 'unknown')}`, "
            f"active `{leader_note.get('signal_activity', 'n/a')}`."
        )

    branch_lines = (
        "\n".join(
            (
                f"1. `{branch['branch_id']}` - {len(branch['rows'])} rounds, latest "
                f"`{branch['rows'][-1].get('round_id', 'none')}` {branch['rows'][-1].get('decision', 'pending')}"
                if branch["rows"]
                else (
                    f"1. `{branch['branch_id']}` - pending, latest debug "
                    f"`{latest_debug_snapshot(branch['branch_dir']).get('failure_signature', 'not run')}`"
                    if latest_debug_snapshot(branch["branch_dir"])
                    else f"1. `{branch['branch_id']}` - scaffolded, no rounds or debug runs yet"
                )
            )
            for branch in branches
        )
        or "1. `No branches yet.`"
    )

    snapshot_lines = (
        "\n".join(
            line
            for branch in branches
            for line in (
                [build_branch_snapshot_line(branch)]
                if branch["rows"]
                else (
                    [
                        (
                            f"1. `{branch['branch_id']}` -> `debug` / "
                            f"`{latest_debug_snapshot(branch['branch_dir']).get('verdict', 'ERROR')}` / "
                            f"signature `{latest_debug_snapshot(branch['branch_dir']).get('failure_signature', 'unknown')}`. "
                            f"Why: `{current_branch_hypothesis(branch['branch_dir'], branch['rows']) or latest_debug_snapshot(branch['branch_dir']).get('summary', 'not recorded')}`. "
                            f"Next: `{latest_debug_snapshot(branch['branch_dir']).get('next_step', 'Fix the engine and rerun debug.')}`"
                        )
                    ]
                    if latest_debug_snapshot(branch["branch_dir"])
                    else []
                )
            )
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

## Discovery Readiness

{render_discovery_readiness_section(readiness)}

## Selection Narrative

This session tracks {len(branches)} branch(es). Current outcomes: {len(keep_branches)} keep, {len(discard_branches)} discard, {len(branches) - len(keep_branches) - len(discard_branches)} pending.

{render_selection_narrative(branches)}

## Branches

{branch_lines}

## Branch Outcome Snapshot

{snapshot_lines}

## Recent Activity

{activity_lines}

## Next Step

{session_next_step(session, branches, discovery, readiness)}
"""


def build_branch_readme(branch: dict, latest_note: dict[str, str], exp_id: str) -> str:
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    debug_note = latest_debug_snapshot(branch["branch_dir"])
    diagnostics_note = latest_note or debug_note
    keep_rows = [row for row in rows if row.get("decision") == "keep"]
    branch_hypothesis = current_branch_hypothesis(branch["branch_dir"], rows)
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
- current_status: `{latest.get("decision", "debugged" if debug_note else "scaffolded" if not rows else "exploring")}`
- total_rounds: `{len(rows)}`
- latest_round: `{latest.get("round_id", "debug" if debug_note else "none")}`
- validation_status: `{latest.get("verdict", diagnostics_note.get("verdict", "not_validated"))}`

## Branch Thesis

See `branch.yaml` for the explicit branch inputs and `thesis.md` for the branch hypothesis.

## Latest Conclusion

- decision: `{latest.get("decision", "pending")}`
- summary: `{latest.get("description", diagnostics_note.get("summary", "No rounds recorded yet."))}`
- next_step: `{diagnostics_note.get("next_step", "Edit engine.py and use `abel-alpha debug-branch` before the first recorded round.")}`

## Latest Diagnostics

- failure_signature: `{diagnostics_note.get("failure_signature", "not recorded")}`
- runtime_stage: `{diagnostics_note.get("runtime_stage", "not recorded")}`
- signal_activity: `{diagnostics_note.get("signal_activity", "not recorded")}`
- diagnostic_hints: `{diagnostics_note.get("diagnostic_hints", "not recorded")}`

## Latest Artifacts

- alpha_context_mode: `{diagnostics_note.get("context_mode", "not recorded")}`
- alpha_context: `{diagnostics_note.get("context_path", "not recorded")}`
- branch_spec: `{BRANCH_SPEC_FILENAME}`
- prepared_inputs: `{"inputs/" + DEPENDENCIES_FILENAME if dependencies_path(branch["branch_dir"]).exists() else "not prepared"}`
- edge_result: `{diagnostics_note.get("result_path", latest.get("result_path", "not recorded"))}`
- edge_report: `{diagnostics_note.get("report_path", latest.get("report_path", "not recorded"))}`
- edge_handoff: `{diagnostics_note.get("handoff_path", latest.get("handoff_path", "not recorded"))}`

## Decision Rationale

1. latest_hypothesis: `{branch_hypothesis or latest_note.get("hypothesis", "not recorded")}`
1. latest_summary: `{diagnostics_note.get("summary", latest.get("description", "not recorded"))}`
1. latest_failures: `{diagnostics_note.get("failures", "none")}`
1. hypothesis_status: `{"explicit" if has_explicit_hypothesis(branch_hypothesis) else "needs work"}`

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


def build_promotion_bundle_readme(
    *,
    branch: Path,
    branch_spec: dict,
    latest: dict[str, str],
) -> str:
    selected = format_simple_nodes(branch_spec.get("selected_drivers") or [], limit=12)
    return f"""# {branch.name} Promotion Bundle

generated by Abel-alpha narrative layer

## Summary

- branch_id: `{branch.name}`
- target: `{branch_spec.get("target", "unknown")}`
- requested_start: `{branch_spec.get("requested_start", "unknown")}`
- overlap_mode: `{branch_spec.get("overlap_mode", "target_only")}`
- selected_drivers: `{selected}`
- latest_round: `{latest.get("round_id", "none")}`
- latest_decision: `{latest.get("decision", "n/a")}`
- latest_verdict: `{latest.get("verdict", "n/a")}`
- latest_score: `{latest.get("score", "n/a")}`

## Included Files

- `engine.py`: branch implementation snapshot
- `{BRANCH_SPEC_FILENAME}`: explicit branch definition
- `{DEPENDENCIES_FILENAME}`: prepared input/cache dependency view when available

## Next Step

Use this bundle as the handoff input for promotion into a formal strategy implementation.
"""


def build_thesis(branch: dict, discovery: dict, readiness: dict) -> str:
    rows = branch["rows"]
    latest = rows[-1] if rows else {}
    hypothesis = current_branch_hypothesis(branch["branch_dir"], rows)
    branch_spec = load_branch_spec(branch["branch_dir"])
    latest_note = (
        read_round_note(branch["branch_dir"], latest.get("round_id", ""))
        if latest
        else {}
    )
    parents = format_discovery_nodes(discovery.get("parents", []), limit=5)
    blanket = format_discovery_nodes(discovery.get("blanket_new", []), limit=5)
    usable = format_simple_nodes(readiness_usable_tickers(readiness), limit=8)
    start_covered = format_simple_nodes(readiness_start_covered_tickers(readiness), limit=8)
    selected = format_simple_nodes(branch_spec.get("selected_drivers") or [], limit=8)
    return f"""# {branch["branch_id"]} Thesis

generated by Abel-alpha narrative layer

## Alpha Source

Branch `{branch["branch_id"]}` currently assumes: `{hypothesis or latest.get("description", "Initial branch hypothesis not recorded yet")}`.
Latest decision is `{latest.get("decision", "pending")}` with verdict `{latest.get("verdict", "not_validated")}`.

## Hypothesis Checklist

- causal claim: `state what should drive the target and why`
- expected sign / regime: `state when the signal should be long, short, or flat`
- invalidation condition: `state what evidence would make this branch unconvincing`

## Input Universe

- target: `{discovery.get("ticker", branch["ticker"])}`
- discovery_source: `{discovery.get("source", "unknown")}`
- direct_parents: `{parents}`
- blanket_candidates: `{blanket}`
- selected_drivers: `{selected}`
- usable_tickers: `{usable}`
- start_covered_tickers: `{start_covered}`

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


def format_simple_nodes(items: list[object], *, limit: int = 8) -> str:
    rendered = [str(item).strip() for item in items[:limit] if str(item).strip()]
    return ", ".join(rendered) or "none recorded"


def readiness_results(readiness: dict) -> list[dict]:
    results = readiness.get("results") or []
    return [item for item in results if isinstance(item, dict)]


def readiness_usable_tickers(readiness: dict) -> list[str]:
    return [
        str(item.get("ticker") or "").strip().upper()
        for item in readiness_results(readiness)
        if item.get("usable")
    ]


def readiness_start_covered_tickers(readiness: dict) -> list[str]:
    return [
        str(item.get("ticker") or "").strip().upper()
        for item in readiness_results(readiness)
        if item.get("covers_requested_start")
    ]


def format_data_readiness_summary(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    requested = report.get("requested_window") or {}
    probe = report.get("probe") or {}
    probe_limit = probe.get("limit")
    return (
        f"{summary.get('start_covered_count', 0)} start-covered, "
        f"{summary.get('partial_window_count', 0)} partial, "
        f"{summary.get('no_data_count', 0)} no-data, "
        f"{summary.get('error_count', 0)} error "
        f"(start {requested.get('start', 'latest')}, probe {probe_limit or 'n/a'})"
    )


def render_target_boundary_line(readiness: dict) -> str:
    report = readiness or {}
    target_boundary = report.get("target_boundary") or {}
    classification = target_boundary.get("classification")
    if not classification:
        return "not recorded"
    observed_first = target_boundary.get("observed_first_timestamp")
    observed_last = target_boundary.get("observed_last_timestamp")
    parts = [str(classification)]
    if observed_first:
        parts.append(f"observed_first={observed_first}")
    if observed_last:
        parts.append(f"observed_last={observed_last}")
    return ", ".join(parts)


def render_readiness_guidance(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    requested_start = str((report.get("requested_window") or {}).get("start") or "latest")
    coverage_hints = report.get("coverage_hints") or {}
    target_safe = coverage_hints.get("target_safe_start")
    dense_overlap = coverage_hints.get("dense_overlap_hint_start")
    if target_safe and dense_overlap and target_safe != dense_overlap:
        return (
            f"Desired start remains {requested_start}. Target-first research can begin around "
            f"{target_safe}, while denser driver overlap appears around {dense_overlap} if the branch needs it."
        )
    if target_safe and target_safe != requested_start:
        return (
            f"Desired start remains {requested_start}. Target-safe coverage is currently observed from "
            f"{target_safe}; later driver overlap is optional, not mandatory."
        )
    if dense_overlap:
        return (
            f"Desired start remains {requested_start}. Dense overlap is hinted around {dense_overlap}, "
            "but target-first branches may continue earlier if they tolerate partial driver coverage."
        )
    return (
        f"Desired start remains {requested_start}. Use readiness as a coverage profile, not as a mandatory "
        "research-design verdict."
    )


def render_discovery_readiness_section(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return "`No data readiness report recorded yet. Run live discovery again after edge verification is available.`"
    start_covered = ", ".join(readiness_start_covered_tickers(readiness)) or "none"
    usable = ", ".join(readiness_usable_tickers(readiness)) or "none"
    lines = [
        f"- summary: `{format_data_readiness_summary(readiness)}`\n"
        f"- target_boundary: `{render_target_boundary_line(readiness)}`\n"
        f"- usable_tickers: `{usable}`\n"
        f"- start_covered_tickers: `{start_covered}`"
    ]
    warning = build_readiness_warning(readiness)
    if warning:
        lines.append(f"- warning: `{warning}`")
    for line in readiness_recommendation_lines(readiness):
        lines.append(f"- coverage_hint: `{line}`")
    guidance = render_readiness_guidance(readiness)
    if guidance:
        lines.append(f"- interpretation: `{guidance}`")
    return "\n".join(lines)


def build_readiness_warning(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    if int(summary.get("usable_count", 0) or 0) == 0:
        return "No usable tickers were confirmed for the requested backtest window."
    requested_start = (report.get("requested_window") or {}).get("start", "latest")
    target_boundary = report.get("target_boundary") or {}
    classification = target_boundary.get("classification")
    observed_first = target_boundary.get("observed_first_timestamp")
    if classification == "confirmed_after_requested_start":
        return (
            "Target history begins after the session requested backtest_start "
            f"{requested_start}. Treat this as a session-level coverage note; branches may still "
            "choose narrower explicit starts intentionally."
        )
    if classification == "unknown_probe_truncated":
        observed_suffix = (
            f" The deepest observed target history begins at {observed_first}."
            if observed_first
            else ""
        )
        return (
            "Target coverage before the requested backtest_start "
            f"{requested_start} is not yet confirmed.{observed_suffix}"
        )
    if int(summary.get("start_covered_count", 0) or 0) <= 0:
        return (
            "Discovered drivers are only partially available from the session requested start "
            f"{requested_start}. Target-first research can still continue; use coverage hints only "
            "if your branch depends on strict overlap."
        )
    return ""


def readiness_recommendation_lines(readiness: dict) -> list[str]:
    report = readiness or {}
    coverage_hints = report.get("coverage_hints") or {}
    lines: list[str] = []
    target_start = coverage_hints.get("target_safe_start")
    common_start = coverage_hints.get("dense_overlap_hint_start")
    if target_start:
        lines.append(f"target_safe={target_start}")
    if common_start:
        lines.append(f"dense_overlap={common_start}")
    return lines


def branch_runtime_advisory_lines(
    *,
    branch_requested_start: str,
    discovery: dict,
    readiness: dict,
) -> list[str]:
    session_requested_start = _get_backtest_start(discovery)
    coverage_hints = (readiness or {}).get("coverage_hints") or {}
    lines = [f"branch_requested_start={branch_requested_start}"]
    if branch_requested_start != session_requested_start:
        lines.append(
            f"session_backtest_start={session_requested_start} (session-level advisory only)"
        )
    target_safe = coverage_hints.get("target_safe_start")
    if target_safe:
        lines.append(f"target_safe_hint={target_safe}")
    dense_overlap = coverage_hints.get("dense_overlap_hint_start")
    if dense_overlap:
        lines.append(
            f"dense_overlap_hint={dense_overlap} (advisory only; not required unless the branch needs strict overlap)"
        )
    return lines


def render_selection_narrative(branches: list[dict]) -> str:
    ranked = ranked_branches(branches)[:3]
    if not ranked:
        return "No branch rankings yet because no validated rounds have been recorded."
    lines = []
    for index, branch in enumerate(ranked, start=1):
        latest = branch["rows"][-1]
        note = read_round_note(branch["branch_dir"], latest.get("round_id", ""))
        reason = (
            current_branch_hypothesis(branch["branch_dir"], branch["rows"])
            or note.get("hypothesis")
            or latest.get("description", "No explicit hypothesis recorded yet.")
        )
        label = "lead" if index == 1 else "runner-up"
        lines.append(
            f"{index}. `{branch['branch_id']}` ({label}) -> "
            f"`{latest.get('decision', 'pending')}` / `{latest.get('verdict', 'n/a')}` / "
            f"`{latest.get('score', '?/?')}` / signature `{note.get('failure_signature', 'unknown')}`. "
            f"Reasoning: `{reason}`"
        )
    return "\n".join(lines)


def alpha_decision(rows: list[dict[str, str]], result: dict, *, session: Path | None = None) -> str:
    if result.get("verdict") != "PASS":
        return "discard"

    baseline = None
    for row in reversed(rows):
        if row.get("decision") == "keep":
            baseline = row
            break
    if baseline is None:
        return "keep"

    profile_name = str(result.get("profile") or "").strip()
    if not profile_name:
        raise RuntimeError(
            "edge evaluation did not provide a profile for baseline compare"
        )

    baseline_metrics = {
        "lo_adjusted": float(baseline.get("lo_adj") or 0),
        "position_ic": float(baseline.get("ic") or 0),
        "omega": float(baseline.get("omega") or 0),
        "sharpe": float(baseline.get("sharpe") or 0),
        "total_return": float(baseline.get("pnl") or 0) / 100.0,
        "max_dd": float(baseline.get("max_dd") or 0),
    }

    try:
        from causal_edge.validation.gate_logic import decide_keep_discard
        from causal_edge.validation.metrics import load_profile

        decision = decide_keep_discard(
            result.get("metrics", {}),
            baseline_metrics,
            load_profile(profile_name),
        )
    except ImportError:
        if session is None:
            raise
        decision = alpha_decision_with_runtime(
            session=session,
            current_metrics=result.get("metrics", {}),
            baseline_metrics=baseline_metrics,
            profile_name=profile_name,
        )
    return "keep" if decision == "KEEP" else "discard"


def alpha_decision_with_runtime(
    *,
    session: Path,
    current_metrics: dict,
    baseline_metrics: dict,
    profile_name: str,
) -> str:
    workspace_root = find_workspace_root(session)
    if workspace_root is None:
        raise RuntimeError(
            "Cannot resolve workspace runtime for baseline comparison."
        )
    manifest = load_workspace_manifest(workspace_root)
    python_path = resolve_runtime_python(workspace_root, manifest)
    payload = {
        "current_metrics": current_metrics,
        "baseline_metrics": baseline_metrics,
        "profile_name": profile_name,
    }
    script = (
        "import json, sys\n"
        "from causal_edge.validation.gate_logic import decide_keep_discard\n"
        "from causal_edge.validation.metrics import load_profile\n"
        "payload = json.loads(sys.stdin.read())\n"
        "decision = decide_keep_discard(\n"
        "    payload['current_metrics'],\n"
        "    payload['baseline_metrics'],\n"
        "    load_profile(payload['profile_name']),\n"
        ")\n"
        "print(decision)\n"
    )
    completed = subprocess.run(
        [str(python_path), "-c", script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip() or "unknown error"
        raise RuntimeError(
            f"Workspace runtime could not compare against the KEEP baseline: {detail}"
        )
    return completed.stdout.strip() or "DISCARD"


def build_branch_context(
    *,
    branch: Path,
    session: Path,
    discovery: dict,
    readiness: dict,
    round_id: str,
    backtest_start: str,
) -> dict:
    """Build the structured context passed into causal-edge evaluate."""
    workspace_root = find_workspace_root(branch)
    branch_spec = load_branch_spec(branch)
    dependencies = {}
    if dependencies_path(branch).exists():
        dependencies = json.loads(dependencies_path(branch).read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "workspace_root": str(workspace_root) if workspace_root is not None else None,
        "exp_id": session.name,
        "branch_id": branch.name,
        "round_id": round_id,
        "session_dir": str(session.resolve()),
        "branch_dir": str(branch.resolve()),
        "outputs_dir": str((branch / "outputs").resolve()),
        "branch_spec_path": str(branch_spec_path(branch).resolve()),
        "dependencies_path": str(dependencies_path(branch).resolve()),
        "discovery_path": str((session / "discovery.json").resolve()),
        "readiness_path": str((session / READINESS_FILENAME).resolve()),
        "ticker": discovery.get("ticker", session.parent.name.upper()),
        "backtest_start": backtest_start,
        "branch_spec": branch_spec,
        "dependencies": dependencies,
        "discovery": discovery,
        "readiness": readiness,
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
        current_branch_hypothesis(branch["branch_dir"], rows)
        or note.get("failures")
        or latest.get("description", "")
    )
    return (
        f"1. `{branch['branch_id']}` -> `{latest.get('decision', 'pending')}` after {len(rows)} round(s). "
        f"Why: `{reason or 'not recorded'}`. Trend: Lo {float(first.get('lo_adj') or 0):.3f} -> {float(latest.get('lo_adj') or 0):.3f}, "
        f"Sharpe {float(first.get('sharpe') or 0):.3f} -> {float(latest.get('sharpe') or 0):.3f}, "
        f"PnL {float(first.get('pnl') or 0):.1f}% -> {float(latest.get('pnl') or 0):.1f}%, "
        f"signature `{note.get('failure_signature', 'unknown')}`, active `{note.get('signal_activity', 'n/a')}`."
    )


def session_next_step(
    session: Path,
    branches: list[dict],
    discovery: dict,
    readiness: dict,
) -> str:
    leader = select_leader(branches)
    pending = [branch for branch in branches if not branch["rows"]]
    has_historical_keep = any(
        row.get("decision") == "keep"
        for branch in branches
        for row in branch["rows"]
    )
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
    if pending:
        branch = pending[-1]
        debug_note = latest_debug_snapshot(branch["branch_dir"])
        if debug_note:
            return (
                f"Fix `{branch['branch_id']}` after the latest debug blocker "
                f"`{debug_note.get('failure_signature', 'unknown')}` "
                f"({debug_note.get('summary', 'see debug result')}), then rerun "
                f"`abel-alpha debug-branch --branch {branch['branch_dir']}` before recording the first round."
            )
        warning = build_readiness_warning(readiness)
        recommendations = ", ".join(readiness_recommendation_lines(readiness))
        guidance = (
            f"Confirm `{branch['branch_id']}/branch.yaml`, then use "
            f"`abel-alpha debug-branch --branch {branch['branch_dir']}` to wire the first real signal before recording a round."
        )
        if warning:
            suffix = (
                " Also revisit `backtest_start` first with "
                f"`abel-alpha set-backtest-start --session {session} --target-safe` ({recommendations})."
                if recommendations
                else " Also revisit `backtest_start` first with "
                f"`abel-alpha set-backtest-start --session {session} --date YYYY-MM-DD`."
            )
            return guidance + suffix
        return guidance
    if leader and leader["rows"]:
        branch_hypothesis = current_branch_hypothesis(leader["branch_dir"], leader["rows"])
        if not has_explicit_hypothesis(branch_hypothesis):
            return (
                f"Before the next round, add an explicit hypothesis to "
                f"`{leader['branch_id']}/branch.yaml`, then validate the next causal claim."
            )
        if has_historical_keep:
            return (
                f"No branch is currently ending on KEEP, but `{leader['branch_id']}` still carries the strongest "
                "history. Resume it from the latest credible baseline before opening a new sibling branch."
            )
        return (
            f"No KEEP baseline exists yet. Resume `{leader['branch_id']}` first because it is currently the strongest "
            "candidate, or open a sibling branch only if you have a genuinely different causal thesis."
        )
    return "Revise the discarded branches or open a new branch with a different hypothesis before the next validation round."


def latest_recorded_hypothesis(branch: dict) -> str:
    for row in reversed(branch["rows"]):
        note = read_round_note(branch["branch_dir"], row.get("round_id", ""))
        hypothesis = (note.get("hypothesis") or "").strip()
        if has_explicit_hypothesis(hypothesis):
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


def load_readiness(session: Path) -> dict:
    path = session / READINESS_FILENAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def branch_spec_path(branch: Path) -> Path:
    return branch / BRANCH_SPEC_FILENAME


def dependencies_path(branch: Path) -> Path:
    return branch / "inputs" / DEPENDENCIES_FILENAME


def load_branch_spec(branch: Path) -> dict:
    path = branch_spec_path(branch)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def write_branch_spec(branch: Path, payload: dict) -> None:
    branch_spec_path(branch).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def discovery_candidate_tickers(discovery: dict) -> list[str]:
    target = str(discovery.get("ticker") or "").strip().upper()
    ordered: list[str] = []
    for section in ("parents", "blanket_new", "children"):
        for item in discovery.get(section) or []:
            if isinstance(item, dict):
                ticker = str(item.get("ticker") or "").strip().upper()
            else:
                ticker = str(item or "").strip().upper()
            if not ticker or ticker == target or ticker in ordered:
                continue
            ordered.append(ticker)
    return ordered


def suggest_branch_drivers(discovery: dict, readiness: dict, *, limit: int = 5) -> list[str]:
    discovered = discovery_candidate_tickers(discovery)
    usable = set(readiness_usable_tickers(readiness))
    prioritized = [ticker for ticker in discovered if ticker in usable]
    fallback = [ticker for ticker in discovered if ticker not in usable]
    return (prioritized + fallback)[:limit]


def build_default_branch_spec(*, branch: Path, discovery: dict, readiness: dict) -> dict:
    suggested = suggest_branch_drivers(discovery, readiness, limit=5)
    selected = suggested[: min(3, len(suggested))]
    return {
        "version": 1,
        "branch_id": branch.name,
        "target": discovery.get("ticker", branch.parent.parent.parent.name.upper()),
        "hypothesis": "",
        "requested_start": _get_backtest_start(discovery),
        "resolved_start_policy": "requested",
        "overlap_mode": "target_only",
        "selected_drivers": selected,
        "suggested_drivers": suggested,
        "data_requirements": {
            "timeframe": "1d",
            "fields": ["close"],
        },
    }


def branch_dependencies_payload(
    *,
    branch: Path,
    branch_spec: dict,
    target: str,
    selected_drivers: list[str],
    requested_start: str,
) -> dict:
    return {
        "version": 1,
        "branch_id": branch.name,
        "target": target,
        "selected_drivers": selected_drivers,
        "requested_start": requested_start,
        "overlap_mode": branch_spec.get("overlap_mode") or "target_only",
        "data_requirements": branch_spec.get("data_requirements") or {"timeframe": "1d"},
        "prepared_at": _now(),
    }


def branch_state_path(branch: Path) -> Path:
    return branch / BRANCH_STATE_FILENAME


def load_branch_state(branch: Path) -> dict:
    path = branch_state_path(branch)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_branch_state(branch: Path, payload: dict) -> None:
    branch_state_path(branch).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def session_state_path(session: Path) -> Path:
    return session / SESSION_STATE_FILENAME


def load_session_state(session: Path) -> dict:
    path = session_state_path(session)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_session_state(session: Path, payload: dict) -> None:
    session_state_path(session).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def readiness_warning_fingerprint(readiness: dict) -> str:
    report = readiness or {}
    summary = report.get("summary") or {}
    if not summary:
        return ""
    target_boundary = report.get("target_boundary") or {}
    coverage_hints = report.get("coverage_hints") or {}
    payload = {
        "requested_start": (report.get("requested_window") or {}).get("start"),
        "usable_count": summary.get("usable_count"),
        "start_covered_count": summary.get("start_covered_count"),
        "classification": target_boundary.get("classification"),
        "observed_first_timestamp": target_boundary.get("observed_first_timestamp"),
        "target_safe_start": coverage_hints.get("target_safe_start"),
        "dense_overlap_hint_start": coverage_hints.get("dense_overlap_hint_start"),
    }
    return json.dumps(payload, sort_keys=True)


def should_emit_readiness_warning(session: Path, readiness: dict) -> bool:
    warning = build_readiness_warning(readiness)
    if not warning:
        return False
    fingerprint = readiness_warning_fingerprint(readiness)
    if not fingerprint:
        return True
    state = load_session_state(session)
    if state.get("last_readiness_warning_fingerprint") == fingerprint:
        return False
    state["last_readiness_warning_fingerprint"] = fingerprint
    write_session_state(session, state)
    return True


def resolve_backtest_start_request(
    *,
    session: Path,
    explicit_date: str | None,
    use_target_safe: bool,
    use_coverage_hint: bool,
) -> tuple[str, str]:
    if explicit_date:
        return explicit_date, "explicit_date"
    report = load_readiness(session)
    coverage_hints = report.get("coverage_hints") or {}
    if use_target_safe:
        target_safe = coverage_hints.get("target_safe_start")
        if not target_safe:
            raise RuntimeError(
                "No target-safe readiness hint is available for this session."
            )
        return str(target_safe), "target_safe_hint"
    if use_coverage_hint:
        coverage_hint = coverage_hints.get("dense_overlap_hint_start")
        if not coverage_hint:
            raise RuntimeError(
                "No dense-overlap readiness hint is available for this session."
            )
        return str(coverage_hint), "coverage_hint"
    raise RuntimeError("A backtest start selector is required.")


def update_backtest_start(
    *,
    session: Path,
    backtest_start: str,
    source: str,
) -> tuple[dict, dict]:
    discovery = load_discovery(session)
    updated_discovery = dict(discovery)
    updated_discovery["backtest"] = {"start": backtest_start}
    readiness = refresh_data_readiness(
        session=session,
        discovery_data=updated_discovery,
        backtest_start=backtest_start,
    )
    with SessionLock(session):
        write_discovery(session, updated_discovery)
        readiness_path = session / READINESS_FILENAME
        if readiness:
            write_readiness(session, readiness)
        else:
            readiness_path.unlink(missing_ok=True)
        state = load_session_state(session)
        state.pop("last_readiness_warning_fingerprint", None)
        write_session_state(session, state)
        append_tsv_row(
            session / "events.tsv",
            EVENTS_HEADER,
            {
                "timestamp": _now(),
                "event": "backtest_start_updated",
                "branch_id": "",
                "round_id": "",
                "mode": "",
                "verdict": "",
                "decision": "",
                "description": (
                    f"Updated session backtest start to {backtest_start} via {source}"
                ),
                "artifact_path": "discovery.json",
            },
        )
        if readiness:
            append_tsv_row(
                session / "events.tsv",
                EVENTS_HEADER,
                {
                    "timestamp": _now(),
                    "event": "data_readiness_recorded",
                    "branch_id": "",
                    "round_id": "",
                    "mode": "",
                    "verdict": "",
                    "decision": "",
                    "description": (
                        "Refreshed driver data readiness: "
                        f"{format_data_readiness_summary(readiness)}"
                    ),
                    "artifact_path": READINESS_FILENAME,
                },
            )
        render_session(session)
    return updated_discovery, readiness or {}


def current_branch_hypothesis(branch_dir: Path, rows: list[dict[str, str]] | None = None) -> str:
    branch_spec = load_branch_spec(branch_dir)
    spec_hypothesis = str(branch_spec.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(spec_hypothesis):
        return spec_hypothesis
    state = load_branch_state(branch_dir)
    hypothesis = str(state.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(hypothesis):
        return hypothesis
    if rows is None:
        rows = read_tsv_rows(branch_dir / "results.tsv")
    return latest_recorded_hypothesis({"branch_dir": branch_dir, "rows": rows})


def should_emit_missing_hypothesis_warning(branch: Path) -> bool:
    if has_explicit_hypothesis(current_branch_hypothesis(branch)):
        return False
    state = load_branch_state(branch)
    if state.get("missing_hypothesis_warning_emitted"):
        return False
    state["missing_hypothesis_warning_emitted"] = True
    write_branch_state(branch, state)
    return True


def persist_branch_hypothesis(branch: Path, hypothesis: str, *, source: str) -> None:
    branch_spec = load_branch_spec(branch)
    if branch_spec:
        branch_spec["hypothesis"] = hypothesis
        write_branch_spec(branch, branch_spec)
    state = load_branch_state(branch)
    state["hypothesis"] = hypothesis
    state["hypothesis_source"] = source
    state["hypothesis_updated_at"] = _now()
    state["missing_hypothesis_warning_emitted"] = False
    write_branch_state(branch, state)


def resolve_branch_hypothesis(
    branch: Path,
    rows: list[dict[str, str]],
    explicit_hypothesis: str,
) -> tuple[str, str]:
    hypothesis = str(explicit_hypothesis or "").strip()
    if has_explicit_hypothesis(hypothesis):
        return hypothesis, "round_argument"
    branch_spec = load_branch_spec(branch)
    spec_hypothesis = str(branch_spec.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(spec_hypothesis):
        return spec_hypothesis, "branch_yaml"
    state = load_branch_state(branch)
    stored = str(state.get("hypothesis") or "").strip()
    if has_explicit_hypothesis(stored):
        return stored, "branch_state"
    recorded = latest_recorded_hypothesis({"branch_dir": branch, "rows": rows})
    if has_explicit_hypothesis(recorded):
        return recorded, "recorded_round"
    return "", "missing"


def latest_debug_snapshot(branch_dir: Path) -> dict[str, str]:
    state = load_branch_state(branch_dir)
    payload = state.get("last_debug")
    return dict(payload) if isinstance(payload, dict) else {}


def persist_debug_snapshot(branch: Path, payload: dict[str, str]) -> None:
    state = load_branch_state(branch)
    state["last_debug"] = payload
    write_branch_state(branch, state)


def build_debug_snapshot(
    *,
    completed: subprocess.CompletedProcess[str],
    session: Path,
    context_path: Path,
    debug_result_path: Path,
    backtest_start: str,
) -> dict[str, str]:
    result: dict[str, object] = {}
    if debug_result_path.exists():
        try:
            parsed = json.loads(debug_result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            result = parsed
    diagnostics = result.get("diagnostics") or {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    signal = diagnostics.get("signal") or {}
    if not isinstance(signal, dict):
        signal = {}
    failures = [
        str(item).strip()
        for item in (result.get("failures") or [])
        if str(item).strip()
    ]
    hints = [
        str(item).strip()
        for item in (diagnostics.get("hints") or [])
        if str(item).strip()
    ]
    fallback_error = (
        completed.stderr.strip()
        or completed.stdout.strip()
        or "Debug evaluation did not produce a structured result."
    )
    summary = failures[0] if failures else fallback_error.splitlines()[-1]
    next_step = hints[0] if hints else "Fix the blocker in engine.py, then rerun `abel-alpha debug-branch`."
    return {
        "updated_at": _now(),
        "returncode": str(completed.returncode),
        "verdict": str(result.get("verdict") or ("PASS" if completed.returncode == 0 else "ERROR")),
        "summary": summary,
        "failures": "; ".join(failures) or summary,
        "failure_signature": str(diagnostics.get("failure_signature") or "debug_runtime_check"),
        "runtime_stage": str(diagnostics.get("runtime_stage") or "debug_evaluate"),
        "signal_activity": (
            f"{int(signal.get('active_days', 0) or 0)} / {int(signal.get('total_days', 0) or 0)}"
        ),
        "diagnostic_hints": "; ".join(hints) or "none",
        "next_step": next_step,
        "context_mode": "injected",
        "context_path": str(context_path.relative_to(session)),
        "result_path": str(debug_result_path.relative_to(session)) if debug_result_path.exists() else "not recorded",
        "handoff_path": "not recorded",
        "report_path": "not recorded",
        "requested_start": backtest_start,
    }


def render_default_engine_template(discovery: dict, readiness: dict, session: Path) -> str:
    return ENGINE_TEMPLATE.format(
        ticker=discovery.get("ticker", session.parent.name.upper()),
        readiness_warning=build_readiness_warning(readiness) or "none",
        coverage_hints_text=", ".join(readiness_recommendation_lines(readiness)) or "none",
    )


def branch_uses_default_scaffold(
    branch: Path,
    discovery: dict,
    readiness: dict,
    session: Path,
) -> bool:
    engine = branch / "engine.py"
    if not engine.exists():
        return False
    return (
        engine.read_text(encoding="utf-8")
        == render_default_engine_template(discovery, readiness, session)
    )

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
            "failure_signature",
            "runtime_stage",
            "signal_activity",
            "diagnostic_hints",
            "summary",
            "next_step",
            "context_mode",
            "context_path",
            "result_path",
            "report_path",
            "handoff_path",
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
    diagnostics = result.get("diagnostics") or {}
    signal = diagnostics.get("signal") or {}
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
- hypothesis: `{normalize_hypothesis_text(kwargs.get("hypothesis", ""))}`
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

## Diagnostics

- failure_signature: `{diagnostics.get("failure_signature", "unknown")}`
- runtime_stage: `{diagnostics.get("runtime_stage", "unknown")}`
- signal_activity: `{signal.get("active_days", 0)} / {signal.get("total_days", 0)}`
- diagnostic_hints: `{"; ".join(diagnostics.get("hints", [])) or "none"}`

## Artifacts

- context_mode: `{kwargs.get("context_mode", "injected")}`
- context_path: `{kwargs.get("context_path", "not recorded")}`
- result_path: `{kwargs.get("result_path", "not recorded")}`
- report_path: `{kwargs.get("report_path", "not recorded")}`
- handoff_path: `{kwargs.get("handoff_path", "not recorded")}`

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
    workspace_root = find_workspace_root(session)
    if workspace_root is not None:
        try:
            manifest = load_workspace_manifest(workspace_root)
            python_path = resolve_runtime_python(workspace_root, manifest)
        except Exception as exc:
            failures.append(
                f"{branch_name}: unable to resolve workspace runtime for handoff validation: {exc}"
            )
            return
        if python_path.exists():
            validate_edge_handoff_with_runtime(
                python_path=python_path,
                handoff_path=handoff_path,
                branch_name=branch_name,
                failures=failures,
            )
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


def validate_edge_handoff_with_runtime(
    *,
    python_path: Path,
    handoff_path: Path,
    branch_name: str,
    failures: list[str],
) -> None:
    script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from causal_edge.research.handoff import load_strategy_handoff, validate_strategy_handoff\n"
        "handoff_path = Path(sys.argv[1])\n"
        "payload = load_strategy_handoff(handoff_path)\n"
        "reasons = list(validate_strategy_handoff(payload, handoff_path=handoff_path))\n"
        "print(json.dumps({'ok': not reasons, 'reasons': reasons}))\n"
    )
    try:
        completed = subprocess.run(
            [str(python_path), "-c", script, str(handoff_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or str(exc)
        failures.append(
            f"{branch_name}: workspace runtime handoff validation failed: {detail}"
        )
        return
    try:
        payload = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        failures.append(
            f"{branch_name}: workspace runtime returned invalid handoff validation output: {exc}"
        )
        return
    for reason in payload.get("reasons") or []:
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
