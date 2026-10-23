"""Incorrect command that ignores the inputs and fabricates a report."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Write a fixed report with equal-volume fractions."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 3:
        return 2
    report = {
        "batch_id": "NCM811-20261023-A",
        "stocks": {},
        "blend_fractions": {
            "recycle": 0.25,
            "ni_sulfate": 0.25,
            "co_sulfate": 0.25,
            "mn_sulfate": 0.25,
        },
        "blend": {
            "ni_mol_l": 0.4,
            "co_mol_l": 0.1,
            "mn_mol_l": 0.1,
            "total_metal_mol_l": 0.6,
            "iron_ppm": 4.5,
            "density_kg_l": 1.3,
            "free_acid_mol_l": 0.012,
        },
        "batch": {},
        "reaction": {
            "caustic_pure_mol": 2400.0,
            "caustic_solution_kg": 300.0,
            "caustic_solution_l": 223.0,
            "hydroxide_solids_kg": 55.0,
            "sodium_sulfate_kg": 170.0,
        },
    }
    Path(arguments[2]).write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
