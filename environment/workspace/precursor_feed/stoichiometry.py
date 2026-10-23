"""Reaction and solution balance for hydroxide precipitation."""

from __future__ import annotations

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
    total_metal = sum(float(value) for value in metal_moles.values())
    pure_mol = 2.0 * total_metal
    pure_naoh_g = pure_mol * SODIUM_HYDROXIDE_G_PER_MOL
    solution_kg = pure_naoh_g / float(caustic_wt_fraction) / 1000.0
    solids_g = (
        float(metal_moles["ni"]) * NICKEL_HYDROXIDE_G_PER_MOL
        + float(metal_moles["co"]) * COBALT_HYDROXIDE_G_PER_MOL
        + float(metal_moles["mn"]) * MANGANESE_HYDROXIDE_G_PER_MOL
    )
    sulfate_g = total_metal * SODIUM_SULFATE_G_PER_MOL
    return {
        "caustic_pure_mol": pure_mol,
        "caustic_solution_kg": solution_kg,
        "caustic_solution_l": solution_kg / float(caustic_density_kg_l),
        "hydroxide_solids_kg": solids_g / 1000.0,
        "sodium_sulfate_kg": sulfate_g / 1000.0,
    }
