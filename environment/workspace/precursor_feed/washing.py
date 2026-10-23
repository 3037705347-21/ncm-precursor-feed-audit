"""Estimate two-stage countercurrent filter-cake washing."""

from __future__ import annotations


def washing_plan(
    crystallization: dict[str, float],
    cake_moisture_kg_per_kg_solid: float,
    cake_wash_target_sulfate_wt_fraction: float,
) -> dict[str, float]:
    """Return a first-pass countercurrent wash estimate."""
    solid_kg = float(crystallization["sodium_sulfate_decahydrate_kg"])
    current_fraction = float(crystallization["remaining_sodium_sulfate_wt_fraction"])
    moisture_ratio = float(cake_moisture_kg_per_kg_solid)
    entrained = solid_kg * moisture_ratio
    sulfate = entrained * current_fraction
    return {
        "dry_solid_kg": solid_kg,
        "entrained_liquor_kg": entrained,
        "wash_water_kg": 0.0,
        "stage1_liquid_sulfate_wt_fraction": current_fraction,
        "final_cake_sulfate_kg": sulfate,
        "filtrate_sulfate_kg": 0.0,
        "sulfate_recovery_fraction": 0.0,
        "final_cake_sulfate_wt_fraction": current_fraction,
    }
