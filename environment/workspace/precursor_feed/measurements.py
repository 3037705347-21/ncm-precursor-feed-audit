"""Convert diluted ICP readings into stock-solution concentrations."""

from __future__ import annotations

from .constants import ATOMIC_MASSES


def element_molarity_mol_l(
    reading_mg_l: float,
    sample_ml: float,
    final_volume_ml: float,
    atomic_mass_g_mol: float,
) -> float:
    """Return elemental molarity from one diluted ICP reading."""
    reading = float(reading_mg_l)
    sample = float(sample_ml)
    final_volume = float(final_volume_ml)
    atomic_mass = float(atomic_mass_g_mol)
    return reading / (1000.0 * atomic_mass)


def iron_mass_concentration_mg_l(
    reading_mg_l: float,
    sample_ml: float,
    final_volume_ml: float,
) -> float:
    """Return the iron concentration of the original stock liquid."""
    reading = float(reading_mg_l)
    sample = float(sample_ml)
    final_volume = float(final_volume_ml)
    return reading


def normalize_stocks(raw_stocks: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    """Convert raw CSV rows into concentration fields used by the blend."""
    normalized: dict[str, dict[str, float]] = {}
    for row in raw_stocks:
        stream_id = row["stream_id"]
        sample = float(row["sample_ml"])
        final_volume = float(row["final_volume_ml"])
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
            "density_kg_l": float(row["density_kg_l"]),
            "free_acid_mol_l": float(row["free_acid_mmol_l"]) / 1000.0,
        }
    return normalized
