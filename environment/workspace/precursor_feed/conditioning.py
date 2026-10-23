"""Estimate post-reaction dilution and working volume."""

from __future__ import annotations


def conditioning_plan(
    batch: dict[str, object],
    reaction: dict[str, float],
    max_na2so4_wt_fraction: float,
    precipitate_density_kg_l: float,
    working_volume_m3: float,
) -> dict[str, float]:
    """Return a first-pass dilution and volume estimate."""
    feed_mass_kg = sum(float(value) for value in batch["stock_mass_kg"].values())
    liquid_before = feed_mass_kg + float(reaction["caustic_solution_kg"])
    sulfate_kg = float(reaction["sodium_sulfate_kg"])
    return {
        "feed_mass_kg": feed_mass_kg,
        "liquid_mass_before_dilution_kg": liquid_before,
        "dilution_water_kg": 0.0,
        "dilution_water_l": 0.0,
        "final_liquid_mass_kg": liquid_before,
        "sodium_sulfate_wt_fraction": sulfate_kg / liquid_before,
        "final_slurry_volume_m3": float(batch["feed_m3"]),
    }
