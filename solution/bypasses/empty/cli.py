"""Incorrect command that writes an empty object regardless of input."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Write an empty JSON object and report success."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 3:
        return 2
    Path(arguments[2]).write_text(json.dumps({}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
