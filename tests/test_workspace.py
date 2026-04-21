from __future__ import annotations

from pathlib import Path

from abel_alpha.workspace import build_default_manifest, render_workspace_status, scaffold_workspace


def test_scaffold_workspace_writes_alpha_owned_boundary_guidance(tmp_path: Path) -> None:
    root = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")

    readme = (root / "README.md").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")

    assert "This workspace is for alpha-managed branch research." in readme
    assert "Do not run `causal-edge init` inside this workspace." in readme
    assert "standalone `causal-edge init` project inside it" in agents


def test_render_workspace_status_reports_alpha_managed_mode(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    status = render_workspace_status(root, build_default_manifest("workspace"))

    assert "Workspace mode: alpha-managed branch research" in status
    assert f"Research root: {root / 'research'}" in status
