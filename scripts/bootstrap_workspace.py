#!/usr/bin/env python3
"""Thin system-Python entrypoint for bootstrapping an Abel-alpha workspace."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from abel_alpha.cli import main as cli_main

    sys.argv = [
        sys.argv[0],
        "workspace",
        "bootstrap",
        *sys.argv[1:],
    ]
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
