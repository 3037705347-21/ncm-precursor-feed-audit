"""Estimate the fewest countercurrent wash stages for a fixed water budget."""

from __future__ import annotations


def multistage_washing_plan(
    crystallization: dict[str, float],
    cake_moisture_kg_per_kg_solid: float,
    cake_wash_target_sulfate_wt_fraction: float,
    wash_water_budget_kg_per_kg_solid: float,
    max_wash_stages: int,
) -> dict[str, object]:
    """Return a first-pass single-stage wash estimate."""
    solid = float(crystallization["sodium_sulfate_decahydrate_kg"])
    mother_liquid = float(crystallization["remaining_liquid_kg"])
    initial_fraction = float(crystallization["remaining_sodium_sulfate_wt_fraction"])
    entrained = solid * float(cake_moisture_kg_per_kg_solid)
    water = solid * float(wash_water_budget_kg_per_kg_solid)
    final_fraction = mother_liquid * initial_fraction / (mother_liquid + water)
    return {
        "stages": 1,
        "dry_solid_kg": solid,
        "entrained_liquor_kg_per_stage": entrained,
        "total_wash_water_kg": water,
        "stage_liquid_sulfate_wt_fractions": [final_fraction],
        "final_cake_sulfate_kg": entrained * final_fraction,
        "sulfate_recovery_fraction": (
            mother_liquid * (initial_fraction - final_fraction) / (mother_liquid * initial_fraction)
        ),
        "final_cake_sulfate_wt_fraction": final_fraction,
    }
