"""Input loading and output helpers for the feed audit command."""

from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from pathlib import Path

from .constants import STREAM_IDS

STOCK_COLUMNS = (
    "stream_id",
    "ni_icp_mg_l",
    "co_icp_mg_l",
    "mn_icp_mg_l",
    "iron_icp_mg_l",
    "sample_ml",
    "final_volume_ml",
    "density_kg_l",
    "free_acid_mmol_l",
)

CAMPAIGN_FIELDS = (
    "batch_id",
    "target_ratio",
    "target_total_metal_mol_l",
    "batch_feed_m3",
    "stage_fractions",
    "feeding_duration_min",
    "caustic_wt_fraction",
    "caustic_density_kg_l",
    "oh_excess_fraction",
    "max_iron_ppm",
    "max_na2so4_wt_fraction",
    "precipitate_density_kg_l",
    "working_volume_m3",
    "cold_na2so4_solubility_wt_fraction",
    "cake_moisture_kg_per_kg_solid",
    "cake_wash_target_sulfate_wt_fraction",
    "wash_water_budget_kg_per_kg_solid",
    "max_wash_stages",
)

NUMERIC_STOCK_COLUMNS = STOCK_COLUMNS[1:]


def load_stocks(path: str | Path) -> list[dict[str, str]]:
    """Load and strictly validate the four-row stock table."""
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or set(reader.fieldnames) != set(STOCK_COLUMNS):
            raise ValueError("stock table has unexpected columns")
        if len(reader.fieldnames) != len(STOCK_COLUMNS):
            raise ValueError("stock table columns must be unique")
        rows = [dict(row) for row in reader]
    if len(rows) != 4:
        raise ValueError("stock table must contain exactly four rows")
    stream_ids = [row["stream_id"] for row in rows]
    if len(set(stream_ids)) != 4 or set(stream_ids) != set(STREAM_IDS):
        raise ValueError("stock streams must be exactly the four required IDs")
    for row in rows:
        if any(row[column] is None or str(row[column]).strip() == "" for column in STOCK_COLUMNS):
            raise ValueError("stock table contains an empty value")
        numbers = [float(row[column]) for column in NUMERIC_STOCK_COLUMNS]
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("stock table values must be finite")
        sample, final_volume, density, free_acid = numbers[4:]
        readings = numbers[:4]
        if sample <= 0 or final_volume <= 0 or density <= 0:
            raise ValueError("dilution volumes and density must be positive")
        if final_volume < sample:
            raise ValueError("final volume must not be smaller than sample volume")
        if any(value < 0 for value in readings) or free_acid < 0:
            raise ValueError("ICP readings and free acid must be non-negative")
    return rows


def load_campaign(path: str | Path) -> dict[str, object]:
    """Load and validate the campaign JSON document."""
    with open(path, encoding="utf-8") as handle:
        campaign = json.load(handle)
    if not isinstance(campaign, dict):
        raise ValueError("campaign must be a JSON object")
    if any(field not in campaign for field in CAMPAIGN_FIELDS):
        raise ValueError("campaign is missing a required field")
    if not str(campaign["batch_id"]).strip():
        raise ValueError("batch_id must not be empty")
    ratio = campaign["target_ratio"]
    if not isinstance(ratio, dict) or set(ratio) != {"ni", "co", "mn"}:
        raise ValueError("target_ratio must contain ni, co and mn")
    ratio_values = [float(ratio[metal]) for metal in ("ni", "co", "mn")]
    if not all(math.isfinite(value) and value >= 0 for value in ratio_values):
        raise ValueError("target ratios must be finite and non-negative")
    if sum(ratio_values) <= 0:
        raise ValueError("target ratio sum must be positive")

    scalar_names = (
        "target_total_metal_mol_l",
        "batch_feed_m3",
        "feeding_duration_min",
        "caustic_wt_fraction",
        "caustic_density_kg_l",
        "oh_excess_fraction",
        "max_iron_ppm",
        "max_na2so4_wt_fraction",
        "precipitate_density_kg_l",
        "working_volume_m3",
        "cold_na2so4_solubility_wt_fraction",
        "cake_moisture_kg_per_kg_solid",
        "cake_wash_target_sulfate_wt_fraction",
        "wash_water_budget_kg_per_kg_solid",
    )
    scalar_values = {name: float(campaign[name]) for name in scalar_names}
    if not all(math.isfinite(value) for value in scalar_values.values()):
        raise ValueError("campaign numeric fields must be finite")
    if scalar_values["max_iron_ppm"] <= 0:
        raise ValueError("max_iron_ppm must be positive")
    for name in scalar_names[:5]:
        if scalar_values[name] <= 0:
            raise ValueError(f"{name} must be positive")
    if not 0.0 < scalar_values["caustic_wt_fraction"] <= 1.0:
        raise ValueError("caustic_wt_fraction must be in (0, 1]")
    if not 0.0 < scalar_values["max_na2so4_wt_fraction"] <= 1.0:
        raise ValueError("max_na2so4_wt_fraction must be in (0, 1]")
    if not 0.0 < scalar_values["cold_na2so4_solubility_wt_fraction"] < 0.4:
        raise ValueError("cold_na2so4_solubility_wt_fraction must be in (0, 0.4)")
    if scalar_values["cake_moisture_kg_per_kg_solid"] <= 0:
        raise ValueError("cake_moisture_kg_per_kg_solid must be positive")
    target = scalar_values["cake_wash_target_sulfate_wt_fraction"]
    if not 0.0 < target <= scalar_values["cold_na2so4_solubility_wt_fraction"]:
        raise ValueError(
            "cake_wash_target_sulfate_wt_fraction must be positive and no greater "
            "than the cold solubility"
        )
    if scalar_values["wash_water_budget_kg_per_kg_solid"] <= 0:
        raise ValueError("wash_water_budget_kg_per_kg_solid must be positive")
    max_stages = campaign["max_wash_stages"]
    if isinstance(max_stages, bool) or not isinstance(max_stages, int):
        raise ValueError("max_wash_stages must be an integer")
    if not 1 <= max_stages <= 8:
        raise ValueError("max_wash_stages must be between one and eight")
    if scalar_values["oh_excess_fraction"] < 0:
        raise ValueError("oh_excess_fraction must be non-negative")
    if scalar_values["precipitate_density_kg_l"] <= 0:
        raise ValueError("precipitate_density_kg_l must be positive")
    if scalar_values["working_volume_m3"] <= 0:
        raise ValueError("working_volume_m3 must be positive")

    if not isinstance(campaign["stage_fractions"], list):
        raise ValueError("stage_fractions must be an array")
    stage_values = [float(value) for value in campaign["stage_fractions"]]
    if len(stage_values) != 3 or any(
        not math.isfinite(value) or value <= 0 for value in stage_values
    ):
        raise ValueError("stage_fractions must contain three positive values")
    if abs(sum(stage_values) - 1.0) > 1e-9:
        raise ValueError("stage_fractions must sum to one")
    return campaign


def check_iron_limit(iron_ppm: float, max_iron_ppm: float) -> None:
    """Reject a blend above the campaign iron limit."""
    value = float(iron_ppm)
    limit = float(max_iron_ppm)
    if not math.isfinite(value) or not math.isfinite(limit):
        raise ValueError("iron values must be finite")
    if value < 0 or limit <= 0:
        raise ValueError("iron concentration must be non-negative and limit positive")
    if value > limit:
        raise ValueError("blended iron exceeds the campaign limit")


def write_json_atomic(path: str | Path, payload: dict[str, object]) -> None:
    """Write a JSON report through a same-directory temporary file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
