"""Console entrypoint for Abel-alpha."""

from __future__ import annotations

from abel_alpha.narrative_impl import main as narrative_main


def main() -> int:
    """Run the Abel-alpha CLI."""
    return narrative_main()
