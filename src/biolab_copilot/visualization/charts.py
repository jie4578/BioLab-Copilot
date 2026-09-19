"""Deterministic PNG charts built only from structured upstream results."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

PALETTE = {
    "blue": "#1F4E78",
    "orange": "#C55A11",
    "green": "#548235",
    "gray": "#595959",
    "grid": "#D9E2F3",
    "warning": "#B45F06",
}


def _save(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path,
        dpi=150,
        format="png",
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "BioLab Copilot"},
    )
    plt.close(fig)


def _numeric(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("chart values must be finite")
    return result


def render_generic_chart(
    *,
    raw_points: list[dict[str, Any]],
    group_statistics: list[dict[str, Any]],
    unit: str,
    path: Path,
) -> None:
    """Plot every measurement row and overlay the already-computed group summaries."""
    groups = [str(item["group"]) for item in group_statistics]
    x_positions = {group: index for index, group in enumerate(groups)}
    fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=150)
    for group in groups:
        values = [
            _numeric(item["measurement"])
            for item in raw_points
            if str(item.get("group")) == group and item.get("measurement") is not None
        ]
        if values:
            n = len(values)
            offsets = [0.0] if n == 1 else [(-0.12 + 0.24 * i / (n - 1)) for i in range(n)]
            ax.scatter(
                [x_positions[group] + offset for offset in offsets],
                values,
                color=PALETTE["gray"],
                alpha=0.75,
                s=34,
                label="Measurement rows" if group == groups[0] else None,
                zorder=3,
            )
    means = [_numeric(item["mean"]) for item in group_statistics]
    yerr = [
        _numeric(item["sample_sd"]) if item.get("sample_sd") is not None else 0.0
        for item in group_statistics
    ]
    has_error = [item.get("sample_sd") is not None for item in group_statistics]
    for index, (mean, error, available) in enumerate(zip(means, yerr, has_error, strict=True)):
        ax.errorbar(
            index,
            mean,
            yerr=error if available else None,
            fmt="o",
            color=PALETTE["blue"],
            ecolor=PALETTE["blue"],
            capsize=4 if available else 0,
            markersize=8,
            label="Group mean ± sample SD" if index == 0 else None,
            zorder=4,
        )
    ax.set_title("Generic grouped measurements")
    ax.set_xlabel("Group")
    ax.set_ylabel(unit or "Measurement")
    ax.set_xticks(range(len(groups)), groups)
    ax.grid(axis="y", color=PALETTE["grid"], linewidth=0.8)
    ax.legend(loc="best", frameon=False)
    fig.text(
        0.01,
        0.01,
        "Measurement rows; counts are not independent biological n.",
        fontsize=8,
        color=PALETTE["gray"],
    )
    _save(fig, path)


def render_welch_chart(
    *,
    unit_values: list[dict[str, Any]],
    group_statistics: list[dict[str, Any]],
    unit: str,
    path: Path,
) -> None:
    """Plot only the experimental-unit values used by the Welch result."""
    groups = [str(item["group"]) for item in group_statistics]
    x_positions = {group: index for index, group in enumerate(groups)}
    fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=150)
    for group in groups:
        values = [
            _numeric(item["aggregated_value"])
            for item in unit_values
            if str(item.get("group")) == group
        ]
        n = len(values)
        offsets = [0.0] if n == 1 else [(-0.12 + 0.24 * i / (n - 1)) for i in range(n)]
        ax.scatter(
            [x_positions[group] + offset for offset in offsets],
            values,
            color=PALETTE["gray"],
            alpha=0.8,
            s=38,
            label="Experimental units" if group == groups[0] else None,
            zorder=3,
        )
    for index, item in enumerate(group_statistics):
        sd = item.get("sample_sd")
        ax.errorbar(
            index,
            _numeric(item["mean"]),
            yerr=_numeric(sd) if sd is not None else None,
            fmt="o",
            color=PALETTE["blue"],
            ecolor=PALETTE["blue"],
            capsize=4 if sd is not None else 0,
            markersize=8,
            label="Mean ± sample SD" if index == 0 else None,
            zorder=4,
        )
    ax.set_title("Welch comparison by experimental unit")
    ax.set_xlabel("Group")
    ax.set_ylabel(unit or "Measurement")
    ax.set_xticks(range(len(groups)), groups)
    ax.grid(axis="y", color=PALETTE["grid"], linewidth=0.8)
    ax.legend(loc="best", frameon=False)
    fig.text(
        0.01,
        0.01,
        "Experimental-unit level; technical repeats do not increase inferential n.",
        fontsize=8,
        color=PALETTE["gray"],
    )
    _save(fig, path)


def _four_pl_display(
    concentration: float,
    *,
    lower: float,
    upper: float,
    midpoint: float,
    slope: float,
    direction: str,
) -> float:
    """Pure display transform using the already-fitted 4PL parameters."""
    sign = 1.0 if direction == "increasing" else -1.0
    z = sign * slope * (math.log(concentration) - math.log(midpoint))
    if z >= 0:
        exp_term = math.exp(-z)
        logistic = 1.0 / (1.0 + exp_term)
    else:
        exp_term = math.exp(z)
        logistic = exp_term / (1.0 + exp_term)
    return lower + (upper - lower) * logistic


def render_elisa_curve_chart(
    *,
    curve: dict[str, Any],
    standard_records: list[dict[str, Any]],
    path: Path,
) -> None:
    positive_records = [
        item
        for item in standard_records
        if item.get("included")
        and item.get("parsed_concentration") is not None
        and _numeric(item["parsed_concentration"]) > 0
        and item.get("parsed_response") is not None
    ]
    fit_points = [
        item
        for item in curve["fit_points"]
        if _numeric(item["concentration"]) > 0
    ]
    span = curve.get("observed_standard_concentration_span")
    if not span or len(span) != 2:
        raise ValueError("ELISA chart requires an observed positive concentration span")
    lower = _numeric(curve["lower_asymptote"])
    upper = _numeric(curve["upper_asymptote"])
    midpoint = _numeric(curve["midpoint_concentration"])
    slope = _numeric(curve["slope_magnitude"])
    direction = str(curve["direction"])
    lo, hi = _numeric(span[0]), _numeric(span[1])
    if lo <= 0 or hi <= lo:
        raise ValueError("ELISA chart span must be positive and increasing")
    steps = 160
    log_lo, log_hi = math.log(lo), math.log(hi)
    curve_x = [math.exp(log_lo + (log_hi - log_lo) * index / (steps - 1)) for index in range(steps)]
    curve_y = [
        _four_pl_display(
            x,
            lower=lower,
            upper=upper,
            midpoint=midpoint,
            slope=slope,
            direction=direction,
        )
        for x in curve_x
    ]
    fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=150)
    ax.plot(curve_x, curve_y, color=PALETTE["blue"], linewidth=2, label="Fitted 4PL")
    ax.scatter(
        [_numeric(item["parsed_concentration"]) for item in positive_records],
        [_numeric(item["parsed_response"]) for item in positive_records],
        color=PALETTE["gray"],
        s=32,
        alpha=0.75,
        label="Raw standard records",
        zorder=3,
    )
    ax.scatter(
        [_numeric(item["concentration"]) for item in fit_points],
        [_numeric(item["observed"]) for item in fit_points],
        facecolors="white",
        edgecolors=PALETTE["orange"],
        s=50,
        linewidth=1.2,
        label="Fit levels",
        zorder=4,
    )
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ax.set_title(f"ELISA 4PL standard curve ({direction})")
    ax.set_xlabel(f"Concentration ({curve['concentration_unit']})")
    ax.set_ylabel(f"Response ({curve['response_unit']})")
    ax.grid(color=PALETTE["grid"], linewidth=0.8, which="both")
    ax.legend(loc="best", frameon=False)
    fig.text(
        0.01,
        0.01,
        (
            "Curve is shown only across the observed positive standard span. Zero "
            "concentration is listed in tables, not placed on the log axis."
        ),
        fontsize=7.5,
        color=PALETTE["gray"],
    )
    _save(fig, path)


def render_elisa_residual_chart(*, curve: dict[str, Any], path: Path) -> None:
    points = [
        item for item in curve["fit_points"] if _numeric(item["concentration"]) > 0
    ]
    fig, ax = plt.subplots(figsize=(8.0, 3.8), dpi=150)
    ax.axhline(0.0, color=PALETTE["gray"], linewidth=1)
    ax.scatter(
        [_numeric(item["concentration"]) for item in points],
        [_numeric(item["residual"]) for item in points],
        color=PALETTE["orange"],
        s=38,
        zorder=3,
    )
    ax.set_xscale("log")
    ax.set_xlabel(f"Concentration ({curve['concentration_unit']})")
    ax.set_ylabel(f"Residual ({curve['response_unit']})")
    ax.set_title("4PL residuals")
    ax.grid(color=PALETTE["grid"], linewidth=0.8, which="both")
    _save(fig, path)


def render_status_counts_chart(*, records: list[dict[str, Any]], path: Path) -> None:
    order = [
        "estimated_within_standard_span",
        "below_standard_span",
        "above_standard_span",
        "outside_model_domain",
        "near_asymptote_unstable",
        "numerical_failure",
    ]
    labels = [item.replace("_", " ") for item in order]
    counts = [sum(item.get("status") == status for item in records) for status in order]
    fig, ax = plt.subplots(figsize=(8.0, 4.2), dpi=150)
    ax.bar(labels, counts, color=PALETTE["blue"])
    ax.set_title("Sample estimate status counts")
    ax.set_ylabel("Measurement rows")
    ax.tick_params(axis="x", rotation=35)
    ax.grid(axis="y", color=PALETTE["grid"], linewidth=0.8)
    _save(fig, path)


__all__ = [
    "render_elisa_curve_chart",
    "render_elisa_residual_chart",
    "render_generic_chart",
    "render_status_counts_chart",
    "render_welch_chart",
]
