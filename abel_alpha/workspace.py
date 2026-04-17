"""Workspace scaffolding and discovery for Abel-alpha."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

MANIFEST_NAME = "alpha.workspace.yaml"
DEFAULT_EDGE_SPEC = "git+https://github.com/Abel-ai-causality/Abel-edge.git@main"


def find_workspace_root(start: Path | None = None) -> Path | None:
    """Return the nearest workspace root at or above ``start``."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / MANIFEST_NAME).exists():
            return candidate
    return None


def is_workspace_root(path: Path) -> bool:
    """Return whether ``path`` contains an Abel-alpha workspace manifest."""
    return (path / MANIFEST_NAME).exists()


def load_workspace_manifest(root: Path) -> dict:
    """Load the workspace manifest from ``root``."""
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"No {MANIFEST_NAME} found under {root}")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid workspace manifest at {manifest_path}")
    return data


def write_workspace_manifest(root: Path, manifest: dict) -> None:
    """Write the workspace manifest back to disk."""
    write_text(root / MANIFEST_NAME, dump_manifest(manifest))


def resolve_workspace_paths(root: Path, manifest: dict | None = None) -> dict[str, Path]:
    """Resolve well-known workspace-relative paths to absolute paths."""
    manifest = manifest or load_workspace_manifest(root)
    paths = manifest.get("paths") or {}
    return {
        "research_root": root / str(paths.get("research_root", "research")),
        "docs_root": root / str(paths.get("docs_root", "docs")),
        "cache_root": root / str(paths.get("cache_root", "cache")),
        "logs_root": root / str(paths.get("logs_root", "logs")),
        "venv": root / str(paths.get("venv", ".venv")),
    }


def resolve_runtime_python(root: Path, manifest: dict | None = None) -> Path:
    """Resolve the configured runtime python path to an absolute path."""
    manifest = manifest or load_workspace_manifest(root)
    runtime = manifest.get("runtime") or {}
    configured = Path(str(runtime.get("python", default_python_path())))
    if configured.is_absolute():
        return configured
    return root / configured


def resolve_edge_spec(root: Path, manifest: dict | None = None) -> str:
    """Resolve the configured Abel-edge install spec for this workspace."""
    manifest = manifest or load_workspace_manifest(root)
    runtime = manifest.get("runtime") or {}
    configured = str(runtime.get("edge_spec") or "").strip()
    return configured or DEFAULT_EDGE_SPEC


def scaffold_workspace(name: str, *, target_root: Path | None = None) -> Path:
    """Create a new Abel-alpha workspace directory with the standard layout."""
    root = (target_root or Path.cwd() / name).resolve()
    if root.exists():
        raise FileExistsError(
            f"Directory '{root}' already exists. Choose a different workspace name or path."
        )

    root.mkdir(parents=True)
    manifest = build_default_manifest(name=name)
    resolved = resolve_workspace_paths(root, manifest)
    for key in ("docs_root", "research_root", "cache_root", "logs_root"):
        resolved[key].mkdir(parents=True, exist_ok=True)

    write_text(root / MANIFEST_NAME, dump_manifest(manifest))
    write_text(root / ".gitignore", render_gitignore())
    write_text(root / ".env.example", render_env_example())
    write_text(root / ".env", "")
    write_text(root / "README.md", render_workspace_readme(name))
    write_text(root / "AGENTS.md", render_workspace_agents())

    return root


def build_default_manifest(name: str) -> dict:
    """Build the default manifest structure for a new workspace."""
    return {
        "version": 1,
        "workspace": {
            "name": name,
            "kind": "abel-alpha",
        },
        "paths": {
            "research_root": "research",
            "docs_root": "docs",
            "cache_root": "cache",
            "logs_root": "logs",
            "venv": ".venv",
        },
        "runtime": {
            "python": default_python_path(),
            "edge_package": "causal-edge",
            "edge_spec": DEFAULT_EDGE_SPEC,
            "auth_strategy": "reuse_causal_abel_first",
        },
        "defaults": {
            "backtest_start": "2020-01-01",
            "discovery_limit": 10,
        },
    }


def dump_manifest(manifest: dict) -> str:
    """Serialize the workspace manifest to YAML."""
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False)


def default_python_path() -> str:
    """Return the default interpreter path inside a local virtual environment."""
    if os.name == "nt":
        return ".venv/Scripts/python.exe"
    return ".venv/bin/python"


def default_activate_command() -> str:
    """Return the default shell command for activating the local virtualenv."""
    if os.name == "nt":
        return ".venv\\Scripts\\Activate.ps1"
    return "source .venv/bin/activate"


def render_workspace_status(root: Path, manifest: dict | None = None) -> str:
    """Render a human-readable workspace status summary."""
    manifest = manifest or load_workspace_manifest(root)
    resolved = resolve_workspace_paths(root, manifest)
    runtime_python = resolve_runtime_python(root, manifest)
    lines = [
        f"Workspace: {manifest.get('workspace', {}).get('name', root.name)}",
        f"Root: {root}",
        f"Manifest: {root / MANIFEST_NAME}",
        f"Research root: {resolved['research_root']}",
        f"Docs root: {resolved['docs_root']}",
        f"Cache root: {resolved['cache_root']}",
        f"Logs root: {resolved['logs_root']}",
        f"Venv: {resolved['venv']}",
        f"Runtime python: {runtime_python}",
        f"Runtime python exists: {'yes' if runtime_python.exists() else 'no'}",
        f"Edge install target: {resolve_edge_spec(root, manifest)}",
    ]
    return "\n".join(lines)


def render_workspace_readme(name: str) -> str:
    """Render the starter README for a new workspace."""
    return f"""# {name}

This is an Abel-alpha research workspace.

## What this workspace is for

- keep exploration sessions under `research/`
- keep plans and iteration notes under `docs/`
- keep disposable caches and logs under `cache/` and `logs/`
- keep workspace defaults in `alpha.workspace.yaml`

## Current first steps

```bash
abel-alpha workspace status
abel-alpha env init
abel-alpha doctor
{default_activate_command()}
abel-alpha init-session --ticker TSLA --exp-id tsla-v1
```

`abel-alpha env init` prepares the local `.venv` and installs `Abel-alpha`
plus `Abel-edge`. By default it installs `Abel-edge` from GitHub `main` until
formal releases exist. If you want live Abel discovery, install `causal-abel`,
complete its OAuth flow, then rerun `abel-alpha init-session --discover`.
"""


def render_workspace_agents() -> str:
    """Render the starter AGENTS guide for a new workspace."""
    return """# AGENTS.md — Abel-alpha Workspace

## I want to...

### Check whether this directory is a valid workspace
```bash
abel-alpha workspace status
abel-alpha doctor
```

### Start a new exploration session
```bash
abel-alpha env init
abel-alpha init-session --ticker TSLA --exp-id tsla-v1
abel-alpha init-branch --session research/tsla/tsla-v1 --branch-id graph-v1
```

### Run one research round
```bash
abel-alpha run-branch --branch research/tsla/tsla-v1/branches/graph-v1 -d "baseline"
```

### Understand the workspace layout
- `alpha.workspace.yaml` is the source of truth for workspace defaults
- `research/` stores sessions, branches, notes, and evaluation outputs
- `docs/` stores plans, summaries, and iteration records
- `cache/` and `logs/` are disposable local runtime artifacts
"""


def render_gitignore() -> str:
    """Render the default workspace gitignore."""
    return """# Abel-alpha workspace
.venv/
.env
cache/
logs/
__pycache__/
*.pyc
"""


def render_env_example() -> str:
    """Render the starter environment example."""
    return """# Optional override for standalone Abel auth fallback
# ABEL_API_KEY=

# Optional: point causal-edge at a shared auth file
# ABEL_AUTH_ENV_FILE=
"""


def write_text(path: Path, content: str) -> None:
    """Write text using UTF-8 encoding."""
    path.write_text(content, encoding="utf-8")
