"""Compatibility loader for the existing research narrative script."""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType


@lru_cache(maxsize=1)
def load_legacy_module() -> ModuleType:
    """Load the existing script-backed implementation from the source tree."""
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "research_narrative.py"
    spec = importlib.util.spec_from_file_location("abel_alpha_legacy_research_narrative", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Abel-alpha legacy script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
