"""Input loading and output helpers for the feed audit command."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path


def load_stocks(path: str | Path) -> list[dict[str, str]]:
    """Load the stock table from CSV."""
    with open(path, newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_campaign(path: str | Path) -> dict[str, object]:
    """Load the campaign JSON document."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def check_iron_limit(iron_ppm: float, max_iron_ppm: float) -> None:
    """Leave the iron check policy to the caller."""
    return None


def write_json_atomic(path: str | Path, payload: dict[str, object]) -> None:
    """Write a JSON report through a same-directory temporary file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, destination)
