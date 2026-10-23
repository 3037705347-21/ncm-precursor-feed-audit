"""Estimate sodium sulfate decahydrate formation during cooling."""

from __future__ import annotations


def crystallization_plan(
    conditioning: dict[str, float],
    cold_na2so4_solubility_wt_fraction: float,
) -> dict[str, float]:
    """Return a first-pass cooling crystallization estimate."""
    liquid_mass = float(conditioning["final_liquid_mass_kg"])
    fraction = float(conditioning["sodium_sulfate_wt_fraction"])
    sulfate_mass = liquid_mass * fraction
    return {
        "sodium_sulfate_decahydrate_kg": 0.0,
        "crystallized_sulfate_kg": 0.0,
        "remaining_liquid_kg": liquid_mass,
        "remaining_sodium_sulfate_kg": sulfate_mass,
        "remaining_sodium_sulfate_wt_fraction": fraction,
    }
