"""Shared runtime probes for the installed Abel-edge environment."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run_python_json(
    python_path: Path | str,
    cwd: Path,
    script: str,
) -> dict[str, object]:
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


def probe_causal_edge_import(python_path: Path | str, cwd: Path) -> dict[str, object]:
    """Probe whether the workspace runtime can import causal_edge."""
    return run_python_json(
        python_path,
        cwd,
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


def probe_causal_edge_cli(python_path: Path | str, cwd: Path) -> dict[str, object]:
    """Probe whether the causal-edge CLI entrypoint works in the runtime."""
    return run_python_json(
        python_path,
        cwd,
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


def probe_edge_discovery_json(python_path: Path | str, cwd: Path) -> bool | None:
    """Probe whether the installed edge discover CLI exposes ``--json``."""
    completed = subprocess.run(
        [str(python_path), "-m", "causal_edge.cli", "discover", "--help"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return "--json" in (completed.stdout or "")


def probe_edge_context_json(python_path: Path | str, cwd: Path) -> bool | None:
    """Probe whether the installed edge runtime supports ``context_json``."""
    completed = subprocess.run(
        [
            str(python_path),
            "-c",
            (
                "import inspect\n"
                "from causal_edge.research.evaluate import run_evaluation\n"
                "print('context_json' in inspect.signature(run_evaluation).parameters)\n"
            ),
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() == "True"


def probe_abel_auth(python_path: Path | str, cwd: Path) -> dict[str, object]:
    """Probe whether Abel auth is available to the installed runtime."""
    return run_python_json(
        python_path,
        cwd,
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
