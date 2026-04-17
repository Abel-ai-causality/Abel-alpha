"""Public package surface for the existing narrative CLI."""

from __future__ import annotations

from typing import Any

from abel_alpha._legacy import load_legacy_module


def main() -> int:
    """Run the existing narrative CLI."""
    module = load_legacy_module()
    return module.main()


def __getattr__(name: str) -> Any:
    """Expose legacy helpers through the package namespace during migration."""
    module = load_legacy_module()
    try:
        return getattr(module, name)
    except AttributeError as exc:
        raise AttributeError(f"module 'abel_alpha.narrative' has no attribute {name!r}") from exc
