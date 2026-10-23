"""Solve the four-stream blend needed for the target precursor ratio."""

from __future__ import annotations

import math

from .constants import METAL_KEYS, STREAM_IDS


def _solve_linear(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a small dense linear system with partial pivoting."""
    size = len(rhs)
    rows = [list(row) + [float(rhs[index])] for index, row in enumerate(matrix)]
    scale = max(abs(value) for row in rows for value in row[:-1])
    pivot_tolerance = max(1.0, scale) * 1e-12
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) <= pivot_tolerance:
            raise ValueError("blend equations are singular")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        for item in range(column, size + 1):
            rows[column][item] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            if factor == 0.0:
                continue
            for item in range(column, size + 1):
                rows[row][item] -= factor * rows[column][item]
    return [rows[index][size] for index in range(size)]


def solve_blend(
    stocks: dict[str, dict[str, float]],
    target_ratio: dict[str, float],
    target_total_metal_mol_l: float,
) -> dict[str, object]:
    """Return stream fractions and composition for the target precursor blend."""
    if set(stocks) != set(STREAM_IDS):
        raise ValueError("blend requires exactly four known stock streams")
    target_total = float(target_total_metal_mol_l)
    if not math.isfinite(target_total) or target_total <= 0:
        raise ValueError("target total metal molarity must be positive")
    ratios: dict[str, float] = {}
    for metal in METAL_KEYS:
        value = float(target_ratio[metal])
        if not math.isfinite(value) or value < 0:
            raise ValueError("target ratios must be finite and non-negative")
        ratios[metal] = value
    ratio_sum = sum(ratios.values())
    if ratio_sum <= 0:
        raise ValueError("target ratio sum must be positive")
    normalized_ratio = {metal: ratios[metal] / ratio_sum for metal in METAL_KEYS}

    matrix: list[list[float]] = []
    rhs: list[float] = []
    for metal in METAL_KEYS:
        matrix.append([float(stocks[stream_id][f"{metal}_mol_l"]) for stream_id in STREAM_IDS])
        rhs.append(target_total * normalized_ratio[metal])
    matrix.append([1.0, 1.0, 1.0, 1.0])
    rhs.append(1.0)

    values = _solve_linear(matrix, rhs)
    fractions: dict[str, float] = {}
    for stream_id, value in zip(STREAM_IDS, values, strict=True):
        if not math.isfinite(value):
            raise ValueError("blend fraction is not finite")
        if value < -1e-9:
            raise ValueError(f"blend requires a negative fraction for {stream_id}")
        fractions[stream_id] = 0.0 if value < 0 else value
    total_fraction = sum(fractions.values())
    if abs(total_fraction - 1.0) > 1e-9:
        raise ValueError("blend fractions do not sum to one")
    fractions = {
        stream_id: value / total_fraction for stream_id, value in fractions.items()
    }

    blend = {
        f"{metal}_mol_l": sum(
            fractions[stream_id] * float(stocks[stream_id][f"{metal}_mol_l"])
            for stream_id in STREAM_IDS
        )
        for metal in METAL_KEYS
    }
    blend["total_metal_mol_l"] = sum(blend[f"{metal}_mol_l"] for metal in METAL_KEYS)
    blend["density_kg_l"] = sum(
        fractions[stream_id] * float(stocks[stream_id]["density_kg_l"])
        for stream_id in STREAM_IDS
    )
    blend["free_acid_mol_l"] = sum(
        fractions[stream_id] * float(stocks[stream_id]["free_acid_mol_l"])
        for stream_id in STREAM_IDS
    )
    blend["iron_ppm"] = sum(
        fractions[stream_id] * float(stocks[stream_id]["iron_mg_l"])
        for stream_id in STREAM_IDS
    ) / blend["density_kg_l"]

    residual = max(
        abs(blend[f"{metal}_mol_l"] - target_total * normalized_ratio[metal])
        for metal in METAL_KEYS
    )
    if residual > 1e-9:
        raise ValueError("blend residual is too large")
    return {"fractions": fractions, "blend": blend}
