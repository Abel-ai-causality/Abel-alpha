"""Readiness checks for Abel-alpha workspaces."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from abel_alpha.workspace import (
    find_workspace_root,
    load_workspace_manifest,
    resolve_edge_spec,
    resolve_runtime_python,
)


SUCCESS_STATUSES = {"ready", "ready_legacy_edge"}


def run_doctor(start: Path | None = None) -> dict[str, object]:
    """Run workspace, environment, edge, and auth readiness checks."""
    start_path = (start or Path.cwd()).resolve()
    root = find_workspace_root(start_path)
    if root is None:
        return {
            "status": "workspace_missing",
            "workspace_root": None,
            "summary": f"No Abel-alpha workspace found at or above {start_path}",
            "checks": {
                "workspace_manifest": "fail",
                "python_env": "not_run",
                "causal_edge_import": "not_run",
                "causal_edge_cli": "not_run",
                "edge_context_json": "not_run",
                "auth": "not_run",
                "edge_login_fallback": "not_run",
            },
            "next_step": "abel-alpha workspace init <name>",
        }

    try:
        manifest = load_workspace_manifest(root)
    except Exception as exc:
        return {
            "status": "workspace_invalid",
            "workspace_root": str(root),
            "summary": f"Failed to load workspace manifest: {exc}",
            "checks": {
                "workspace_manifest": "fail",
                "python_env": "not_run",
                "causal_edge_import": "not_run",
                "causal_edge_cli": "not_run",
                "edge_context_json": "not_run",
                "auth": "not_run",
                "edge_login_fallback": "not_run",
            },
            "next_step": "fix alpha.workspace.yaml",
        }

    python_path = resolve_runtime_python(root, manifest)
    checks: dict[str, object] = {
        "workspace_manifest": "pass",
        "python_env": "pass" if python_path.exists() else "fail",
        "causal_edge_import": "not_run",
        "causal_edge_cli": "not_run",
        "edge_context_json": "not_run",
        "auth": "not_run",
        "edge_login_fallback": "not_run",
    }

    result: dict[str, object] = {
        "workspace_root": str(root),
        "python_path": str(python_path),
        "edge_install_target": resolve_edge_spec(root, manifest),
        "checks": checks,
    }

    if not python_path.exists():
        result.update(
            {
                "status": "env_missing",
                "summary": f"Workspace python does not exist at {python_path}",
                "next_step": "abel-alpha env init",
            }
        )
        return result

    import_check = run_python_json(
        python_path,
        root,
        """
import json
try:
    import causal_edge  # noqa: F401
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}))
else:
    print(json.dumps({"ok": True}))
""",
    )
    checks["causal_edge_import"] = "pass" if import_check.get("ok") else "fail"
    if not import_check.get("ok"):
        result.update(
            {
                "status": "edge_missing",
                "summary": f"Workspace python cannot import causal_edge: {import_check.get('error', 'unknown error')}",
                "next_step": "abel-alpha env init",
            }
        )
        return result

    cli_check = run_python_json(
        python_path,
        root,
        """
import json
import subprocess
import sys

completed = subprocess.run(
    [sys.executable, "-m", "causal_edge.cli", "version"],
    capture_output=True,
    text=True,
)
print(json.dumps({
    "ok": completed.returncode == 0,
    "stdout": completed.stdout.strip(),
    "stderr": completed.stderr.strip(),
}))
""",
    )
    checks["causal_edge_cli"] = "pass" if cli_check.get("ok") else "fail"

    context_contract_check = run_python_json(
        python_path,
        root,
        """
import inspect
import json

from causal_edge.research.evaluate import run_evaluation

print(json.dumps({
    "ok": "context_json" in inspect.signature(run_evaluation).parameters,
}))
""",
    )
    checks["edge_context_json"] = (
        "pass" if context_contract_check.get("ok") else "fail"
    )

    auth_check = run_python_json(
        python_path,
        root,
        """
import json
import os
from pathlib import Path

from causal_edge.plugins.abel.credentials import (
    _candidate_shared_auth_files,
    _read_env_file,
    normalize_api_key,
)

env_path = Path(".env").resolve()
env_values = _read_env_file(env_path)

env_token = normalize_api_key(
    os.getenv("ABEL_API_KEY")
    or os.getenv("CAP_API_KEY")
)
if env_token:
    print(json.dumps({
        "ok": True,
        "source": "env_var",
        "path": None,
    }))
    raise SystemExit(0)

project_token = normalize_api_key(
    env_values.get("ABEL_API_KEY")
    or env_values.get("CAP_API_KEY")
)
if project_token:
    print(json.dumps({
        "ok": True,
        "source": "workspace_env",
        "path": str(env_path),
    }))
    raise SystemExit(0)

for candidate in _candidate_shared_auth_files(env_path=env_path):
    candidate_values = _read_env_file(candidate)
    shared_token = normalize_api_key(
        candidate_values.get("ABEL_API_KEY") or candidate_values.get("CAP_API_KEY")
    )
    if shared_token:
        print(json.dumps({
            "ok": True,
            "source": "shared_auth_file",
            "path": str(candidate),
        }))
        raise SystemExit(0)

print(json.dumps({
    "ok": False,
    "source": "missing",
    "path": None,
}))
""",
    )
    checks["auth"] = "pass" if auth_check.get("ok") else "fail"
    checks["edge_login_fallback"] = "pass" if checks["causal_edge_cli"] == "pass" else "fail"
    result["auth"] = auth_check

    if not auth_check.get("ok"):
        result.update(
            {
                "status": (
                    "auth_missing"
                    if checks["edge_context_json"] == "pass"
                    else "auth_missing_legacy_edge"
                ),
                "summary": (
                    "Workspace environment is ready, but Abel auth was not detected."
                    if checks["edge_context_json"] == "pass"
                    else "Workspace environment is ready, but Abel auth is missing and the installed "
                    "Abel-edge does not yet support the alpha context contract."
                ),
                "next_step": (
                    "Install causal-abel and complete OAuth, or run "
                    f"`{python_path} -m causal_edge.cli login --json --no-browser`"
                ),
            }
        )
        return result

    if checks["edge_context_json"] == "pass":
        result.update(
            {
                "status": "ready",
                "summary": "Workspace, Python environment, causal-edge, and Abel auth are ready.",
                "next_step": "abel-alpha init-session --ticker <TICKER> --exp-id <session-id>",
            }
        )
    else:
        result.update(
            {
                "status": "ready_legacy_edge",
                "summary": "Workspace is usable, but the installed Abel-edge does not yet support the alpha context contract.",
                "next_step": "Upgrade Abel-edge, then run `abel-alpha init-session --ticker <TICKER> --exp-id <session-id>`.",
            }
        )
    return result


def doctor_exit_code(result: dict[str, object]) -> int:
    """Return the CLI exit code for a doctor result."""
    status = str(result.get("status") or "").strip()
    return 0 if status in SUCCESS_STATUSES else 1


def render_doctor_report(result: dict[str, object]) -> str:
    """Render a human-readable doctor report."""
    lines = [
        f"Status: {result.get('status', 'unknown')}",
        f"Summary: {result.get('summary', '')}",
    ]
    workspace_root = result.get("workspace_root")
    if workspace_root:
        lines.append(f"Workspace root: {workspace_root}")
    python_path = result.get("python_path")
    if python_path:
        lines.append(f"Python path: {python_path}")
    edge_install_target = result.get("edge_install_target")
    if edge_install_target:
        lines.append(f"Edge install target: {edge_install_target}")
    lines.append("Checks:")
    checks = result.get("checks", {})
    if isinstance(checks, dict):
        for key, value in checks.items():
            lines.append(f"  - {key}: {value}")
    auth = result.get("auth")
    if isinstance(auth, dict):
        lines.append(
            "Auth source: "
            f"{auth.get('source', 'unknown')}"
            + (f" ({auth.get('path')})" if auth.get("path") else "")
        )
    lines.append(f"Next step: {result.get('next_step', '')}")
    return "\n".join(lines)


def run_python_json(python_path: Path, cwd: Path, script: str) -> dict[str, object]:
    """Run an inline Python script and parse a JSON payload from stdout."""
    completed = subprocess.run(
        [str(python_path), "-c", script],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "error": completed.stderr.strip() or completed.stdout.strip() or "command failed",
        }
    payload = completed.stdout.strip()
    if not payload:
        return {"ok": False, "error": "no output"}
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid JSON output: {exc}", "stdout": payload}
