"""Command-line entry point for the NCM precursor feed audit."""

from __future__ import annotations

import math
import sys

from .blending import solve_blend
from .charging import batch_plan
from .conditioning import conditioning_plan
from .crystallization import crystallization_plan
from .measurements import normalize_stocks
from .stoichiometry import reaction_plan
from .washing import washing_plan
from .multistage_washing import multistage_washing_plan
from .validation import (
    check_iron_limit,
    load_campaign,
    load_stocks,
    write_json_atomic,
)


def build_report(
    raw_stocks: list[dict[str, str]],
    campaign: dict[str, object],
) -> dict[str, object]:
    """Build a complete feed and reaction report from validated inputs."""
    stocks = normalize_stocks(raw_stocks)
    ratio = campaign["target_ratio"]
    target_total = float(campaign["target_total_metal_mol_l"])
    blend_result = solve_blend(stocks, ratio, target_total)
    batch = batch_plan(
        float(campaign["batch_feed_m3"]),
        [float(value) for value in campaign["stage_fractions"]],
        float(campaign["feeding_duration_min"]),
        blend_result["fractions"],
        stocks,
        blend_result["blend"],
    )
    reaction = reaction_plan(
        batch["metal_moles"],
        batch["free_acid_mol"],
        float(campaign["oh_excess_fraction"]),
        float(campaign["caustic_wt_fraction"]),
        float(campaign["caustic_density_kg_l"]),
    )
    conditioning = conditioning_plan(
        batch,
        reaction,
        float(campaign["max_na2so4_wt_fraction"]),
        float(campaign["precipitate_density_kg_l"]),
        float(campaign["working_volume_m3"]),
    )
    crystallization = crystallization_plan(
        conditioning,
        float(campaign["cold_na2so4_solubility_wt_fraction"]),
    )
    washing = washing_plan(
        crystallization,
        float(campaign["cake_moisture_kg_per_kg_solid"]),
        float(campaign["cake_wash_target_sulfate_wt_fraction"]),
    )
    multistage_washing = multistage_washing_plan(
        crystallization,
        float(campaign["cake_moisture_kg_per_kg_solid"]),
        float(campaign["cake_wash_target_sulfate_wt_fraction"]),
        float(campaign["wash_water_budget_kg_per_kg_solid"]),
        int(campaign["max_wash_stages"]),
    )
    check_iron_limit(
        float(blend_result["blend"]["iron_ppm"]),
        float(campaign["max_iron_ppm"]),
    )
    if not math.isfinite(float(batch["total_metal_mol"])):
        raise ValueError("batch total is not finite")
    return {
        "batch_id": str(campaign["batch_id"]),
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


def run(stocks_path: str, campaign_path: str, output_path: str) -> None:
    """Run one feed audit and write its report."""
    raw_stocks = load_stocks(stocks_path)
    campaign = load_campaign(campaign_path)
    report = build_report(raw_stocks, campaign)
    write_json_atomic(output_path, report)


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 3:
        print(
            "usage: python -m precursor_feed.cli STOCKS.csv CAMPAIGN.json PLAN.json",
            file=sys.stderr,
        )
        return 2
    try:
        run(*arguments)
    except (KeyError, OSError, TypeError, ValueError, ZeroDivisionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
