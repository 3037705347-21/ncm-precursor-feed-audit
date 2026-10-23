"""Estimate two-stage countercurrent filter-cake washing."""

from __future__ import annotations

import math


def washing_plan(
    crystallization: dict[str, float],
    cake_moisture_kg_per_kg_solid: float,
    cake_wash_target_sulfate_wt_fraction: float,
) -> dict[str, float]:
    """Return minimum wash water and two-stage sulfate balances."""
    solid_kg = float(crystallization["sodium_sulfate_decahydrate_kg"])
    current_fraction = float(crystallization["remaining_sodium_sulfate_wt_fraction"])
    moisture_ratio = float(cake_moisture_kg_per_kg_solid)
    target_fraction = float(cake_wash_target_sulfate_wt_fraction)
    values = (solid_kg, current_fraction, moisture_ratio, target_fraction)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("washing inputs must be finite")
    if solid_kg < 0 or not 0.0 <= current_fraction <= 1.0:
        raise ValueError("crystal mass and mother-liquor fraction are out of range")
    if moisture_ratio <= 0:
        raise ValueError("cake moisture ratio must be positive")
    if target_fraction <= 0:
        raise ValueError("wash target must be positive")

    entrained = solid_kg * moisture_ratio
    mother_liquor = float(crystallization["remaining_liquid_kg"])
    feed_sulfate = mother_liquor * current_fraction
    if target_fraction >= current_fraction:
        wash_ratio = 0.0
        stage1_fraction = current_fraction
        final_fraction = current_fraction
    else:
        if current_fraction <= 0:
            raise ValueError("cannot wash sulfate from a sulfate-free mother liquor")
        wash_water_root = (
            -mother_liquor
            + math.sqrt(
                mother_liquor**2
                + 4.0
                * entrained
                * mother_liquor
                * (current_fraction - target_fraction)
                / target_fraction
            )
        ) / 2.0
        wash_water = max(0.0, wash_water_root)
        wash_ratio = wash_water / solid_kg if solid_kg > 0 else 0.0
        stage1_fraction = target_fraction * (entrained + wash_water) / (
            entrained
        )
        final_fraction = target_fraction

    wash_water = wash_ratio * solid_kg
    final_cake_sulfate = entrained * final_fraction
    filtrate_sulfate = max(0.0, feed_sulfate - final_cake_sulfate)
    recovery = (
        0.0 if feed_sulfate == 0 else filtrate_sulfate / feed_sulfate
    )
    return {
        "dry_solid_kg": solid_kg,
        "entrained_liquor_kg": entrained,
        "wash_water_kg": wash_water,
        "stage1_liquid_sulfate_wt_fraction": stage1_fraction,
        "final_cake_sulfate_kg": final_cake_sulfate,
        "filtrate_sulfate_kg": filtrate_sulfate,
        "sulfate_recovery_fraction": recovery,
        "final_cake_sulfate_wt_fraction": final_fraction,
    }
