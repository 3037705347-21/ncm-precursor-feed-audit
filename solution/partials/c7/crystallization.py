"""Estimate sodium sulfate decahydrate formation during cooling."""

from __future__ import annotations

import math

SODIUM_SULFATE_G_PER_MOL = 142.04214
DECAHYDRATE_G_PER_MOL = 322.19494
HYDRATE_MASS_RATIO = DECAHYDRATE_G_PER_MOL / SODIUM_SULFATE_G_PER_MOL


def crystallization_plan(
    conditioning: dict[str, float],
    cold_na2so4_solubility_wt_fraction: float,
) -> dict[str, float]:
    """Return cooling crystallization and remaining liquid balances."""
    liquid_mass = float(conditioning["final_liquid_mass_kg"])
    current_fraction = float(conditioning["sodium_sulfate_wt_fraction"])
    limit = float(cold_na2so4_solubility_wt_fraction)
    if not all(
        math.isfinite(value) for value in (liquid_mass, current_fraction, limit)
    ):
        raise ValueError("crystallization inputs must be finite")
    if liquid_mass <= 0:
        raise ValueError("liquid mass must be positive")
    if not 0.0 <= current_fraction <= 1.0:
        raise ValueError("sodium sulfate mass fraction must be in [0, 1]")
    if not 0.0 < limit < 0.4:
        raise ValueError("cold solubility must be in (0, 0.4)")

    sulfate_mass = liquid_mass * current_fraction
    if current_fraction <= limit:
        crystallized_sulfate = 0.0
    else:
        denominator = HYDRATE_MASS_RATIO * limit - 1.0
        if denominator >= 0:
            raise ValueError("cold solubility cannot produce a physical hydrate balance")
        crystallized_sulfate = (limit * liquid_mass - sulfate_mass) / denominator
        crystallized_sulfate = max(0.0, crystallized_sulfate)
    hydrate_mass = HYDRATE_MASS_RATIO * crystallized_sulfate
    remaining_liquid = liquid_mass - hydrate_mass
    remaining_sulfate = sulfate_mass - crystallized_sulfate
    if remaining_liquid <= 0 or remaining_sulfate < 0:
        raise ValueError("crystallization leaves a non-physical liquid balance")
    remaining_fraction = remaining_sulfate / remaining_liquid
    return {
        "sodium_sulfate_decahydrate_kg": hydrate_mass,
        "crystallized_sulfate_kg": crystallized_sulfate,
        "remaining_liquid_kg": remaining_liquid,
        "remaining_sodium_sulfate_kg": remaining_sulfate,
        "remaining_sodium_sulfate_wt_fraction": remaining_fraction,
    }
