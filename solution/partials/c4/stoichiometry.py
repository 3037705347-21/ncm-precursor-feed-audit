"""Reaction and solution balance for hydroxide precipitation."""

from __future__ import annotations

import math

from .constants import (
    COBALT_HYDROXIDE_G_PER_MOL,
    MANGANESE_HYDROXIDE_G_PER_MOL,
    NICKEL_HYDROXIDE_G_PER_MOL,
    SODIUM_HYDROXIDE_G_PER_MOL,
    SODIUM_SULFATE_G_PER_MOL,
)


def reaction_plan(
    metal_moles: dict[str, float],
    free_acid_mol: float,
    oh_excess_fraction: float,
    caustic_wt_fraction: float,
    caustic_density_kg_l: float,
) -> dict[str, float]:
    """Return caustic demand and precipitated material masses."""
    metals = {key: float(metal_moles[key]) for key in ("ni", "co", "mn")}
    acid = float(free_acid_mol)
    excess = float(oh_excess_fraction)
    wt_fraction = float(caustic_wt_fraction)
    density = float(caustic_density_kg_l)
    values = (*metals.values(), acid, excess, wt_fraction, density)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("reaction inputs must be finite")
    if any(value < 0 for value in metals.values()) or acid < 0 or excess < 0:
        raise ValueError("metal moles, acid and excess must be non-negative")
    if not 0.0 < wt_fraction <= 1.0:
        raise ValueError("caustic mass fraction must be in (0, 1]")
    if density <= 0:
        raise ValueError("caustic density must be positive")

    total_metal = sum(metals.values())
    pure_mol = (2.0 * total_metal + acid) * (1.0 + excess)
    solution_kg = pure_mol * SODIUM_HYDROXIDE_G_PER_MOL / wt_fraction / 1000.0
    solids_g = (
        metals["ni"] * NICKEL_HYDROXIDE_G_PER_MOL
        + metals["co"] * COBALT_HYDROXIDE_G_PER_MOL
        + metals["mn"] * MANGANESE_HYDROXIDE_G_PER_MOL
    )
    sulfate_g = (total_metal + acid / 2.0) * SODIUM_SULFATE_G_PER_MOL
    return {
        "caustic_pure_mol": pure_mol,
        "caustic_solution_kg": solution_kg,
        "caustic_solution_l": solution_kg / density,
        "hydroxide_solids_kg": solids_g / 1000.0,
        "sodium_sulfate_kg": sulfate_g / 1000.0,
    }
