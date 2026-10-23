#!/usr/bin/env python3
"""Generate the reproducible simulated stock table and campaign."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

SEED = 20261023
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "environment" / "workspace" / "data"

BASE_STREAMS = (
    {
        "stream_id": "recycle",
        "ni_g_l": 22.0,
        "co_g_l": 2.8,
        "mn_g_l": 2.6,
        "iron_mg_l": 14.0,
        "sample_ml": 1.0,
        "final_volume_ml": 100.0,
        "density_kg_l": 1.246,
        "free_acid_mmol_l": 18.0,
    },
    {
        "stream_id": "ni_sulfate",
        "ni_g_l": 95.0,
        "co_g_l": 0.25,
        "mn_g_l": 0.08,
        "iron_mg_l": 6.0,
        "sample_ml": 2.0,
        "final_volume_ml": 100.0,
        "density_kg_l": 1.36,
        "free_acid_mmol_l": 12.0,
    },
    {
        "stream_id": "co_sulfate",
        "ni_g_l": 0.15,
        "co_g_l": 78.0,
        "mn_g_l": 0.05,
        "iron_mg_l": 5.0,
        "sample_ml": 2.0,
        "final_volume_ml": 100.0,
        "density_kg_l": 1.32,
        "free_acid_mmol_l": 10.0,
    },
    {
        "stream_id": "mn_sulfate",
        "ni_g_l": 0.10,
        "co_g_l": 0.12,
        "mn_g_l": 64.0,
        "iron_mg_l": 7.0,
        "sample_ml": 2.0,
        "final_volume_ml": 100.0,
        "density_kg_l": 1.29,
        "free_acid_mmol_l": 15.0,
    },
)

CAMPAIGN = {
    "batch_id": "NCM811-20261023-A",
    "target_ratio": {"ni": 8.0, "co": 1.0, "mn": 1.0},
    "target_total_metal_mol_l": 1.48,
    "batch_feed_m3": 12.0,
    "stage_fractions": [0.18, 0.52, 0.30],
    "feeding_duration_min": 360.0,
    "caustic_wt_fraction": 0.32,
    "caustic_density_kg_l": 1.345,
    "oh_excess_fraction": 0.015,
    "max_iron_ppm": 12.0,
    "max_na2so4_wt_fraction": 0.13,
    "precipitate_density_kg_l": 2.1,
    "working_volume_m3": 17.0,
    "cold_na2so4_solubility_wt_fraction": 0.08,
    "cake_moisture_kg_per_kg_solid": 0.30,
    "cake_wash_target_sulfate_wt_fraction": 0.01,
    "wash_water_budget_kg_per_kg_solid": 1.2,
    "max_wash_stages": 5,
}


def diluted_reading(actual_mg_l: float, sample_ml: float, final_ml: float, rng: random.Random) -> float:
    """Return a seeded ICP reading after dilution and rounding."""
    noise = rng.uniform(-0.0035, 0.0035)
    reading = actual_mg_l * sample_ml / final_ml * (1.0 + noise)
    return round(reading, 1)


def main() -> None:
    """Write the simulated data files."""
    rng = random.Random(SEED)
    rows = []
    for stream in BASE_STREAMS:
        sample = float(stream["sample_ml"])
        final_ml = float(stream["final_volume_ml"])
        rows.append(
            {
                "stream_id": stream["stream_id"],
                "ni_icp_mg_l": f"{diluted_reading(stream['ni_g_l'] * 1000.0, sample, final_ml, rng):.1f}",
                "co_icp_mg_l": f"{diluted_reading(stream['co_g_l'] * 1000.0, sample, final_ml, rng):.1f}",
                "mn_icp_mg_l": f"{diluted_reading(stream['mn_g_l'] * 1000.0, sample, final_ml, rng):.1f}",
                "iron_icp_mg_l": f"{diluted_reading(stream['iron_mg_l'], sample, final_ml, rng):.2f}",
                "sample_ml": f"{sample:.1f}",
                "final_volume_ml": f"{final_ml:.1f}",
                "density_kg_l": f"{stream['density_kg_l']:.3f}",
                "free_acid_mmol_l": f"{stream['free_acid_mmol_l']:.1f}",
            }
        )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR / "stocks.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (DATA_DIR / "campaign.json").open("w", encoding="utf-8") as handle:
        json.dump(CAMPAIGN, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
