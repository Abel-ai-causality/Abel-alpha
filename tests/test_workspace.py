from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from abel_alpha import narrative_impl
from abel_alpha.workspace import (
    build_default_manifest,
    render_workspace_status,
    scaffold_workspace,
)


def test_scaffold_workspace_writes_alpha_owned_boundary_guidance(tmp_path: Path) -> None:
    root = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")

    readme = (root / "README.md").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")

    assert "This workspace is for alpha-managed branch research." in readme
    assert "Do not run `causal-edge init` inside this workspace." in readme
    assert "Do not bootstrap `./abel-alpha-workspace` inside it." in readme
    assert "standalone `causal-edge init` project inside it" in agents
    assert "Do not create `./abel-alpha-workspace` inside it." in agents


def test_scaffold_workspace_rejects_nested_workspace_under_existing_root(tmp_path: Path) -> None:
    root = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")

    with pytest.raises(RuntimeError, match="Refusing to create a nested Abel-alpha workspace"):
        scaffold_workspace("nested", target_root=root / "abel-alpha-workspace")


def test_workspace_bootstrap_rejects_nested_target_with_reentry_hint(
    tmp_path: Path,
    capsys,
) -> None:
    root = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")
    nested_target = root / "abel-alpha-workspace"

    args = argparse.Namespace(
        workspace_command="bootstrap",
        path=str(nested_target),
        name="abel-alpha-workspace",
        base_python=None,
        alpha_source=None,
        edge_spec=None,
        edge_source=None,
        runtime_python=None,
        no_editable=False,
    )

    rc = narrative_impl.handle_workspace_command(args)
    out = capsys.readouterr().out

    assert rc == 1
    assert "Refusing to bootstrap a nested Abel-alpha workspace" in out
    assert f"Existing workspace root for this area: {root}" in out
    assert f"abel-alpha workspace status --path {root}" in out
    assert f"abel-alpha doctor --path {root}" in out


def test_render_workspace_status_reports_alpha_managed_mode(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    status = render_workspace_status(root, build_default_manifest("workspace"))

    assert "Workspace mode: alpha-managed branch research" in status
    assert f"Research root: {root / 'research'}" in status
