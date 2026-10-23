"""Estimate post-reaction dilution and working volume."""

from __future__ import annotations

import math


def conditioning_plan(
    batch: dict[str, object],
    reaction: dict[str, float],
    max_na2so4_wt_fraction: float,
    precipitate_density_kg_l: float,
    working_volume_m3: float,
) -> dict[str, float]:
    """Return dilution water and final sulfate mass fraction."""
    limit = float(max_na2so4_wt_fraction)
    solid_density = float(precipitate_density_kg_l)
    capacity = float(working_volume_m3)
    feed_mass_kg = sum(float(value) for value in batch["stock_mass_kg"].values())
    feed_volume_m3 = float(batch["feed_m3"])
    caustic_mass_kg = float(reaction["caustic_solution_kg"])
    caustic_volume_l = float(reaction["caustic_solution_l"])
    solids_kg = float(reaction["hydroxide_solids_kg"])
    sulfate_kg = float(reaction["sodium_sulfate_kg"])

    numbers = (
        limit,
        solid_density,
        capacity,
        feed_mass_kg,
        feed_volume_m3,
        caustic_mass_kg,
        caustic_volume_l,
        solids_kg,
        sulfate_kg,
    )
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError("conditioning inputs must be finite")
    if not 0.0 < limit <= 1.0:
        raise ValueError("maximum sodium sulfate mass fraction must be in (0, 1]")
    if solid_density <= 0 or capacity <= 0 or feed_volume_m3 <= 0:
        raise ValueError("solid density, working volume and feed volume must be positive")
    if min(feed_mass_kg, caustic_mass_kg, caustic_volume_l, solids_kg, sulfate_kg) < 0:
        raise ValueError("conditioning masses and volumes must be non-negative")

    liquid_before = feed_mass_kg + caustic_mass_kg - solids_kg
    if liquid_before <= 0:
        raise ValueError("liquid mass after precipitation must be positive")
    water_kg = max(0.0, sulfate_kg / limit - liquid_before)
    final_liquid = liquid_before + water_kg
    sulfate_fraction = sulfate_kg / final_liquid
    final_volume = (
        feed_volume_m3
        + caustic_volume_l / 1000.0
        + water_kg / 1000.0
        + solids_kg / solid_density / 1000.0
    )
    if final_volume > capacity:
        raise ValueError("final slurry volume exceeds reactor working volume")
    return {
        "feed_mass_kg": feed_mass_kg,
        "liquid_mass_before_dilution_kg": liquid_before,
        "dilution_water_kg": water_kg,
        "dilution_water_l": water_kg,
        "final_liquid_mass_kg": final_liquid,
        "sodium_sulfate_wt_fraction": sulfate_fraction,
        "final_slurry_volume_m3": final_volume,
    }
