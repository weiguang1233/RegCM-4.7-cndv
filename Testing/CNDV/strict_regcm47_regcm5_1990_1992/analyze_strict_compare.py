#!/usr/bin/env python3
"""Paired RegCM4.7/RegCM5 CNDV comparison on one shared input grid."""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from strict_compare_io import (
    aligned_masks,
    closure_error,
    grid_index,
    read_history,
    read_hv,
    read_restart_drought,
    soil_table,
)


DATES = (19900101, 19910101, 19920101)
HV_NAMES = tuple(f"cndvab.clm.regcm.hv.{year}.nc" for year in (1991, 1992, 1993))
HISTORY_TOLERANCE_DAYS = 5.0e-5
PFT_NAMES = {
    0: "not_vegetated",
    1: "needleleaf_evergreen_temperate_tree",
    2: "needleleaf_evergreen_boreal_tree",
    3: "needleleaf_deciduous_boreal_tree",
    4: "broadleaf_evergreen_tropical_tree",
    5: "broadleaf_evergreen_temperate_tree",
    6: "broadleaf_deciduous_tropical_tree",
    7: "broadleaf_deciduous_temperate_tree",
    8: "broadleaf_deciduous_boreal_tree",
    9: "broadleaf_evergreen_shrub",
    10: "broadleaf_deciduous_temperate_shrub",
    11: "broadleaf_deciduous_boreal_shrub",
    12: "c3_arctic_grass",
    13: "c3_non_arctic_grass",
    14: "c4_grass",
    15: "c3_crop",
    16: "c3_irrigated",
}


def max_abs(values: np.ndarray) -> float:
    return float(np.max(np.abs(values))) if values.size else 0.0


def rmse(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values)))) if values.size else 0.0


def correlation(left: np.ndarray, right: np.ndarray) -> float:
    if left.size < 2 or np.std(left) == 0.0 or np.std(right) == 0.0:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def sign_class(values: np.ndarray, tolerance: float = 1.0e-8) -> np.ndarray:
    result = np.zeros(values.shape, dtype=np.int8)
    result[values > tolerance] = 1
    result[values < -tolerance] = -1
    return result


def assert_state_mapping(states: list[dict], tables: list[dict], label: str) -> None:
    reference = states[0]
    reference_table = tables[0]
    for index, (state, table, expected_date) in enumerate(zip(states, tables, DATES)):
        if state["mcdate"] != expected_date or state["mcsec"] != 0:
            raise ValueError(f"{label} state {index} has unexpected date/time")
        if state["numpft"] != 17:
            raise ValueError(f"{label} state {index} does not have 17 PFTs")
        if not np.array_equal(reference_table["keys"], table["keys"]):
            raise ValueError(f"{label} soil-PFT mapping changed at state {index}")
        if not np.allclose(reference["lon"], state["lon"], rtol=0.0, atol=1.0e-10):
            raise ValueError(f"{label} longitude changed at state {index}")
        if not np.allclose(reference["lat"], state["lat"], rtol=0.0, atol=1.0e-10):
            raise ValueError(f"{label} latitude changed at state {index}")
        if closure_error(state, table) > 1.0e-6:
            raise ValueError(f"{label} FPC closure failed at state {index}")
        if np.min(table["fpc"]) < -1.0e-10 or np.max(table["fpc"]) > 100.0 + 1.0e-10:
            raise ValueError(f"{label} FPC range failed at state {index}")
        if np.min(table["nind"]) < -1.0e-12:
            raise ValueError(f"{label} NIND range failed at state {index}")


def natural_grid(table: dict[str, np.ndarray], grid_count: int) -> np.ndarray:
    natural = (table["pft"] >= 1) & (table["pft"] <= 14)
    index = grid_index(table["gridcell"][natural], grid_count)
    return np.bincount(index, weights=table["fpc"][natural], minlength=grid_count)


def dominant_grid(table: dict[str, np.ndarray], grid_count: int) -> np.ndarray:
    matrix = np.zeros((grid_count, 14), dtype=np.float64)
    for pft_id in range(1, 15):
        selected = table["pft"] == pft_id
        index = grid_index(table["gridcell"][selected], grid_count)
        matrix[index, pft_id - 1] = table["fpc"][selected]
    result = np.argmax(matrix, axis=1).astype(np.int64) + 1
    result[np.max(matrix, axis=1) <= 1.0e-10] = 0
    return result


def state_mean(table: dict[str, np.ndarray], grid_count: int, pft_ids: range | tuple[int, ...]) -> float:
    selected = np.isin(table["pft"], list(pft_ids))
    return float(np.sum(table["fpc"][selected]) / grid_count)


def parse_history_date(history: dict[str, np.ndarray | str]) -> datetime:
    units = str(history["time_units"])
    prefix = "hours since "
    if not units.startswith(prefix):
        raise ValueError(f"unsupported history time units: {units}")
    origin_text = units[len(prefix):].strip()
    origin = datetime.strptime(origin_text, "%Y-%m-%d %H:%M:%S")
    return origin + timedelta(hours=float(history["time"]))


def sorted_history(history: dict[str, np.ndarray | str]) -> dict[str, np.ndarray]:
    lon = np.asarray(history["lon"])
    lat = np.asarray(history["lat"])
    drought = np.asarray(history["drought"])
    drought20 = np.asarray(history["drought20"])
    valid = (
        np.isfinite(lon)
        & np.isfinite(lat)
        & np.isfinite(drought)
        & np.isfinite(drought20)
        & (np.abs(drought) < 1.0e19)
        & (np.abs(drought20) < 1.0e19)
    )
    order = np.lexsort((lon[valid], lat[valid]))
    return {
        "lon": lon[valid][order],
        "lat": lat[valid][order],
        "drought": drought[valid][order],
        "drought20": drought20[valid][order],
    }


def drought_metrics(left: np.ndarray, right: np.ndarray, prefix: str) -> list[str]:
    difference = right - left
    exceed_left = left > 45.0
    exceed_right = right > 45.0
    return [
        f"{prefix}_regcm47_mean_days={float(np.mean(left)):.15g}",
        f"{prefix}_regcm5_mean_days={float(np.mean(right)):.15g}",
        f"{prefix}_paired_mean_difference_regcm5_minus_regcm47_days={float(np.mean(difference)):.15g}",
        f"{prefix}_paired_rmse_days={rmse(difference):.15g}",
        f"{prefix}_paired_correlation={correlation(left, right):.15g}",
        f"{prefix}_regcm47_columns_gt_45={int(np.count_nonzero(exceed_left))}",
        f"{prefix}_regcm5_columns_gt_45={int(np.count_nonzero(exceed_right))}",
        f"{prefix}_threshold_both_gt_45={int(np.count_nonzero(exceed_left & exceed_right))}",
        f"{prefix}_threshold_only_regcm47_gt_45={int(np.count_nonzero(exceed_left & ~exceed_right))}",
        f"{prefix}_threshold_only_regcm5_gt_45={int(np.count_nonzero(~exceed_left & exceed_right))}",
        f"{prefix}_threshold_neither_gt_45={int(np.count_nonzero(~exceed_left & ~exceed_right))}",
    ]


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: analyze_strict_compare.py REGCM47_OUTPUT REGCM5_OUTPUT OUTPUT_DIR", file=sys.stderr)
        return 2
    output47, output5, analysis = map(Path, sys.argv[1:])
    analysis.mkdir(parents=True, exist_ok=True)

    states47 = [read_hv(output47 / name) for name in HV_NAMES]
    states5 = [read_hv(output5 / name) for name in HV_NAMES]
    tables47 = [soil_table(state) for state in states47]
    tables5 = [soil_table(state) for state in states5]
    assert_state_mapping(states47, tables47, "RegCM4.7")
    assert_state_mapping(states5, tables5, "RegCM5")

    if not np.array_equal(tables47[0]["keys"], tables5[0]["keys"]):
        raise ValueError("cross-version soil-PFT mapping differs")
    if not np.allclose(states47[0]["lon"], states5[0]["lon"], rtol=0.0, atol=1.0e-10):
        raise ValueError("cross-version longitude differs")
    if not np.allclose(states47[0]["lat"], states5[0]["lat"], rtol=0.0, atol=1.0e-10):
        raise ValueError("cross-version latitude differs")
    mask47, mask5 = aligned_masks(states47[0]["regcm_mask"], states5[0]["regcm_mask"])
    if not np.array_equal(mask47, mask5):
        raise ValueError("cross-version regcm_mask differs")

    grid_count = len(np.asarray(states47[0]["lon"]))
    pft = tables47[0]["pft"]
    natural = (pft >= 1) & (pft <= 14)
    initial_fpc_error = tables5[0]["fpc"] - tables47[0]["fpc"]
    initial_nind_error = tables5[0]["nind"] - tables47[0]["nind"]
    if max_abs(initial_fpc_error) > 1.0e-12 or max_abs(initial_nind_error) > 1.0e-12:
        raise ValueError("cross-version initial state is not identical")

    delta47 = [tables47[1]["fpc"] - tables47[0]["fpc"], tables47[2]["fpc"] - tables47[1]["fpc"]]
    delta5 = [tables5[1]["fpc"] - tables5[0]["fpc"], tables5[2]["fpc"] - tables5[1]["fpc"]]
    natural47 = [natural_grid(table, grid_count) for table in tables47]
    natural5 = [natural_grid(table, grid_count) for table in tables5]
    dominant47 = [dominant_grid(table, grid_count) for table in tables47]
    dominant5 = [dominant_grid(table, grid_count) for table in tables5]
    grid_order = np.lexsort((np.asarray(states47[0]["lon"]), np.asarray(states47[0]["lat"])))
    reference_lon = np.asarray(states47[0]["lon"])[grid_order]
    reference_lat = np.asarray(states47[0]["lat"])[grid_order]
    natural47 = [values[grid_order] for values in natural47]
    natural5 = [values[grid_order] for values in natural5]
    dominant47 = [values[grid_order] for values in dominant47]
    dominant5 = [values[grid_order] for values in dominant5]

    summary_lines = [
        f"gridcells={grid_count}",
        f"soil_pft_rows={len(pft)}",
        f"initial_fpc_max_abs_cross_version_error_pct_point={max_abs(initial_fpc_error):.15g}",
        f"initial_nind_max_abs_cross_version_error={max_abs(initial_nind_error):.15g}",
    ]
    for state_index, label in enumerate(("initial", "year1_end", "year2_end")):
        summary_lines.extend(
            [
                f"{label}_regcm47_natural_grid_mean_fpc_pct={float(np.mean(natural47[state_index])):.15g}",
                f"{label}_regcm5_natural_grid_mean_fpc_pct={float(np.mean(natural5[state_index])):.15g}",
                f"{label}_natural_grid_paired_rmse_pct_point={rmse(natural5[state_index] - natural47[state_index]):.15g}",
                f"{label}_natural_grid_paired_correlation={correlation(natural47[state_index], natural5[state_index]):.15g}",
                f"{label}_dominant_natural_pft_agreement_gridcells={int(np.count_nonzero(dominant47[state_index] == dominant5[state_index]))}",
            ]
        )

    for year_index, label in enumerate(("year1_update", "year2_update")):
        left = delta47[year_index][natural]
        right = delta5[year_index][natural]
        difference = right - left
        material = (np.abs(left) >= 0.01) | (np.abs(right) >= 0.01)
        sign_agree = sign_class(left[material]) == sign_class(right[material])
        summary_lines.extend(
            [
                f"{label}_natural_slot_paired_mae_pct_point={float(np.mean(np.abs(difference))):.15g}",
                f"{label}_natural_slot_paired_rmse_pct_point={rmse(difference):.15g}",
                f"{label}_natural_slot_paired_max_abs_difference_pct_point={max_abs(difference):.15g}",
                f"{label}_natural_slot_paired_correlation={correlation(left, right):.15g}",
                f"{label}_material_union_slots={int(np.count_nonzero(material))}",
                f"{label}_material_sign_agreement_slots={int(np.count_nonzero(sign_agree))}",
                f"{label}_material_sign_agreement_fraction={float(np.mean(sign_agree)) if sign_agree.size else float('nan'):.15g}",
            ]
        )

    histories: dict[tuple[str, int], dict] = {}
    for version, directory in (("regcm47", output47), ("regcm5", output5)):
        for year in (1991, 1992):
            history = read_history(directory / f"cndvab.clm.regcm.h0.{year}01.nc")
            expected = datetime(year, 1, 1)
            if parse_history_date(history) != expected:
                raise ValueError(f"{version} history {year} has wrong time")
            histories[(version, year)] = sorted_history(history)

    for year in (1991, 1992):
        left = histories[("regcm47", year)]
        right = histories[("regcm5", year)]
        if not np.allclose(left["lon"], right["lon"], rtol=0.0, atol=1.0e-10):
            raise ValueError(f"history longitude differs in {year}")
        if not np.allclose(left["lat"], right["lat"], rtol=0.0, atol=1.0e-10):
            raise ValueError(f"history latitude differs in {year}")
        if not np.allclose(left["lon"], reference_lon, rtol=0.0, atol=1.0e-10):
            raise ValueError(f"history longitude does not map to the HV grid in {year}")
        if not np.allclose(left["lat"], reference_lat, rtol=0.0, atol=1.0e-10):
            raise ValueError(f"history latitude does not map to the HV grid in {year}")
        summary_lines.extend(drought_metrics(left["drought"], right["drought"], f"history_{year}_pre_dv_drought"))
        summary_lines.extend(drought_metrics(left["drought20"], right["drought20"], f"history_{year}_pre_dv_drought20"))

    restarts: dict[tuple[str, int], dict] = {}
    for version, directory in (("regcm47", output47), ("regcm5", output5)):
        for year in (1991, 1992):
            restart = read_restart_drought(directory / f"cndvab.clm.regcm.r.{year}010100.nc")
            if restart["mcdate"] != year * 10000 + 101 or restart["mcsec"] != 0:
                raise ValueError(f"{version} restart {year} has wrong date/time")
            if max_abs(np.asarray(restart["drought"])) > 1.0e-12:
                raise ValueError(f"{version} restart {year} did not reset drought_days")
            restarts[(version, year)] = restart

    for year in (1991, 1992):
        left = restarts[("regcm47", year)]
        right = restarts[("regcm5", year)]
        if not np.allclose(left["lon"], right["lon"], rtol=0.0, atol=1.0e-10):
            raise ValueError(f"restart longitude differs in {year}")
        if not np.allclose(left["lat"], right["lat"], rtol=0.0, atol=1.0e-10):
            raise ValueError(f"restart latitude differs in {year}")
        if not np.allclose(left["lon"], reference_lon, rtol=0.0, atol=1.0e-10):
            raise ValueError(f"restart longitude does not map to the HV grid in {year}")
        if not np.allclose(left["lat"], reference_lat, rtol=0.0, atol=1.0e-10):
            raise ValueError(f"restart latitude does not map to the HV grid in {year}")
        summary_lines.extend(drought_metrics(np.asarray(left["drought20"]), np.asarray(right["drought20"]), f"restart_{year}_post_dv_drought20"))

    for version in ("regcm47", "regcm5"):
        for year in (1991, 1992):
            history = histories[(version, year)]
            restart = restarts[(version, year)]
            if not np.allclose(history["lon"], restart["lon"], rtol=0.0, atol=1.0e-10):
                raise ValueError(f"{version} history/restart longitude differs in {year}")
            if not np.allclose(history["lat"], restart["lat"], rtol=0.0, atol=1.0e-10):
                raise ValueError(f"{version} history/restart latitude differs in {year}")
            previous_drought20 = (
                -np.ones_like(np.asarray(restart["drought20"]))
                if year == 1991
                else np.asarray(restarts[(version, 1991)]["drought20"])
            )
            carried_state_error = np.asarray(history["drought20"]) - previous_drought20
            expected_drought20 = np.where(
                previous_drought20 < 0.0,
                np.asarray(history["drought"]),
                (19.0 * previous_drought20 + np.asarray(history["drought"])) / 20.0,
            )
            recurrence_error = np.asarray(restart["drought20"]) - expected_drought20
            carried_state_max = max_abs(carried_state_error)
            recurrence_max = max_abs(recurrence_error)
            summary_lines.extend(
                [
                    f"{version}_{year}_history_carries_previous_drought20_max_abs_error_days={carried_state_max:.15g}",
                    f"{version}_{year}_drought20_recurrence_max_abs_error_days={recurrence_max:.15g}",
                    f"{version}_{year}_drought20_recurrence_rmse_days={rmse(recurrence_error):.15g}",
                ]
            )
            if carried_state_max > HISTORY_TOLERANCE_DAYS:
                raise ValueError(f"{version} history does not carry the previous drought_days20 in {year}")
            if recurrence_max > HISTORY_TOLERANCE_DAYS:
                raise ValueError(f"{version} drought_days20 recurrence failed in {year}")

    by_type_path = analysis / "strict_pft_comparison_by_type.csv"
    with by_type_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "pft_id",
                "pft_name",
                "initial_common_mean_fpc_pct",
                "regcm47_year1_end_mean_fpc_pct",
                "regcm5_year1_end_mean_fpc_pct",
                "regcm47_year2_end_mean_fpc_pct",
                "regcm5_year2_end_mean_fpc_pct",
                "regcm47_year1_delta_pp",
                "regcm5_year1_delta_pp",
                "regcm47_year2_delta_pp",
                "regcm5_year2_delta_pp",
            ]
        )
        for pft_id in range(17):
            means47 = [state_mean(table, grid_count, (pft_id,)) for table in tables47]
            means5 = [state_mean(table, grid_count, (pft_id,)) for table in tables5]
            writer.writerow(
                [
                    pft_id,
                    PFT_NAMES[pft_id],
                    means47[0],
                    means47[1],
                    means5[1],
                    means47[2],
                    means5[2],
                    means47[1] - means47[0],
                    means5[1] - means5[0],
                    means47[2] - means47[1],
                    means5[2] - means5[1],
                ]
            )

    paired_path = analysis / "strict_paired_grid_summary.csv"
    final47 = restarts[("regcm47", 1992)]
    final5 = restarts[("regcm5", 1992)]
    with paired_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "grid_index",
                "longitude",
                "latitude",
                "initial_natural_fpc_pct",
                "regcm47_year1_natural_fpc_pct",
                "regcm5_year1_natural_fpc_pct",
                "regcm47_year2_natural_fpc_pct",
                "regcm5_year2_natural_fpc_pct",
                "regcm47_year2_drought_days20",
                "regcm5_year2_drought_days20",
            ]
        )
        for row in zip(
            range(grid_count),
            reference_lon,
            reference_lat,
            natural47[0],
            natural47[1],
            natural5[1],
            natural47[2],
            natural5[2],
            final47["drought20"],
            final5["drought20"],
        ):
            writer.writerow(row)

    summary_lines.extend(
        [
            "qa_common_initial_state=true",
            "qa_common_grid_and_mapping=true",
            "qa_each_version_fpc_closure=true",
            "qa_each_version_restart_drought_reset=true",
            "qa_each_version_drought_recurrence=true",
            "qa_data_valid=true",
            f"by_type_csv={by_type_path}",
            f"paired_grid_csv={paired_path}",
        ]
    )
    summary_path = analysis / "strict_comparison_summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    labels = ["Initial", "Year 1 end", "Year 2 end"]
    axes[0].plot(labels, [np.mean(item) for item in natural47], marker="o", label="RegCM4.7")
    axes[0].plot(labels, [np.mean(item) for item in natural5], marker="o", label="RegCM5")
    axes[0].set_ylabel("Grid-mean natural target FPC (%)")
    axes[0].set_title("Paired-grid natural cover")
    axes[0].grid(alpha=0.25)
    axes[0].legend()

    axes[1].scatter(delta47[1][natural], delta5[1][natural], s=4, alpha=0.25)
    bound = max(max_abs(delta47[1][natural]), max_abs(delta5[1][natural]), 1.0)
    axes[1].plot([-bound, bound], [-bound, bound], color="black", linewidth=1)
    axes[1].set_xlim(-bound, bound)
    axes[1].set_ylim(-bound, bound)
    axes[1].set_xlabel("RegCM4.7 second-year ΔFPC (pp)")
    axes[1].set_ylabel("RegCM5 second-year ΔFPC (pp)")
    axes[1].set_title("Matched natural-PFT slots")
    axes[1].grid(alpha=0.25)

    axes[2].scatter(final47["drought20"], final5["drought20"], s=8, alpha=0.35)
    drought_bound = max(float(np.max(final47["drought20"])), float(np.max(final5["drought20"])), 45.0)
    axes[2].plot([0, drought_bound], [0, drought_bound], color="black", linewidth=1)
    axes[2].axvline(45.0, color="tab:red", linestyle="--", linewidth=1)
    axes[2].axhline(45.0, color="tab:red", linestyle="--", linewidth=1)
    axes[2].set_xlabel("RegCM4.7 year-2 drought_days20 (days)")
    axes[2].set_ylabel("RegCM5 year-2 drought_days20 (days)")
    axes[2].set_title("Matched active-soil columns")
    axes[2].grid(alpha=0.25)

    fig.suptitle("Strict RegCM4.7 vs RegCM5 CNDV comparison on shared inputs")
    fig.tight_layout()
    figure_path = analysis / "strict_comparison.png"
    fig.savefig(figure_path, dpi=180, facecolor="white")
    plt.close(fig)

    print("\n".join(summary_lines))
    print(f"figure={figure_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
