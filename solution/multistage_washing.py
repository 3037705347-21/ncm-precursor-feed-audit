"""Estimate the fewest countercurrent wash stages for a fixed water budget."""

from __future__ import annotations

import math


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a dense linear system with partial pivoting."""
    size = len(rhs)
    rows = [list(row) + [float(rhs[index])] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) <= 1e-14:
            raise ValueError("washing equations are singular")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        for index in range(column, size + 1):
            rows[column][index] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            if factor == 0.0:
                continue
            for index in range(column, size + 1):
                rows[row][index] -= factor * rows[column][index]
    return [rows[index][size] for index in range(size)]


def _stage_fractions(
    stages: int,
    mother_liquid: float,
    entrained: float,
    wash_water: float,
    initial_fraction: float,
) -> list[float]:
    """Solve all stage liquid fractions for one candidate stage count."""
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
    return _solve(matrix, rhs)


def multistage_washing_plan(
    crystallization: dict[str, float],
    cake_moisture_kg_per_kg_solid: float,
    cake_wash_target_sulfate_wt_fraction: float,
    wash_water_budget_kg_per_kg_solid: float,
    max_wash_stages: int,
) -> dict[str, object]:
    """Return the fewest stages meeting the fixed-budget wash target."""
    required = {
        "sodium_sulfate_decahydrate_kg",
        "remaining_liquid_kg",
        "remaining_sodium_sulfate_wt_fraction",
    }
    if not isinstance(crystallization, dict) or not required.issubset(crystallization):
        raise ValueError("crystallization is missing required fields")
    solid = float(crystallization["sodium_sulfate_decahydrate_kg"])
    mother_liquid = float(crystallization["remaining_liquid_kg"])
    initial_fraction = float(crystallization["remaining_sodium_sulfate_wt_fraction"])
    moisture_ratio = float(cake_moisture_kg_per_kg_solid)
    target_fraction = float(cake_wash_target_sulfate_wt_fraction)
    wash_ratio = float(wash_water_budget_kg_per_kg_solid)
    if isinstance(max_wash_stages, bool) or not isinstance(max_wash_stages, int):
        raise ValueError("max_wash_stages must be an integer")
    if not all(
        math.isfinite(value)
        for value in (
            solid,
            mother_liquid,
            initial_fraction,
            moisture_ratio,
            target_fraction,
            wash_ratio,
        )
    ):
        raise ValueError("multistage washing inputs must be finite")
    if solid <= 0 or mother_liquid <= 0:
        raise ValueError("solid and mother liquid masses must be positive")
    if not 0.0 < initial_fraction <= 1.0:
        raise ValueError("mother-liquor sulfate fraction is out of range")
    if moisture_ratio <= 0 or wash_ratio <= 0:
        raise ValueError("moisture and wash water ratios must be positive")
    if not 0.0 < target_fraction <= initial_fraction:
        raise ValueError("wash target must be positive and no greater than the feed")
    if max_wash_stages < 1 or max_wash_stages > 8:
        raise ValueError("max_wash_stages must be between one and eight")

    entrained = solid * moisture_ratio
    wash_water = solid * wash_ratio
    if entrained > mother_liquid:
        raise ValueError("filter cake cannot retain more liquid than the mother liquor")
    for stages in range(1, max_wash_stages + 1):
        fractions = _stage_fractions(
            stages, mother_liquid, entrained, wash_water, initial_fraction
        )
        if any(not math.isfinite(value) or value < 0 for value in fractions):
            raise ValueError("washing equations produced a non-physical fraction")
        final_fraction = fractions[-1]
        if final_fraction <= target_fraction:
            feed_sulfate = mother_liquid * initial_fraction
            final_cake_sulfate = entrained * final_fraction
            filtrate_sulfate = max(0.0, feed_sulfate - final_cake_sulfate)
            return {
                "stages": stages,
                "dry_solid_kg": solid,
                "entrained_liquor_kg_per_stage": entrained,
                "total_wash_water_kg": wash_water,
                "stage_liquid_sulfate_wt_fractions": fractions,
                "final_cake_sulfate_kg": final_cake_sulfate,
                "sulfate_recovery_fraction": filtrate_sulfate / feed_sulfate,
                "final_cake_sulfate_wt_fraction": final_fraction,
            }
    raise ValueError("wash water budget cannot meet the target within the stage limit")
