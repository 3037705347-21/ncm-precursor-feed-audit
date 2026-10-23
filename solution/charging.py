"""Expand blend fractions into batch volumes, masses, and stage flows."""

from __future__ import annotations

import math

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
    stages = [float(value) for value in stage_fractions]
    if not math.isfinite(feed_m3) or feed_m3 <= 0:
        raise ValueError("batch feed volume must be positive")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("feeding duration must be positive")
    if len(stages) != 3 or any(not math.isfinite(value) or value <= 0 for value in stages):
        raise ValueError("stage fractions must be three positive finite values")
    if abs(sum(stages) - 1.0) > 1e-9:
        raise ValueError("stage fractions must sum to one")
    if set(fractions) != set(STREAM_IDS):
        raise ValueError("batch requires exactly four blend fractions")
    fraction_sum = sum(float(fractions[stream_id]) for stream_id in STREAM_IDS)
    if abs(fraction_sum - 1.0) > 1e-9:
        raise ValueError("blend fractions must sum to one")

    feed_l = feed_m3 * 1000.0
    stock_volume_l = {
        stream_id: float(fractions[stream_id]) * feed_l for stream_id in STREAM_IDS
    }
    stock_mass_kg = {
        stream_id: stock_volume_l[stream_id] * float(stocks[stream_id]["density_kg_l"])
        for stream_id in STREAM_IDS
    }
    stage_rows = []
    for index, stage_fraction in enumerate(stages, start=1):
        stage_duration = duration * stage_fraction
        volumes = {
            stream_id: stock_volume_l[stream_id] * stage_fraction
            for stream_id in STREAM_IDS
        }
        flows = {
            stream_id: volumes[stream_id] / (stage_duration / 60.0)
            for stream_id in STREAM_IDS
        }
        stage_rows.append(
            {
                "stage": index,
                "duration_min": stage_duration,
                "volumes_l": volumes,
                "flows_l_h": flows,
            }
        )

    return {
        "feed_m3": feed_m3,
        "feed_l": feed_l,
        "total_metal_mol": float(blend["total_metal_mol_l"]) * feed_l,
        "free_acid_mol": float(blend["free_acid_mol_l"]) * feed_l,
        "metal_moles": {
            metal: float(blend[f"{metal}_mol_l"]) * feed_l for metal in METAL_KEYS
        },
        "stock_volume_l": stock_volume_l,
        "stock_mass_kg": stock_mass_kg,
        "stages": stage_rows,
    }
