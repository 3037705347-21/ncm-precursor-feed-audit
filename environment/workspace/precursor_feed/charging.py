"""Expand blend fractions into batch volumes, masses, and stage flows."""

from __future__ import annotations

from .constants import METAL_KEYS, STREAM_IDS


def batch_plan(
    batch_feed_m3: float,
    stage_fractions: list[float],
    feeding_duration_min: float,
    fractions: dict[str, float],
    stocks: dict[str, dict[str, float]],
    blend: dict[str, float],
) -> dict[str, object]:
    """Return the batch charge and three-stage feed schedule."""
    feed_m3 = float(batch_feed_m3)
    duration = float(feeding_duration_min)
    stock_volume_l = {
        stream_id: feed_m3 * float(fractions[stream_id])
        for stream_id in STREAM_IDS
    }
    stock_mass_kg = {
        stream_id: stock_volume_l[stream_id] * 0.5
        for stream_id in STREAM_IDS
    }
    stages = []
    for index, stage_fraction in enumerate(stage_fractions, start=1):
        stages.append(
            {
                "stage": index,
                "duration_min": duration,
                "volumes_l": {
                    stream_id: stock_volume_l[stream_id]
                    for stream_id in STREAM_IDS
                },
                "flows_l_h": {
                    stream_id: stock_volume_l[stream_id] / (duration / 60.0)
                    for stream_id in STREAM_IDS
                },
            }
        )
    return {
        "feed_m3": feed_m3,
        "feed_l": feed_m3 * 1000.0,
        "total_metal_mol": float(blend["total_metal_mol_l"]) * feed_m3 * 1000.0,
        "free_acid_mol": float(blend["free_acid_mol_l"]) * feed_m3 * 1000.0,
        "metal_moles": {
            metal: float(blend[f"{metal}_mol_l"]) * feed_m3 * 1000.0
            for metal in METAL_KEYS
        },
        "stock_volume_l": stock_volume_l,
        "stock_mass_kg": stock_mass_kg,
        "stages": stages,
    }
