"""Convert diluted ICP readings into stock-solution concentrations."""

from __future__ import annotations

import math

from .constants import ATOMIC_MASSES


def _dilution_factor(sample_ml: float, final_volume_ml: float) -> float:
    """Validate a dilution and return final volume divided by sample volume."""
    sample = float(sample_ml)
    final_volume = float(final_volume_ml)
    if not math.isfinite(sample) or not math.isfinite(final_volume):
        raise ValueError("dilution volumes must be finite")
    if sample <= 0 or final_volume <= 0:
        raise ValueError("dilution volumes must be positive")
    if final_volume < sample:
        raise ValueError("final volume must not be smaller than sample volume")
    return final_volume / sample


def element_molarity_mol_l(
    reading_mg_l: float,
    sample_ml: float,
    final_volume_ml: float,
    atomic_mass_g_mol: float,
) -> float:
    """Return elemental molarity from one diluted ICP reading."""
    reading = float(reading_mg_l)
    atomic_mass = float(atomic_mass_g_mol)
    if not math.isfinite(reading) or not math.isfinite(atomic_mass):
        raise ValueError("reading and atomic mass must be finite")
    if reading < 0 or atomic_mass <= 0:
        raise ValueError("reading must be non-negative and atomic mass positive")
    factor = _dilution_factor(sample_ml, final_volume_ml)
    return reading * factor / (1000.0 * atomic_mass)


def iron_mass_concentration_mg_l(
    reading_mg_l: float,
    sample_ml: float,
    final_volume_ml: float,
) -> float:
    """Return the iron concentration of the original stock liquid."""
    reading = float(reading_mg_l)
    if not math.isfinite(reading):
        raise ValueError("iron reading must be finite")
    if reading < 0:
        raise ValueError("iron reading must be non-negative")
    return reading * _dilution_factor(sample_ml, final_volume_ml)


def normalize_stocks(raw_stocks: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    """Convert raw CSV rows into concentration fields used by the blend."""
    normalized: dict[str, dict[str, float]] = {}
    for row in raw_stocks:
        stream_id = str(row["stream_id"])
        sample = float(row["sample_ml"])
        final_volume = float(row["final_volume_ml"])
        density = float(row["density_kg_l"])
        free_acid_mmol = float(row["free_acid_mmol_l"])
        if not all(math.isfinite(value) for value in (density, free_acid_mmol)):
            raise ValueError("stock properties must be finite")
        if density <= 0 or free_acid_mmol < 0:
            raise ValueError("density must be positive and free acid non-negative")
        normalized[stream_id] = {
            "ni_mol_l": element_molarity_mol_l(
                row["ni_icp_mg_l"], sample, final_volume, ATOMIC_MASSES["ni"]
            ),
            "co_mol_l": element_molarity_mol_l(
                row["co_icp_mg_l"], sample, final_volume, ATOMIC_MASSES["co"]
            ),
            "mn_mol_l": element_molarity_mol_l(
                row["mn_icp_mg_l"], sample, final_volume, ATOMIC_MASSES["mn"]
            ),
            "iron_mg_l": iron_mass_concentration_mg_l(
                row["iron_icp_mg_l"], sample, final_volume
            ),
            "density_kg_l": density,
            "free_acid_mol_l": free_acid_mmol / 1000.0,
        }
    return normalized
