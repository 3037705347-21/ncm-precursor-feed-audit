"""Check ICP conversion, blend reconciliation, charging, and reaction balances."""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, "/workspace")

from precursor_feed.blending import solve_blend
from precursor_feed.charging import batch_plan
from precursor_feed.conditioning import conditioning_plan
from precursor_feed.crystallization import crystallization_plan
from precursor_feed.measurements import (
    element_molarity_mol_l,
    iron_mass_concentration_mg_l,
    normalize_stocks,
)
from precursor_feed.stoichiometry import reaction_plan
from precursor_feed.washing import washing_plan
from precursor_feed.multistage_washing import multistage_washing_plan
from precursor_feed.validation import check_iron_limit, load_campaign, load_stocks

DATA = Path("/workspace/data")
NICKEL_G_PER_MOL = 58.6934
COBALT_G_PER_MOL = 58.933194
MANGANESE_G_PER_MOL = 54.938044
NICKEL_HYDROXIDE_G_PER_MOL = 92.70808
COBALT_HYDROXIDE_G_PER_MOL = 92.947874
MANGANESE_HYDROXIDE_G_PER_MOL = 88.952724
SODIUM_HYDROXIDE_G_PER_MOL = 39.99711
SODIUM_SULFATE_G_PER_MOL = 142.04214
STREAM_IDS = ("recycle", "ni_sulfate", "co_sulfate", "mn_sulfate")
METAL_KEYS = ("ni", "co", "mn")
ATOMIC_MASSES = {
    "ni": NICKEL_G_PER_MOL,
    "co": COBALT_G_PER_MOL,
    "mn": MANGANESE_G_PER_MOL,
}


def _reference_diluted(
    reading_mg_l: float,
    sample_ml: float,
    final_volume_ml: float,
) -> float:
    """Return a dilution-corrected reading using the reference ratio."""
    return reading_mg_l * final_volume_ml / sample_ml


def _reference_molarity(
    reading_mg_l: float,
    sample_ml: float,
    final_volume_ml: float,
    atomic_mass: float,
) -> float:
    """Convert one diluted reading to stock molarity."""
    return _reference_diluted(reading_mg_l, sample_ml, final_volume_ml) / (
        1000.0 * atomic_mass
    )


def _reference_normalize(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    """Normalize raw stock rows without importing workspace calculations."""
    result = {}
    for row in rows:
        sample = float(row["sample_ml"])
        final_volume = float(row["final_volume_ml"])
        result[row["stream_id"]] = {
            "ni_mol_l": _reference_molarity(
                float(row["ni_icp_mg_l"]), sample, final_volume, NICKEL_G_PER_MOL
            ),
            "co_mol_l": _reference_molarity(
                float(row["co_icp_mg_l"]), sample, final_volume, COBALT_G_PER_MOL
            ),
            "mn_mol_l": _reference_molarity(
                float(row["mn_icp_mg_l"]), sample, final_volume, MANGANESE_G_PER_MOL
            ),
            "iron_mg_l": _reference_diluted(
                float(row["iron_icp_mg_l"]), sample, final_volume
            ),
            "density_kg_l": float(row["density_kg_l"]),
            "free_acid_mol_l": float(row["free_acid_mmol_l"]) / 1000.0,
        }
    return result


def _reference_solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a small linear system by Gauss-Jordan elimination."""
    size = len(rhs)
    rows = [list(row) + [float(rhs[index])] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1e-13:
            raise ValueError("singular reference system")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            rows[row] = [
                rows[row][item] - factor * rows[column][item]
                for item in range(size + 1)
            ]
    return [rows[index][size] for index in range(size)]


def _reference_blend(
    stocks: dict[str, dict[str, float]],
    ratio: dict[str, float],
    target_total: float,
) -> dict[str, object]:
    """Solve and evaluate a four-stream blend independently."""
    ratio_sum = sum(float(ratio[metal]) for metal in METAL_KEYS)
    normalized = {metal: float(ratio[metal]) / ratio_sum for metal in METAL_KEYS}
    matrix = [
        [stocks[stream_id][f"{metal}_mol_l"] for stream_id in STREAM_IDS]
        for metal in METAL_KEYS
    ]
    matrix.append([1.0, 1.0, 1.0, 1.0])
    rhs = [target_total * normalized[metal] for metal in METAL_KEYS] + [1.0]
    values = _reference_solve(matrix, rhs)
    fractions = dict(zip(STREAM_IDS, values, strict=True))
    blend = {
        f"{metal}_mol_l": sum(
            fractions[stream_id] * stocks[stream_id][f"{metal}_mol_l"]
            for stream_id in STREAM_IDS
        )
        for metal in METAL_KEYS
    }
    blend["total_metal_mol_l"] = sum(blend[f"{metal}_mol_l"] for metal in METAL_KEYS)
    blend["density_kg_l"] = sum(
        fractions[stream_id] * stocks[stream_id]["density_kg_l"]
        for stream_id in STREAM_IDS
    )
    blend["free_acid_mol_l"] = sum(
        fractions[stream_id] * stocks[stream_id]["free_acid_mol_l"]
        for stream_id in STREAM_IDS
    )
    blend["iron_ppm"] = sum(
        fractions[stream_id] * stocks[stream_id]["iron_mg_l"]
        for stream_id in STREAM_IDS
    ) / blend["density_kg_l"]
    return {"fractions": fractions, "blend": blend}


def _reference_batch(
    feed_m3: float,
    stages: list[float],
    duration_min: float,
    fractions: dict[str, float],
    stocks: dict[str, dict[str, float]],
    blend: dict[str, float],
) -> dict[str, object]:
    """Expand a reference blend into the complete charging plan."""
    feed_l = feed_m3 * 1000.0
    volumes = {stream_id: fractions[stream_id] * feed_l for stream_id in STREAM_IDS}
    masses = {
        stream_id: volumes[stream_id] * stocks[stream_id]["density_kg_l"]
        for stream_id in STREAM_IDS
    }
    stage_rows = []
    for index, stage_fraction in enumerate(stages, start=1):
        stage_duration = duration_min * stage_fraction
        stage_volumes = {
            stream_id: volumes[stream_id] * stage_fraction for stream_id in STREAM_IDS
        }
        stage_rows.append(
            {
                "stage": index,
                "duration_min": stage_duration,
                "volumes_l": stage_volumes,
                "flows_l_h": {
                    stream_id: stage_volumes[stream_id] / (stage_duration / 60.0)
                    for stream_id in STREAM_IDS
                },
            }
        )
    return {
        "feed_m3": feed_m3,
        "feed_l": feed_l,
        "total_metal_mol": blend["total_metal_mol_l"] * feed_l,
        "free_acid_mol": blend["free_acid_mol_l"] * feed_l,
        "metal_moles": {
            metal: blend[f"{metal}_mol_l"] * feed_l for metal in METAL_KEYS
        },
        "stock_volume_l": volumes,
        "stock_mass_kg": masses,
        "stages": stage_rows,
    }


def _reference_reaction(
    metal_moles: dict[str, float],
    acid_mol: float,
    excess: float,
    wt_fraction: float,
    density: float,
) -> dict[str, float]:
    """Compute caustic and byproduct masses independently."""
    total_metal = sum(metal_moles[metal] for metal in METAL_KEYS)
    caustic_mol = (2.0 * total_metal + acid_mol) * (1.0 + excess)
    solution_kg = (
        caustic_mol * SODIUM_HYDROXIDE_G_PER_MOL / wt_fraction / 1000.0
    )
    solids_kg = (
        metal_moles["ni"] * NICKEL_HYDROXIDE_G_PER_MOL
        + metal_moles["co"] * COBALT_HYDROXIDE_G_PER_MOL
        + metal_moles["mn"] * MANGANESE_HYDROXIDE_G_PER_MOL
    ) / 1000.0
    sulfate_kg = (
        (total_metal + acid_mol / 2.0) * SODIUM_SULFATE_G_PER_MOL / 1000.0
    )
    return {
        "caustic_pure_mol": caustic_mol,
        "caustic_solution_kg": solution_kg,
        "caustic_solution_l": solution_kg / density,
        "hydroxide_solids_kg": solids_kg,
        "sodium_sulfate_kg": sulfate_kg,
    }


def _reference_conditioning(
    batch: dict[str, object],
    reaction: dict[str, float],
    limit: float,
    solid_density: float,
    capacity: float,
) -> dict[str, float]:
    """Compute post-reaction dilution and slurry volume independently."""
    feed_mass = sum(batch["stock_mass_kg"].values())
    liquid_before = (
        feed_mass + reaction["caustic_solution_kg"] - reaction["hydroxide_solids_kg"]
    )
    water_kg = max(
        0.0, reaction["sodium_sulfate_kg"] / limit - liquid_before
    )
    final_liquid = liquid_before + water_kg
    final_volume = (
        batch["feed_m3"]
        + reaction["caustic_solution_l"] / 1000.0
        + water_kg / 1000.0
        + reaction["hydroxide_solids_kg"] / solid_density / 1000.0
    )
    if final_volume > capacity:
        raise ValueError("reference working volume exceeded")
    return {
        "feed_mass_kg": feed_mass,
        "liquid_mass_before_dilution_kg": liquid_before,
        "dilution_water_kg": water_kg,
        "dilution_water_l": water_kg,
        "final_liquid_mass_kg": final_liquid,
        "sodium_sulfate_wt_fraction": reaction["sodium_sulfate_kg"] / final_liquid,
        "final_slurry_volume_m3": final_volume,
    }


def _reference_crystallization(
    conditioning: dict[str, float],
    cold_limit: float,
) -> dict[str, float]:
    """Calculate hydrate crystallization using a mass-ratio balance."""
    ratio = 322.19494 / 142.04214
    liquid_mass = conditioning["final_liquid_mass_kg"]
    current_fraction = conditioning["sodium_sulfate_wt_fraction"]
    sulfate_mass = liquid_mass * current_fraction
    if current_fraction <= cold_limit:
        crystallized = 0.0
    else:
        crystallized = (
            cold_limit * liquid_mass - sulfate_mass
        ) / (ratio * cold_limit - 1.0)
    hydrate_mass = ratio * crystallized
    remaining_liquid = liquid_mass - hydrate_mass
    remaining_sulfate = sulfate_mass - crystallized
    return {
        "sodium_sulfate_decahydrate_kg": hydrate_mass,
        "crystallized_sulfate_kg": crystallized,
        "remaining_liquid_kg": remaining_liquid,
        "remaining_sodium_sulfate_kg": remaining_sulfate,
        "remaining_sodium_sulfate_wt_fraction": remaining_sulfate
        / remaining_liquid,
    }


def _reference_washing(
    crystallization: dict[str, float],
    moisture_ratio: float,
    target_fraction: float,
) -> dict[str, float]:
    """Solve the two-stage countercurrent wash balance independently."""
    solid = crystallization["sodium_sulfate_decahydrate_kg"]
    current = crystallization["remaining_sodium_sulfate_wt_fraction"]
    entrained = solid * moisture_ratio
    mother_liquor = crystallization["remaining_liquid_kg"]
    feed_sulfate = mother_liquor * current
    if target_fraction >= current:
        wash_ratio = 0.0
        stage1 = current
        final = current
    else:
        wash_water_root = (
            -mother_liquor
            + math.sqrt(
                mother_liquor**2
                + 4.0
                * entrained
                * mother_liquor
                * (current - target_fraction)
                / target_fraction
            )
        ) / 2.0
        wash_water = max(0.0, wash_water_root)
        wash_ratio = wash_water / solid
        stage1 = target_fraction * (entrained + wash_water) / entrained
        final = target_fraction
    wash_water = wash_ratio * solid
    final_sulfate = entrained * final
    filtrate_sulfate = max(0.0, feed_sulfate - final_sulfate)
    recovery = 0.0 if feed_sulfate == 0 else filtrate_sulfate / feed_sulfate
    return {
        "dry_solid_kg": solid,
        "entrained_liquor_kg": entrained,
        "wash_water_kg": wash_water,
        "stage1_liquid_sulfate_wt_fraction": stage1,
        "final_cake_sulfate_kg": final_sulfate,
        "filtrate_sulfate_kg": filtrate_sulfate,
        "sulfate_recovery_fraction": recovery,
        "final_cake_sulfate_wt_fraction": final,
    }


def _reference_multistage(
    crystallization: dict[str, float],
    moisture_ratio: float,
    target_fraction: float,
    wash_ratio: float,
    max_stages: int,
) -> dict[str, object]:
    """Search stage counts using independent steady-state equations."""
    solid = crystallization["sodium_sulfate_decahydrate_kg"]
    mother_liquid = crystallization["remaining_liquid_kg"]
    initial_fraction = crystallization["remaining_sodium_sulfate_wt_fraction"]
    entrained = solid * moisture_ratio
    wash_water = solid * wash_ratio
    for stages in range(1, max_stages + 1):
        matrix = [[0.0 for _ in range(stages)] for _ in range(stages)]
        rhs = [0.0 for _ in range(stages)]
        if stages == 1:
            matrix[0][0] = mother_liquid + wash_water
            rhs[0] = mother_liquid * initial_fraction
        else:
            matrix[0][0] = mother_liquid + wash_water
            matrix[0][1] = -wash_water
            rhs[0] = mother_liquid * initial_fraction
            for stage in range(1, stages - 1):
                matrix[stage][stage - 1] = -entrained
                matrix[stage][stage] = entrained + wash_water
                matrix[stage][stage + 1] = -wash_water
            matrix[-1][-2] = -entrained
            matrix[-1][-1] = entrained + wash_water
        fractions = _reference_solve(matrix, rhs)
        if fractions[-1] <= target_fraction:
            feed_sulfate = mother_liquid * initial_fraction
            final_cake_sulfate = entrained * fractions[-1]
            filtrate_sulfate = feed_sulfate - final_cake_sulfate
            return {
                "stages": stages,
                "dry_solid_kg": solid,
                "entrained_liquor_kg_per_stage": entrained,
                "total_wash_water_kg": wash_water,
                "stage_liquid_sulfate_wt_fractions": fractions,
                "final_cake_sulfate_kg": final_cake_sulfate,
                "sulfate_recovery_fraction": filtrate_sulfate / feed_sulfate,
                "final_cake_sulfate_wt_fraction": fractions[-1],
            }
    raise ValueError("reference wash budget cannot meet target")


def _demo_rows() -> list[dict[str, str]]:
    """Read the bundled simulated stock rows."""
    with (DATA / "stocks.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _demo_campaign() -> dict[str, object]:
    """Read the bundled campaign parameters."""
    return json.loads((DATA / "campaign.json").read_text(encoding="utf-8"))


def _reference_report(
    raw_rows: list[dict[str, str]],
    campaign: dict[str, object],
) -> dict[str, object]:
    """Construct the entire report from independent reference functions."""
    stocks = _reference_normalize(raw_rows)
    blend_result = _reference_blend(
        stocks,
        campaign["target_ratio"],
        float(campaign["target_total_metal_mol_l"]),
    )
    batch = _reference_batch(
        float(campaign["batch_feed_m3"]),
        [float(value) for value in campaign["stage_fractions"]],
        float(campaign["feeding_duration_min"]),
        blend_result["fractions"],
        stocks,
        blend_result["blend"],
    )
    reaction = _reference_reaction(
        batch["metal_moles"],
        batch["free_acid_mol"],
        float(campaign["oh_excess_fraction"]),
        float(campaign["caustic_wt_fraction"]),
        float(campaign["caustic_density_kg_l"]),
    )
    conditioning = _reference_conditioning(
        batch,
        reaction,
        float(campaign["max_na2so4_wt_fraction"]),
        float(campaign["precipitate_density_kg_l"]),
        float(campaign["working_volume_m3"]),
    )
    crystallization = _reference_crystallization(
        conditioning,
        float(campaign["cold_na2so4_solubility_wt_fraction"]),
    )
    washing = _reference_washing(
        crystallization,
        float(campaign["cake_moisture_kg_per_kg_solid"]),
        float(campaign["cake_wash_target_sulfate_wt_fraction"]),
    )
    multistage_washing = _reference_multistage(
        crystallization,
        float(campaign["cake_moisture_kg_per_kg_solid"]),
        float(campaign["cake_wash_target_sulfate_wt_fraction"]),
        float(campaign["wash_water_budget_kg_per_kg_solid"]),
        int(campaign["max_wash_stages"]),
    )
    return {
        "batch_id": campaign["batch_id"],
        "stocks": stocks,
        "blend_fractions": blend_result["fractions"],
        "blend": blend_result["blend"],
        "batch": batch,
        "reaction": reaction,
        "conditioning": conditioning,
        "crystallization": crystallization,
        "washing": washing,
        "multistage_washing": multistage_washing,
    }


def _write_stocks(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    """Write arbitrary stock rows for parser and command tests."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _run_cli(stocks: Path, campaign: Path, output: Path) -> subprocess.CompletedProcess[str]:
    """Run the feed audit command in a subprocess."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "precursor_feed.cli",
            str(stocks),
            str(campaign),
            str(output),
        ],
        cwd="/workspace",
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_c1_dilution_and_molarity():
    """Apply the 100-fold dilution before nickel molar conversion."""
    expected = _reference_molarity(219.6, 1.0, 100.0, NICKEL_G_PER_MOL)
    actual = element_molarity_mol_l(219.6, 1.0, 100.0, NICKEL_G_PER_MOL)
    assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_c1_cobalt_and_manganese_masses():
    """Use the separate cobalt and manganese atomic masses."""
    expected_co = _reference_molarity(1557.8, 2.0, 100.0, COBALT_G_PER_MOL)
    expected_mn = _reference_molarity(1279.1, 2.0, 100.0, MANGANESE_G_PER_MOL)
    actual_co = element_molarity_mol_l(1557.8, 2.0, 100.0, COBALT_G_PER_MOL)
    actual_mn = element_molarity_mol_l(1279.1, 2.0, 100.0, MANGANESE_G_PER_MOL)
    assert actual_co == pytest.approx(expected_co, rel=1e-12, abs=1e-12)
    assert actual_mn == pytest.approx(expected_mn, rel=1e-12, abs=1e-12)


def test_c1_identity_dilution_boundary():
    """Keep a one-to-one sample preparation unchanged."""
    actual = element_molarity_mol_l(58.6934, 5.0, 5.0, NICKEL_G_PER_MOL)
    assert actual == pytest.approx(0.001, rel=1e-12, abs=1e-12)


def test_c1_rejects_nonpositive_sample():
    """Reject a zero sample volume before division."""
    with pytest.raises(ValueError):
        element_molarity_mol_l(100.0, 0.0, 100.0, NICKEL_G_PER_MOL)


def test_c1_iron_uses_same_dilution():
    """Scale the diluted iron reading back to the original stock."""
    actual = iron_mass_concentration_mg_l(0.10, 1.0, 100.0)
    expected = _reference_diluted(0.10, 1.0, 100.0)
    assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_c2_demo_blend_fractions():
    """Recover the unique four-stream fractions for the demo batch."""
    campaign = _demo_campaign()
    stocks = _reference_normalize(_demo_rows())
    expected = _reference_blend(
        stocks,
        campaign["target_ratio"],
        float(campaign["target_total_metal_mol_l"]),
    )
    actual = solve_blend(
        stocks,
        campaign["target_ratio"],
        float(campaign["target_total_metal_mol_l"]),
    )
    fraction_error = max(
        abs(actual["fractions"][stream_id] - expected["fractions"][stream_id])
        for stream_id in STREAM_IDS
    )
    assert fraction_error < 1e-10


def test_c2_blend_matches_target_ratio():
    """Hit both the total metal molarity and normalized 8:1:1 ratio."""
    campaign = _demo_campaign()
    stocks = _reference_normalize(_demo_rows())
    actual = solve_blend(
        stocks,
        campaign["target_ratio"],
        float(campaign["target_total_metal_mol_l"]),
    )
    ratio = [actual["blend"][f"{metal}_mol_l"] for metal in METAL_KEYS]
    assert actual["blend"]["total_metal_mol_l"] == pytest.approx(
        float(campaign["target_total_metal_mol_l"]), rel=1e-10, abs=1e-10
    )
    assert ratio[0] / ratio[1] == pytest.approx(8.0, rel=1e-10, abs=1e-10)
    assert ratio[1] / ratio[2] == pytest.approx(1.0, rel=1e-10, abs=1e-10)


def test_c2_iron_ppm_uses_weighted_density():
    """Divide blended iron mg/L by blended density kg/L."""
    campaign = _demo_campaign()
    stocks = _reference_normalize(_demo_rows())
    expected = _reference_blend(
        stocks,
        campaign["target_ratio"],
        float(campaign["target_total_metal_mol_l"]),
    )
    actual = solve_blend(
        stocks,
        campaign["target_ratio"],
        float(campaign["target_total_metal_mol_l"]),
    )
    assert actual["blend"]["iron_ppm"] == pytest.approx(
        expected["blend"]["iron_ppm"], rel=1e-10, abs=1e-10
    )


def test_c2_rejects_negative_fraction():
    """Reject a high total-metal target that needs a negative recycle fraction."""
    campaign = _demo_campaign()
    stocks = _reference_normalize(_demo_rows())
    with pytest.raises(ValueError):
        solve_blend(stocks, campaign["target_ratio"], 2.0)


def test_c2_rejects_singular_stock_matrix():
    """Reject four identical stock columns as a singular blend."""
    template = {
        "ni_mol_l": 1.0,
        "co_mol_l": 0.1,
        "mn_mol_l": 0.1,
        "iron_mg_l": 2.0,
        "density_kg_l": 1.2,
        "free_acid_mol_l": 0.01,
    }
    stocks = {stream_id: dict(template) for stream_id in STREAM_IDS}
    with pytest.raises(ValueError):
        solve_blend(stocks, {"ni": 8.0, "co": 1.0, "mn": 1.0}, 1.2)


def test_c3_stock_volume_from_fraction():
    """Expand volumetric fractions into litres of each stock."""
    campaign = _demo_campaign()
    stocks = _reference_normalize(_demo_rows())
    blend_result = _reference_blend(
        stocks,
        campaign["target_ratio"],
        float(campaign["target_total_metal_mol_l"]),
    )
    expected = _reference_batch(
        float(campaign["batch_feed_m3"]),
        [float(value) for value in campaign["stage_fractions"]],
        float(campaign["feeding_duration_min"]),
        blend_result["fractions"],
        stocks,
        blend_result["blend"],
    )
    actual = batch_plan(
        float(campaign["batch_feed_m3"]),
        [float(value) for value in campaign["stage_fractions"]],
        float(campaign["feeding_duration_min"]),
        blend_result["fractions"],
        stocks,
        blend_result["blend"],
    )
    volume_error = max(
        abs(actual["stock_volume_l"][stream_id] - expected["stock_volume_l"][stream_id])
        for stream_id in STREAM_IDS
    )
    assert volume_error < 1e-7


def test_c3_stock_mass_uses_density():
    """Convert each stock volume to mass with its own density."""
    campaign = _demo_campaign()
    stocks = _reference_normalize(_demo_rows())
    blend_result = _reference_blend(
        stocks,
        campaign["target_ratio"],
        float(campaign["target_total_metal_mol_l"]),
    )
    expected = _reference_batch(
        12.0,
        [0.18, 0.52, 0.30],
        360.0,
        blend_result["fractions"],
        stocks,
        blend_result["blend"],
    )
    actual = batch_plan(
        12.0,
        [0.18, 0.52, 0.30],
        360.0,
        blend_result["fractions"],
        stocks,
        blend_result["blend"],
    )
    mass_error = max(
        abs(actual["stock_mass_kg"][stream_id] - expected["stock_mass_kg"][stream_id])
        for stream_id in STREAM_IDS
    )
    assert mass_error < 1e-7


def test_c3_stage_volumes_conserve_batch():
    """Make the three stage volumes sum to the full stock volume."""
    campaign = _demo_campaign()
    stocks = _reference_normalize(_demo_rows())
    blend_result = _reference_blend(
        stocks,
        campaign["target_ratio"],
        float(campaign["target_total_metal_mol_l"]),
    )
    actual = batch_plan(
        12.0,
        [0.18, 0.52, 0.30],
        360.0,
        blend_result["fractions"],
        stocks,
        blend_result["blend"],
    )
    stage_errors = [
        abs(
            sum(stage["volumes_l"][stream_id] for stage in actual["stages"])
            - actual["stock_volume_l"][stream_id]
        )
        for stream_id in STREAM_IDS
    ]
    assert max(stage_errors) < 1e-7
    assert [stage["duration_min"] for stage in actual["stages"]] == pytest.approx(
        [64.8, 187.2, 108.0], rel=1e-12, abs=1e-12
    )


def test_c3_stage_flow_uses_stage_duration():
    """Compute each stage flow from that stage's own duration."""
    stocks = _reference_normalize(_demo_rows())
    fractions = {stream_id: 0.25 for stream_id in STREAM_IDS}
    blend = {
        "ni_mol_l": 0.4,
        "co_mol_l": 0.05,
        "mn_mol_l": 0.05,
        "total_metal_mol_l": 0.5,
        "iron_ppm": 3.9,
        "density_kg_l": 1.34,
        "free_acid_mol_l": 0.01,
    }
    actual = batch_plan(4.0, [0.2, 0.5, 0.3], 300.0, fractions, stocks, blend)
    expected_first = 4000.0 * 0.25 * 0.2 / ((300.0 * 0.2) / 60.0)
    assert actual["stages"][0]["flows_l_h"]["recycle"] == pytest.approx(
        expected_first, rel=1e-12, abs=1e-12
    )


def test_c3_total_metal_and_acid_moles():
    """Scale mixed molarities by the batch volume in litres."""
    stocks = _reference_normalize(_demo_rows())
    fractions = {stream_id: 0.25 for stream_id in STREAM_IDS}
    blend = {
        "ni_mol_l": 0.4,
        "co_mol_l": 0.05,
        "mn_mol_l": 0.05,
        "total_metal_mol_l": 0.5,
        "iron_ppm": 3.9,
        "density_kg_l": 1.34,
        "free_acid_mol_l": 0.01,
    }
    actual = batch_plan(2.5, [0.2, 0.5, 0.3], 200.0, fractions, stocks, blend)
    assert actual["total_metal_mol"] == pytest.approx(1250.0, rel=1e-12)
    assert actual["metal_moles"]["ni"] == pytest.approx(1000.0, rel=1e-12)
    assert actual["free_acid_mol"] == pytest.approx(25.0, rel=1e-12)


def test_c4_precipitation_caustic_stoichiometry():
    """Consume two hydroxide equivalents per transition metal."""
    actual = reaction_plan({"ni": 1000.0, "co": 100.0, "mn": 100.0}, 0.0, 0.0, 1.0, 1.0)
    assert actual["caustic_pure_mol"] == pytest.approx(2400.0, rel=1e-12)


def test_c4_acid_and_excess_in_caustic_demand():
    """Add free acid equivalents before applying process excess."""
    actual = reaction_plan({"ni": 1000.0, "co": 100.0, "mn": 100.0}, 50.0, 0.02, 1.0, 1.1)
    expected = (2450.0) * 1.02
    assert actual["caustic_pure_mol"] == pytest.approx(expected, rel=1e-12)


def test_c4_hydroxide_solids_mass():
    """Sum each metal's hydroxide molar mass contribution."""
    actual = reaction_plan({"ni": 1000.0, "co": 100.0, "mn": 100.0}, 50.0, 0.02, 0.32, 1.345)
    expected = (
        1000.0 * NICKEL_HYDROXIDE_G_PER_MOL
        + 100.0 * COBALT_HYDROXIDE_G_PER_MOL
        + 100.0 * MANGANESE_HYDROXIDE_G_PER_MOL
    ) / 1000.0
    assert actual["hydroxide_solids_kg"] == pytest.approx(expected, rel=1e-12)


def test_c4_sodium_sulfate_from_metal_and_acid():
    """Count one sulfate per metal and one per two acid equivalents."""
    actual = reaction_plan({"ni": 1000.0, "co": 100.0, "mn": 100.0}, 50.0, 0.02, 0.32, 1.345)
    expected = (1200.0 + 25.0) * SODIUM_SULFATE_G_PER_MOL / 1000.0
    assert actual["sodium_sulfate_kg"] == pytest.approx(expected, rel=1e-12)


def test_c4_rejects_bad_caustic_assay():
    """Reject a caustic solution with zero mass fraction."""
    with pytest.raises(ValueError):
        reaction_plan({"ni": 10.0, "co": 1.0, "mn": 1.0}, 0.0, 0.01, 0.0, 1.2)


def test_c5_rejects_duplicate_streams():
    """Reject duplicate stream IDs even when there are four rows."""
    rows = _demo_rows()
    rows[1]["stream_id"] = "recycle"
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        stocks_path = directory_path / "stocks.csv"
        output_path = directory_path / "plan.json"
        _write_stocks(stocks_path, rows, list(rows[0]))
        completed = _run_cli(stocks_path, DATA / "campaign.json", output_path)
        assert completed.returncode != 0
        assert not output_path.exists()


def test_c5_rejects_missing_stream():
    """Reject a stock table that omits one required stream."""
    rows = _demo_rows()[:3]
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        stocks_path = directory_path / "stocks.csv"
        output_path = directory_path / "plan.json"
        _write_stocks(stocks_path, rows, list(rows[0]))
        completed = _run_cli(stocks_path, DATA / "campaign.json", output_path)
        assert completed.returncode != 0
        assert not output_path.exists()


def test_c5_rejects_iron_over_limit():
    """Reject a blended iron mass fraction above the campaign limit."""
    with pytest.raises(ValueError):
        check_iron_limit(12.01, 12.0)


def test_c5_rejects_bad_stage_fraction():
    """Reject stage fractions whose sum is not one."""
    campaign = _demo_campaign()
    campaign["stage_fractions"] = [0.2, 0.5, 0.4]
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        campaign_path = directory_path / "campaign.json"
        output_path = directory_path / "plan.json"
        campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
        completed = _run_cli(DATA / "stocks.csv", campaign_path, output_path)
        assert completed.returncode != 0
        assert not output_path.exists()


def test_c5_cli_invalid_preserves_existing_output():
    """Leave an existing report untouched when a stock value is invalid."""
    rows = _demo_rows()
    rows[0]["ni_icp_mg_l"] = "-1.0"
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        stocks_path = directory_path / "stocks.csv"
        campaign_path = directory_path / "campaign.json"
        output_path = directory_path / "plan.json"
        _write_stocks(stocks_path, rows, list(rows[0]))
        campaign_path.write_text(json.dumps(_demo_campaign()), encoding="utf-8")
        output_path.write_text("existing plan\n", encoding="utf-8")
        completed = _run_cli(stocks_path, campaign_path, output_path)
        assert completed.returncode != 0
        assert output_path.read_text(encoding="utf-8") == "existing plan\n"


def test_c6_no_dilution_when_under_limit():
    """Leave dilution water at zero when the sulfate fraction is already low."""
    batch = {
        "feed_m3": 2.0,
        "stock_mass_kg": {
            "recycle": 400.0,
            "ni_sulfate": 0.0,
            "co_sulfate": 0.0,
            "mn_sulfate": 0.0,
        },
    }
    reaction = {
        "caustic_solution_kg": 100.0,
        "caustic_solution_l": 74.0,
        "hydroxide_solids_kg": 50.0,
        "sodium_sulfate_kg": 40.0,
    }
    actual = conditioning_plan(batch, reaction, 0.15, 2.0, 5.0)
    expected = _reference_conditioning(batch, reaction, 0.15, 2.0, 5.0)
    assert actual["dilution_water_kg"] == pytest.approx(0.0, abs=1e-12)
    assert actual["sodium_sulfate_wt_fraction"] == pytest.approx(
        expected["sodium_sulfate_wt_fraction"], rel=1e-12
    )


def test_c6_demo_water_addition_to_limit():
    """Add water until the demo sodium sulfate fraction reaches its upper limit."""
    report = _reference_report(_demo_rows(), _demo_campaign())
    expected = report["conditioning"]
    actual = conditioning_plan(
        report["batch"],
        report["reaction"],
        0.13,
        2.1,
        17.0,
    )
    assert actual["dilution_water_kg"] > 0.0
    assert actual["dilution_water_l"] == pytest.approx(
        actual["dilution_water_kg"], abs=1e-12
    )
    assert actual["sodium_sulfate_wt_fraction"] == pytest.approx(
        expected["sodium_sulfate_wt_fraction"], rel=1e-10, abs=1e-12
    )
    assert actual["final_slurry_volume_m3"] == pytest.approx(
        expected["final_slurry_volume_m3"], rel=1e-10, abs=1e-9
    )


def test_c6_rejects_working_volume_overflow():
    """Reject a dilution plan that cannot fit in the reactor working volume."""
    report = _reference_report(_demo_rows(), _demo_campaign())
    with pytest.raises(ValueError):
        conditioning_plan(report["batch"], report["reaction"], 0.13, 2.1, 15.0)


def test_c7_decahydrate_stoichiometry():
    """Account for both sulfate and crystallization water in the hydrate mass."""
    report = _reference_report(_demo_rows(), _demo_campaign())
    expected = report["crystallization"]
    actual = crystallization_plan(report["conditioning"], 0.08)
    assert actual["crystallized_sulfate_kg"] > 0.0
    assert actual["sodium_sulfate_decahydrate_kg"] == pytest.approx(
        expected["sodium_sulfate_decahydrate_kg"], rel=1e-10, abs=1e-9
    )
    assert actual["remaining_liquid_kg"] == pytest.approx(
        expected["remaining_liquid_kg"], rel=1e-10, abs=1e-9
    )
    assert actual["remaining_sodium_sulfate_wt_fraction"] == pytest.approx(
        0.08, rel=1e-10, abs=1e-12
    )


def test_c7_saturated_boundary_has_no_crystals():
    """Leave the liquid unchanged when it already sits at the cold solubility."""
    conditioning = {
        "final_liquid_mass_kg": 1000.0,
        "sodium_sulfate_wt_fraction": 0.08,
    }
    actual = crystallization_plan(conditioning, 0.08)
    assert actual["sodium_sulfate_decahydrate_kg"] == pytest.approx(
        0.0, abs=1e-12
    )
    assert actual["remaining_liquid_kg"] == pytest.approx(1000.0, abs=1e-12)
    assert actual["remaining_sodium_sulfate_wt_fraction"] == pytest.approx(
        0.08, abs=1e-12
    )


def test_c7_rejects_invalid_cold_solubility():
    """Reject a cold-end solubility outside the physically supported range."""
    conditioning = {
        "final_liquid_mass_kg": 1000.0,
        "sodium_sulfate_wt_fraction": 0.13,
    }
    with pytest.raises(ValueError):
        crystallization_plan(conditioning, 0.4)


def test_c8_countercurrent_wash_balance():
    """Meet the cake sulfate target with the minimum two-stage wash water."""
    report = _reference_report(_demo_rows(), _demo_campaign())
    expected = report["washing"]
    actual = washing_plan(report["crystallization"], 0.30, 0.01)
    assert actual["wash_water_kg"] > 0.0
    assert actual["stage1_liquid_sulfate_wt_fraction"] == pytest.approx(
        expected["stage1_liquid_sulfate_wt_fraction"], rel=1e-10, abs=1e-12
    )
    assert actual["wash_water_kg"] == pytest.approx(
        expected["wash_water_kg"], rel=1e-10, abs=1e-9
    )
    assert actual["final_cake_sulfate_wt_fraction"] == pytest.approx(
        0.01, rel=1e-12, abs=1e-12
    )
    assert actual["sulfate_recovery_fraction"] == pytest.approx(
        expected["sulfate_recovery_fraction"], rel=1e-10, abs=1e-12
    )


def test_c8_target_equal_to_feed_needs_no_wash():
    """Return unchanged liquor when the wash target equals the feed fraction."""
    crystallization = {
        "sodium_sulfate_decahydrate_kg": 1000.0,
        "remaining_liquid_kg": 5000.0,
        "remaining_sodium_sulfate_kg": 400.0,
        "remaining_sodium_sulfate_wt_fraction": 0.08,
    }
    actual = washing_plan(crystallization, 0.3, 0.08)
    assert actual["wash_water_kg"] == pytest.approx(0.0, abs=1e-12)
    assert actual["stage1_liquid_sulfate_wt_fraction"] == pytest.approx(
        0.08, abs=1e-12
    )
    assert actual["sulfate_recovery_fraction"] == pytest.approx(
        0.94, rel=1e-12, abs=1e-12
    )


def test_c8_rejects_invalid_wash_inputs():
    """Reject a non-positive moisture ratio or impossible wash target."""
    crystallization = {
        "sodium_sulfate_decahydrate_kg": 1000.0,
        "remaining_liquid_kg": 5000.0,
        "remaining_sodium_sulfate_kg": 400.0,
        "remaining_sodium_sulfate_wt_fraction": 0.08,
    }
    with pytest.raises(ValueError):
        washing_plan(crystallization, 0.0, 0.01)
    with pytest.raises(ValueError):
        washing_plan(crystallization, 0.3, 0.0)


def test_c9_selects_minimum_stage_count():
    """Select three stages when the fixed wash budget cannot meet target in two."""
    report = _reference_report(_demo_rows(), _demo_campaign())
    expected = report["multistage_washing"]
    actual = multistage_washing_plan(
        report["crystallization"], 0.30, 0.01, 1.2, 5
    )
    assert actual["stages"] == 3
    assert actual["stages"] == expected["stages"]
    assert actual["total_wash_water_kg"] == pytest.approx(
        expected["total_wash_water_kg"], rel=1e-12
    )


def test_c9_stage_profiles_satisfy_final_target():
    """Keep all stage fractions finite and end at or below the target."""
    report = _reference_report(_demo_rows(), _demo_campaign())
    expected = report["multistage_washing"]
    actual = multistage_washing_plan(
        report["crystallization"], 0.30, 0.01, 1.2, 5
    )
    assert len(actual["stage_liquid_sulfate_wt_fractions"]) == 3
    assert all(value > 0.0 for value in actual["stage_liquid_sulfate_wt_fractions"])
    assert actual["stage_liquid_sulfate_wt_fractions"][-1] <= 0.01
    fraction_error = max(
        abs(
            actual["stage_liquid_sulfate_wt_fractions"][index]
            - expected["stage_liquid_sulfate_wt_fractions"][index]
        )
        for index in range(3)
    )
    assert fraction_error < 1e-10
    assert actual["sulfate_recovery_fraction"] == pytest.approx(
        expected["sulfate_recovery_fraction"], rel=1e-10, abs=1e-12
    )


def test_c9_rejects_unreachable_budget_and_bad_stage_limit():
    """Reject insufficient wash water and an invalid maximum stage count."""
    report = _reference_report(_demo_rows(), _demo_campaign())
    with pytest.raises(ValueError):
        multistage_washing_plan(report["crystallization"], 0.30, 0.01, 0.2, 5)
    with pytest.raises(ValueError):
        multistage_washing_plan(report["crystallization"], 0.30, 0.01, 1.2, 0)


def test_e2e_demo_report():
    """Generate and independently check the complete bundled report."""
    expected = _reference_report(_demo_rows(), _demo_campaign())
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "plan.json"
        completed = _run_cli(DATA / "stocks.csv", DATA / "campaign.json", output)
        assert completed.returncode == 0, completed.stderr
        actual = json.loads(output.read_text(encoding="utf-8"))
    assert set(actual) == {
        "batch_id",
        "stocks",
        "blend_fractions",
        "blend",
        "batch",
        "reaction",
        "conditioning",
        "crystallization",
        "washing",
        "multistage_washing",
    }
    assert actual["batch_id"] == expected["batch_id"]
    fraction_error = max(
        abs(
            actual["blend_fractions"][stream_id]
            - expected["blend_fractions"][stream_id]
        )
        for stream_id in STREAM_IDS
    )
    volume_error = max(
        abs(
            actual["batch"]["stock_volume_l"][stream_id]
            - expected["batch"]["stock_volume_l"][stream_id]
        )
        for stream_id in STREAM_IDS
    )
    assert fraction_error < 1e-10
    assert volume_error < 1e-7
    reaction_fields = (
        "caustic_pure_mol",
        "caustic_solution_kg",
        "caustic_solution_l",
        "hydroxide_solids_kg",
        "sodium_sulfate_kg",
    )
    reaction_error = max(
        abs(actual["reaction"][field] - expected["reaction"][field])
        for field in reaction_fields
    )
    assert reaction_error < 1e-7
    conditioning_fields = (
        "feed_mass_kg",
        "liquid_mass_before_dilution_kg",
        "dilution_water_kg",
        "final_liquid_mass_kg",
        "sodium_sulfate_wt_fraction",
        "final_slurry_volume_m3",
    )
    conditioning_error = max(
        abs(actual["conditioning"][field] - expected["conditioning"][field])
        for field in conditioning_fields
    )
    assert conditioning_error < 1e-7
    crystal_fields = (
        "sodium_sulfate_decahydrate_kg",
        "crystallized_sulfate_kg",
        "remaining_liquid_kg",
        "remaining_sodium_sulfate_kg",
        "remaining_sodium_sulfate_wt_fraction",
    )
    crystal_error = max(
        abs(actual["crystallization"][field] - expected["crystallization"][field])
        for field in crystal_fields
    )
    assert crystal_error < 1e-7
    washing_fields = (
        "dry_solid_kg",
        "entrained_liquor_kg",
        "wash_water_kg",
        "stage1_liquid_sulfate_wt_fraction",
        "final_cake_sulfate_kg",
        "filtrate_sulfate_kg",
        "sulfate_recovery_fraction",
        "final_cake_sulfate_wt_fraction",
    )
    washing_error = max(
        abs(actual["washing"][field] - expected["washing"][field])
        for field in washing_fields
    )
    assert washing_error < 1e-7
    multistage_fields = (
        "dry_solid_kg",
        "entrained_liquor_kg_per_stage",
        "total_wash_water_kg",
        "final_cake_sulfate_kg",
        "sulfate_recovery_fraction",
        "final_cake_sulfate_wt_fraction",
    )
    multistage_error = max(
        abs(
            actual["multistage_washing"][field]
            - expected["multistage_washing"][field]
        )
        for field in multistage_fields
    )
    assert actual["multistage_washing"]["stages"] == 3
    assert multistage_error < 1e-7


def test_e2e_reordered_columns():
    """Read a stock table by column name after reversing the column order."""
    rows = _demo_rows()
    expected = _reference_report(rows, _demo_campaign())
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        stocks_path = directory_path / "stocks.csv"
        output_path = directory_path / "plan.json"
        columns = list(reversed(list(rows[0])))
        _write_stocks(stocks_path, rows, columns)
        completed = _run_cli(stocks_path, DATA / "campaign.json", output_path)
        assert completed.returncode == 0, completed.stderr
        actual = json.loads(output_path.read_text(encoding="utf-8"))
    assert actual["blend"]["iron_ppm"] == pytest.approx(
        expected["blend"]["iron_ppm"], rel=1e-10, abs=1e-10
    )
    assert actual["reaction"]["caustic_solution_l"] == pytest.approx(
        expected["reaction"]["caustic_solution_l"], rel=1e-10, abs=1e-9
    )
