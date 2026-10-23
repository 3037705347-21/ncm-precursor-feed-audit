"""Incorrect command that exits successfully with truncated JSON."""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Write an unclosed JSON object."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 3:
        return 2
    Path(arguments[2]).write_text('{"batch_id":', encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
