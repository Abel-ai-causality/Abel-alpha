"""Workspace environment bootstrap helpers for Abel-alpha."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from abel_alpha.workspace import (
    find_workspace_root,
    load_workspace_manifest,
    resolve_runtime_python,
    resolve_workspace_paths,
)


@dataclass
class EnvInitResult:
    """Structured result for `abel-alpha env init`."""

    workspace_root: Path
    venv_path: Path
    python_path: Path
    alpha_source: Path
    edge_source: Path | None
    editable: bool
    created_venv: bool


def init_workspace_env(
    *,
    start: Path | None = None,
    base_python: str | None = None,
    alpha_source: str | Path | None = None,
    edge_source: str | Path | None = None,
    editable: bool = True,
) -> EnvInitResult:
    """Create the workspace venv and install Abel-alpha plus dependencies."""
    workspace_root = find_workspace_root(start)
    if workspace_root is None:
        raise RuntimeError(
            "No Abel-alpha workspace found. Run `abel-alpha workspace init <name>` first."
        )

    manifest = load_workspace_manifest(workspace_root)
    paths = resolve_workspace_paths(workspace_root, manifest)
    venv_path = paths["venv"]
    python_path = resolve_runtime_python(workspace_root, manifest)
    created_venv = False

    if not python_path.exists():
        interpreter = base_python or sys.executable
        run_command([interpreter, "-m", "venv", str(venv_path)], cwd=workspace_root)
        created_venv = True

    resolved_alpha_source = resolve_alpha_source(alpha_source)
    resolved_edge_source = resolve_edge_source(
        explicit=edge_source,
        alpha_source=resolved_alpha_source,
    )

    run_command(
        [str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
        cwd=workspace_root,
    )

    if resolved_edge_source is not None:
        run_command(
            build_pip_install_command(
                python_path,
                resolved_edge_source,
                editable=editable,
            ),
            cwd=workspace_root,
        )
        run_command(
            [str(python_path), "-m", "pip", "install", "PyYAML>=6.0"],
            cwd=workspace_root,
        )
        run_command(
            build_pip_install_command(
                python_path,
                resolved_alpha_source,
                editable=editable,
                no_deps=True,
            ),
            cwd=workspace_root,
        )
    else:
        run_command(
            build_pip_install_command(
                python_path,
                resolved_alpha_source,
                editable=editable,
            ),
            cwd=workspace_root,
        )

    return EnvInitResult(
        workspace_root=workspace_root,
        venv_path=venv_path,
        python_path=python_path,
        alpha_source=resolved_alpha_source,
        edge_source=resolved_edge_source,
        editable=editable,
        created_venv=created_venv,
    )


def build_pip_install_command(
    python_path: Path,
    source: Path,
    *,
    editable: bool,
    no_deps: bool = False,
) -> list[str]:
    """Build the pip install command for a local source tree."""
    command = [str(python_path), "-m", "pip", "install"]
    if editable:
        command.extend(["-e", str(source)])
    else:
        command.append(str(source))
    if no_deps:
        command.append("--no-deps")
    return command


def resolve_alpha_source(explicit: str | Path | None = None) -> Path:
    """Resolve the Abel-alpha source tree used for workspace installs."""
    if explicit is not None:
        return validate_source_tree(Path(explicit).expanduser().resolve(), "Abel-alpha")

    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "pyproject.toml").exists():
        return candidate

    raise RuntimeError(
        "Could not resolve a local Abel-alpha source tree. "
        "Pass `--alpha-source /path/to/Abel-alpha`."
    )


def resolve_edge_source(
    *,
    explicit: str | Path | None = None,
    alpha_source: Path,
) -> Path | None:
    """Resolve a local Abel-edge source tree when one is available."""
    if explicit is not None:
        return validate_source_tree(Path(explicit).expanduser().resolve(), "Abel-edge")

    for sibling_name in ("Abel-edge", "abel-edge", "Abel-edge.git", "abel-edge.git"):
        candidate = alpha_source.parent / sibling_name
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def validate_source_tree(path: Path, label: str) -> Path:
    """Validate that a local source path looks like an installable Python project."""
    if not (path / "pyproject.toml").exists():
        raise RuntimeError(f"{label} source path does not contain pyproject.toml: {path}")
    return path


def run_command(command: list[str], *, cwd: Path) -> None:
    """Run a command and raise a readable error on failure."""
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except subprocess.CalledProcessError as exc:
        rendered = " ".join(command)
        raise RuntimeError(f"Command failed with exit code {exc.returncode}: {rendered}") from exc
