"""Solve the four-stream blend needed for the target precursor ratio."""

from __future__ import annotations

from .constants import METAL_KEYS, STREAM_IDS


def solve_blend(
    stocks: dict[str, dict[str, float]],
    target_ratio: dict[str, float],
    target_total_metal_mol_l: float,
) -> dict[str, object]:
    """Return a simple equal-volume blend and its composition."""
    fractions = {stream_id: 0.25 for stream_id in STREAM_IDS}
    blend = {
        "ni_mol_l": sum(
            fractions[stream_id] * stocks[stream_id]["ni_mol_l"]
            for stream_id in STREAM_IDS
        ),
        "co_mol_l": sum(
            fractions[stream_id] * stocks[stream_id]["co_mol_l"]
            for stream_id in STREAM_IDS
        ),
        "mn_mol_l": sum(
            fractions[stream_id] * stocks[stream_id]["mn_mol_l"]
            for stream_id in STREAM_IDS
        ),
        "density_kg_l": sum(
            fractions[stream_id] * stocks[stream_id]["density_kg_l"]
            for stream_id in STREAM_IDS
        ),
        "free_acid_mol_l": sum(
            fractions[stream_id] * stocks[stream_id]["free_acid_mol_l"]
            for stream_id in STREAM_IDS
        ),
    }
    blend["total_metal_mol_l"] = sum(blend[f"{metal}_mol_l"] for metal in METAL_KEYS)
    blend["iron_ppm"] = (
        sum(
            fractions[stream_id] * stocks[stream_id]["iron_mg_l"]
            for stream_id in STREAM_IDS
        )
        / blend["density_kg_l"]
    )
    return {"fractions": fractions, "blend": blend}
