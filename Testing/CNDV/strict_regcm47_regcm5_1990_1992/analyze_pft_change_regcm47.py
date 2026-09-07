#!/usr/bin/env python3
"""Compare the initial and post-annual-update RegCM/CLM CNDV PFT files."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file


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
    17: "corn",
    18: "irrigated_corn",
    19: "spring_temperate_cereal",
    20: "irrigated_spring_temperate_cereal",
    21: "winter_temperate_cereal",
    22: "irrigated_winter_temperate_cereal",
    23: "soybean",
    24: "irrigated_soybean",
}


def read_nc_array(ds, name: str, *, single_time: bool = False) -> np.ndarray:
    """Copy a scipy NetCDF variable, optionally removing its sole time axis."""
    variable = ds.variables[name]
    data = np.array(variable.data, copy=True)
    if single_time:
        dimensions = [
            item.decode() if isinstance(item, bytes) else str(item)
            for item in variable.dimensions
        ]
        if dimensions.count("time") != 1:
            raise ValueError(f"{name} does not have exactly one time dimension")
        axis = dimensions.index("time")
        if data.shape[axis] != 1:
            raise ValueError(f"{name} has {data.shape[axis]} time records, expected one")
        data = np.take(data, 0, axis=axis)
    return data


def read_hv(path: Path) -> dict[str, np.ndarray | int]:
    with netcdf_file(path, "r", mmap=False) as ds:
        return {
            "fpc": np.asarray(
                read_nc_array(ds, "FPCGRID", single_time=True), dtype=np.float64
            ),
            "nind": np.asarray(
                read_nc_array(ds, "NIND", single_time=True), dtype=np.float64
            ),
            "pft": np.asarray(read_nc_array(ds, "pfts1d_itypveg"), dtype=np.int64),
            "landunit": np.asarray(
                read_nc_array(ds, "pfts1d_ityplun"), dtype=np.int64
            ),
            "gridcell": np.asarray(
                read_nc_array(ds, "pfts1d_gridcell"), dtype=np.int64
            ),
            "lat": np.asarray(read_nc_array(ds, "latixy"), dtype=np.float64),
            "lon": np.asarray(read_nc_array(ds, "longxy"), dtype=np.float64),
            "mcdate": int(read_nc_array(ds, "mcdate", single_time=True)),
            "mcsec": int(read_nc_array(ds, "mcsec", single_time=True)),
            "numpft": int(read_nc_array(ds, "numpft")),
        }


def grid_index(ids: np.ndarray, size: int) -> np.ndarray:
    if ids.min() >= 1 and ids.max() <= size:
        return ids - 1
    if ids.min() >= 0 and ids.max() < size:
        return ids
    raise ValueError("pfts1d_gridcell is neither zero- nor one-based")


def state_valid(values: np.ndarray) -> np.ndarray:
    """Exclude NaN/Inf and CLM's large inactive/fill sentinels."""
    return np.isfinite(values) & (np.abs(values) < 1.0e19)


def max_abs(values: np.ndarray) -> float:
    if values.size == 0:
        raise ValueError("cannot summarize an empty validation array")
    return float(np.max(np.abs(values)))


def rms(values: np.ndarray) -> float:
    if values.size == 0:
        raise ValueError("cannot summarize an empty validation array")
    return float(np.sqrt(np.mean(np.square(values))))


def main() -> int:
    if len(sys.argv) not in (4, 5, 6):
        print(
            "usage: analyze_pft_change.py INITIAL_HV FINAL_HV OUTPUT_DIR "
            "[FINAL_RESTART [INITIAL_RESTART]]",
            file=sys.stderr,
        )
        return 2

    initial_path, final_path, output_dir = map(Path, sys.argv[1:4])
    restart_path = Path(sys.argv[4]) if len(sys.argv) >= 5 else None
    initial_restart_path = Path(sys.argv[5]) if len(sys.argv) == 6 else None
    output_dir.mkdir(parents=True, exist_ok=True)
    initial = read_hv(initial_path)
    final = read_hv(final_path)

    for key in ("pft", "landunit", "gridcell", "numpft"):
        if not np.array_equal(initial[key], final[key]):
            raise ValueError(f"PFT mapping changed between files: {key}")
    for key in ("lat", "lon"):
        if not np.allclose(initial[key], final[key], rtol=0.0, atol=1.0e-10):
            raise ValueError(f"grid coordinates changed between files: {key}")

    pft = initial["pft"]
    landunit = initial["landunit"]
    fpc0 = initial["fpc"]
    fpc1 = final["fpc"]
    nind0 = initial["nind"]
    nind1 = final["nind"]
    valid = (
        state_valid(fpc0)
        & state_valid(fpc1)
        & state_valid(nind0)
        & state_valid(nind1)
    )
    soil = valid & (landunit == 1) & (pft >= 0) & (pft <= 16)
    natural = soil & (pft >= 1) & (pft <= 14)
    if initial["numpft"] != 17:
        raise ValueError(f"this test expects 17 PFT slots, found {initial['numpft']}")
    if initial["mcsec"] != 0 or final["mcsec"] != 0:
        raise ValueError("annual HV files must be written at 00:00:00")
    if not soil.any() or not natural.any():
        raise ValueError("no valid soil/natural PFT slots")
    dfpc = fpc1 - fpc0
    dnind = nind1 - nind0
    fpc_changed = natural & (np.abs(dfpc) > 1.0e-8)
    fpc_material = natural & (np.abs(dfpc) >= 1.0e-2)
    nind_changed = natural & (np.abs(dnind) > 1.0e-12)
    alive0 = natural & (fpc0 >= 1.0e-8) & (nind0 >= 1.0e-10)
    alive1 = natural & (fpc1 >= 1.0e-8) & (nind1 >= 1.0e-10)

    gidx = grid_index(initial["gridcell"], len(initial["lat"]))
    grid_count = len(initial["lat"])
    grid_sum0 = np.bincount(gidx[soil], weights=fpc0[soil], minlength=grid_count)
    grid_sum1 = np.bincount(gidx[soil], weights=fpc1[soil], minlength=grid_count)
    soil_grid = np.bincount(gidx[soil], minlength=grid_count) > 0
    closure_error0 = np.abs(grid_sum0[soil_grid] - 100.0)
    closure_error1 = np.abs(grid_sum1[soil_grid] - 100.0)
    closure_ok = bool(
        closure_error0.max() <= 1.0e-6 and closure_error1.max() <= 1.0e-6
    )
    if not closure_ok:
        raise ValueError(
            "soil-PFT FPC closure failed: "
            f"initial={closure_error0.max():.15g}, final={closure_error1.max():.15g}"
        )

    by_type_path = output_dir / "pft_change_by_type.csv"
    with by_type_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "pft_id",
                "pft_name",
                "slot_count",
                "initial_grid_mean_fpc_pct",
                "final_grid_mean_fpc_pct",
                "delta_grid_mean_fpc_pct_point",
                "initial_fpc_sum_pct",
                "final_fpc_sum_pct",
                "delta_fpc_sum_pct",
                "mean_delta_fpc_pct_point",
                "max_abs_delta_fpc_pct_point",
                "fpc_changed_slots",
                "fpc_material_changed_slots_ge_0.01_pct_point",
                "initial_nind_sum",
                "final_nind_sum",
                "delta_nind_sum",
                "max_abs_delta_nind",
                "nind_changed_slots",
                "fpc_gained_slots",
                "fpc_lost_slots",
                "dynamic_natural_pft",
            ]
        )
        for pft_id in range(0, 17):
            mask = soil & (pft == pft_id)
            dynamic_mask = natural & (pft == pft_id)
            gained = dynamic_mask & ~alive0 & alive1
            lost = dynamic_mask & alive0 & ~alive1
            writer.writerow(
                [
                    pft_id,
                    PFT_NAMES[pft_id],
                    int(mask.sum()),
                    float(fpc0[mask].sum() / grid_count),
                    float(fpc1[mask].sum() / grid_count),
                    float(dfpc[mask].sum() / grid_count),
                    float(fpc0[mask].sum()),
                    float(fpc1[mask].sum()),
                    float(dfpc[mask].sum()),
                    float(dfpc[mask].mean()) if mask.any() else 0.0,
                    float(np.abs(dfpc[mask]).max()) if mask.any() else 0.0,
                    int((fpc_changed & dynamic_mask).sum()),
                    int((fpc_material & dynamic_mask).sum()),
                    float(nind0[mask].sum()),
                    float(nind1[mask].sum()),
                    float(dnind[mask].sum()),
                    float(np.abs(dnind[mask]).max()) if mask.any() else 0.0,
                    int((nind_changed & dynamic_mask).sum()),
                    int(gained.sum()),
                    int(lost.sum()),
                    int(1 <= pft_id <= 14),
                ]
            )

    candidate = np.flatnonzero(natural)
    # Sort largest changes first and use the slot id as a deterministic tie-breaker.
    order = candidate[np.lexsort((candidate, -np.abs(dfpc[candidate])))]
    top_path = output_dir / "pft_top_changes.csv"
    with top_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "rank",
                "pft_slot",
                "pft_id",
                "pft_name",
                "gridcell_id",
                "latitude",
                "longitude",
                "initial_fpc_pct",
                "final_fpc_pct",
                "delta_fpc_pct_point",
                "initial_nind",
                "final_nind",
                "delta_nind",
            ]
        )
        for rank, slot in enumerate(order[:50], start=1):
            gi = gidx[slot]
            pft_id = int(pft[slot])
            writer.writerow(
                [
                    rank,
                    int(slot),
                    pft_id,
                    PFT_NAMES.get(pft_id, f"pft_{pft_id}"),
                    int(initial["gridcell"][slot]),
                    float(initial["lat"][gi]),
                    float(initial["lon"][gi]),
                    float(fpc0[slot]),
                    float(fpc1[slot]),
                    float(dfpc[slot]),
                    float(nind0[slot]),
                    float(nind1[slot]),
                    float(dnind[slot]),
                ]
            )

    dominant0 = np.zeros(grid_count, dtype=np.int64)
    dominant1 = np.zeros(grid_count, dtype=np.int64)
    dominant_fpc0 = np.zeros(grid_count, dtype=np.float64)
    dominant_fpc1 = np.zeros(grid_count, dtype=np.float64)
    for pft_id in range(1, 15):
        mask = natural & (pft == pft_id)
        ids = gidx[mask]
        vals0 = fpc0[mask]
        vals1 = fpc1[mask]
        update0 = vals0 > dominant_fpc0[ids]
        update1 = vals1 > dominant_fpc1[ids]
        dominant_fpc0[ids[update0]] = vals0[update0]
        dominant0[ids[update0]] = pft_id
        dominant_fpc1[ids[update1]] = vals1[update1]
        dominant1[ids[update1]] = pft_id

    transitions_path = output_dir / "dominant_pft_transitions.csv"
    with transitions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["initial_pft_id", "initial_pft_name", "final_pft_id", "final_pft_name", "gridcells"]
        )
        pairs, counts = np.unique(
            np.column_stack((dominant0, dominant1)), axis=0, return_counts=True
        )
        for pair, count in sorted(
            zip(pairs, counts), key=lambda item: int(item[1]), reverse=True
        ):
            old_id, new_id = map(int, pair)
            writer.writerow(
                [
                    old_id,
                    PFT_NAMES.get(old_id, f"pft_{old_id}"),
                    new_id,
                    PFT_NAMES.get(new_id, f"pft_{new_id}"),
                    int(count),
                ]
            )

    dominant_changed_gridcells = int(np.count_nonzero(dominant0 != dominant1))
    natural_initial_grid_mean = float(fpc0[natural].sum() / grid_count)
    natural_final_grid_mean = float(fpc1[natural].sum() / grid_count)
    natural_delta_grid_mean = natural_final_grid_mean - natural_initial_grid_mean
    bare_initial_grid_mean = float(fpc0[soil & (pft == 0)].sum() / grid_count)
    bare_final_grid_mean = float(fpc1[soil & (pft == 0)].sum() / grid_count)
    crop_initial_grid_mean = float(fpc0[soil & (pft == 15)].sum() / grid_count)
    crop_final_grid_mean = float(fpc1[soil & (pft == 15)].sum() / grid_count)

    restart_lines: list[str] = []
    if restart_path is not None:
        with netcdf_file(restart_path, "r", mmap=False) as restart:
            restart_fpc = np.asarray(
                restart.variables["fpcgrid"].data, dtype=np.float64
            ) * 100.0
            restart_old = np.asarray(
                restart.variables["fpcgridold"].data, dtype=np.float64
            ) * 100.0
            restart_nind = np.asarray(restart.variables["nind"].data, dtype=np.float64)
            present = np.asarray(restart.variables["present"].data, dtype=np.int64)
            drought = np.asarray(
                restart.variables["drought_days"].data, dtype=np.float64
            )
            drought20 = np.asarray(
                restart.variables["drought_days20"].data, dtype=np.float64
            )
            col_landunit = np.asarray(
                restart.variables["cols1d_ityplun"].data, dtype=np.int64
            )
            col_type = np.asarray(
                restart.variables["cols1d_ityp"].data, dtype=np.int64
            )
            col_wtxy = np.asarray(
                restart.variables["cols1d_wtxy"].data, dtype=np.float64
            )
            col_wtlnd = np.asarray(
                restart.variables["cols1d_wtlnd"].data, dtype=np.float64
            )
            restart_pft = np.asarray(
                restart.variables["pfts1d_itypveg"].data, dtype=np.int64
            )
            restart_landunit = np.asarray(
                restart.variables["pfts1d_ityplun"].data, dtype=np.int64
            )
            restart_lon = np.asarray(
                restart.variables["pfts1d_lon"].data, dtype=np.float64
            )
            restart_lat = np.asarray(
                restart.variables["pfts1d_lat"].data, dtype=np.float64
            )
            restart_mcdate = int(restart.variables["mcdate"].data)
            restart_mcsec = int(restart.variables["mcsec"].data)

        pft_shape = fpc0.shape
        for name, values in (
            ("fpcgrid", restart_fpc),
            ("fpcgridold", restart_old),
            ("nind", restart_nind),
            ("present", present),
        ):
            if values.shape != pft_shape:
                raise ValueError(
                    f"restart {name} shape {values.shape} differs from HV {pft_shape}"
                )

        if not np.array_equal(restart_pft, pft):
            raise ValueError("restart pfts1d_itypveg differs from HV")
        if not np.array_equal(restart_landunit, landunit):
            raise ValueError("restart pfts1d_ityplun differs from HV")
        if not np.allclose(restart_lon, initial["lon"][gidx], rtol=0.0, atol=1.0e-10):
            raise ValueError("restart PFT longitude mapping differs from HV")
        if not np.allclose(restart_lat, initial["lat"][gidx], rtol=0.0, atol=1.0e-10):
            raise ValueError("restart PFT latitude mapping differs from HV")
        if restart_mcdate != final["mcdate"] or restart_mcsec != final["mcsec"]:
            raise ValueError("final restart date/time differs from final HV")
        if not np.all(np.isin(present, (0, 1))):
            raise ValueError("restart present contains values other than 0 and 1")

        pft_state_valid = (
            state_valid(restart_fpc)
            & state_valid(restart_old)
            & state_valid(restart_nind)
            & state_valid(fpc0)
            & state_valid(fpc1)
            & state_valid(nind0)
            & state_valid(nind1)
        )
        restart_soil = soil & pft_state_valid
        restart_natural = natural & pft_state_valid
        if not restart_soil.any() or not restart_natural.any():
            raise ValueError("restart/HV comparison has no valid soil PFT slots")

        final_fpc_error = restart_fpc - fpc1
        final_nind_error = restart_nind - nind1
        annual_delta_error = (restart_fpc - restart_old) - dfpc

        if not (
            drought.shape
            == drought20.shape
            == col_landunit.shape
            == col_type.shape
            == col_wtxy.shape
            == col_wtlnd.shape
        ):
            raise ValueError("restart column metadata and drought arrays have different shapes")
        active_soil_column = (
            (col_landunit == 1)
            & (col_type == 1)
            & (col_wtxy > 0.0)
            & (col_wtlnd > 0.0)
            & state_valid(col_wtxy)
            & state_valid(col_wtlnd)
        )
        drought_valid = active_soil_column & state_valid(drought)
        drought20_valid = active_soil_column & state_valid(drought20)
        if not drought_valid.any() or not drought20_valid.any():
            raise ValueError("restart has no valid active-soil drought state")
        drought_values = drought[drought_valid]
        drought20_values = drought20[drought20_valid]

        initial_restart_lines: list[str] = []
        initial_restart_ok = True
        if initial_restart_path is not None:
            with netcdf_file(initial_restart_path, "r", mmap=False) as initial_restart:
                initial_restart_fpc = (
                    np.asarray(
                        initial_restart.variables["fpcgrid"].data, dtype=np.float64
                    )
                    * 100.0
                )
                initial_restart_nind = np.asarray(
                    initial_restart.variables["nind"].data, dtype=np.float64
                )
                initial_present = np.asarray(
                    initial_restart.variables["present"].data, dtype=np.int64
                )
                initial_restart_mcdate = int(initial_restart.variables["mcdate"].data)
                initial_restart_mcsec = int(initial_restart.variables["mcsec"].data)
            for name, values in (
                ("fpcgrid", initial_restart_fpc),
                ("nind", initial_restart_nind),
                ("present", initial_present),
            ):
                if values.shape != pft_shape:
                    raise ValueError(
                        f"initial restart {name} shape {values.shape} differs from HV {pft_shape}"
                    )
            initial_scope = (
                restart_natural
                & state_valid(initial_restart_fpc)
                & state_valid(initial_restart_nind)
            )
            if not initial_scope.any():
                raise ValueError("initial restart/HV comparison has no valid natural PFT slots")
            if (
                initial_restart_mcdate != initial["mcdate"]
                or initial_restart_mcsec != initial["mcsec"]
            ):
                raise ValueError("initial restart date/time differs from initial HV")
            if not np.all(np.isin(initial_present, (0, 1))):
                raise ValueError("initial restart present contains values other than 0 and 1")
            initial_fpc_error = initial_restart_fpc - fpc0
            initial_nind_error = initial_restart_nind - nind0
            exact_established = initial_scope & (initial_present == 0) & (present != 0)
            exact_lost = initial_scope & (initial_present != 0) & (present == 0)
            initial_restart_ok = bool(
                max_abs(initial_fpc_error[initial_scope]) <= 1.0e-10
                and max_abs(initial_nind_error[initial_scope]) <= 1.0e-12
            )
            initial_restart_lines = [
                f"initial_restart_file={initial_restart_path}",
                f"initial_restart_natural_max_abs_fpc_vs_initial_hv_pct_point={max_abs(initial_fpc_error[initial_scope]):.15g}",
                f"initial_restart_natural_max_abs_nind_vs_initial_hv={max_abs(initial_nind_error[initial_scope]):.15g}",
                f"initial_restart_present_natural_count={int(np.count_nonzero(initial_present[initial_scope]))}",
                f"restart_exact_established_natural_slots={int(np.count_nonzero(exact_established))}",
                f"restart_exact_lost_natural_slots={int(np.count_nonzero(exact_lost))}",
                f"qa_initial_restart_natural_crosscheck_ok={str(initial_restart_ok).lower()}",
            ]

        restart_crosscheck_ok = bool(
            max_abs(final_fpc_error[restart_soil]) <= 1.0e-10
            and max_abs(final_nind_error[restart_soil]) <= 1.0e-12
            and max_abs(annual_delta_error[restart_soil]) <= 1.0e-10
        )
        drought_reset_ok = bool(max_abs(drought_values) <= 1.0e-12)
        restart_lines = [
            f"restart_file={restart_path}",
            f"restart_soil_pft_slots={int(restart_soil.sum())}",
            f"restart_natural_pft_slots={int(restart_natural.sum())}",
            f"restart_soil_max_abs_fpc_vs_final_hv_pct_point={max_abs(final_fpc_error[restart_soil]):.15g}",
            f"restart_soil_rms_fpc_vs_final_hv_pct_point={rms(final_fpc_error[restart_soil]):.15g}",
            f"restart_soil_max_abs_nind_vs_final_hv={max_abs(final_nind_error[restart_soil]):.15g}",
            f"restart_soil_rms_nind_vs_final_hv={rms(final_nind_error[restart_soil]):.15g}",
            f"restart_soil_max_abs_annual_delta_vs_hv_delta_pct_point={max_abs(annual_delta_error[restart_soil]):.15g}",
            f"restart_soil_rms_annual_delta_vs_hv_delta_pct_point={rms(annual_delta_error[restart_soil]):.15g}",
            f"restart_natural_max_abs_annual_delta_vs_hv_delta_pct_point={max_abs(annual_delta_error[restart_natural]):.15g}",
            f"restart_natural_rms_annual_delta_vs_hv_delta_pct_point={rms(annual_delta_error[restart_natural]):.15g}",
            f"restart_present_natural_count={int(np.count_nonzero(present[restart_natural]))}",
            f"restart_active_soil_column_count={int(active_soil_column.sum())}",
            f"restart_valid_drought_days_count={int(drought_values.size)}",
            f"restart_drought_days_min={float(np.min(drought_values)):.15g}",
            f"restart_drought_days_mean={float(np.mean(drought_values)):.15g}",
            f"restart_drought_days_max={float(np.max(drought_values)):.15g}",
            f"restart_valid_drought_days20_count={int(drought20_values.size)}",
            f"restart_drought_days20_min={float(np.min(drought20_values)):.15g}",
            f"restart_drought_days20_mean={float(np.mean(drought20_values)):.15g}",
            f"restart_drought_days20_median={float(np.median(drought20_values)):.15g}",
            f"restart_drought_days20_p95={float(np.percentile(drought20_values, 95.0)):.15g}",
            f"restart_drought_days20_max={float(np.max(drought20_values)):.15g}",
            f"restart_drought_days20_columns_gt_45={int(np.count_nonzero(drought20_values > 45.0))}",
            f"qa_fpc_closure_ok={str(closure_ok).lower()}",
            f"qa_restart_soil_crosscheck_ok={str(restart_crosscheck_ok).lower()}",
            f"qa_drought_days_reset_ok={str(drought_reset_ok).lower()}",
        ] + initial_restart_lines

        if not restart_crosscheck_ok:
            raise ValueError("restart/HV FPC, NIND, or annual-delta cross-check failed")
        if not drought_reset_ok:
            raise ValueError("annual restart drought_days was not reset to zero")
        if not initial_restart_ok:
            raise ValueError("initial restart does not match the initial HV state")

    chart_path = output_dir / "pft_grid_mean_fpc_before_after.png"
    change_map_path = output_dir / "pft_total_abs_change_map.png"
    dominant_map_path = output_dir / "dominant_pft_before_after.png"
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        pft_ids = np.arange(17)
        initial_means = np.array(
            [fpc0[soil & (pft == i)].sum() / grid_count for i in pft_ids]
        )
        final_means = np.array(
            [fpc1[soil & (pft == i)].sum() / grid_count for i in pft_ids]
        )
        x = np.arange(len(pft_ids))
        width = 0.42
        fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
        axes[0].bar(
            x - width / 2,
            initial_means,
            width,
            label=f"mcdate {initial['mcdate']}",
            color="#4c78a8",
        )
        axes[0].bar(
            x + width / 2,
            final_means,
            width,
            label=f"mcdate {final['mcdate']}",
            color="#f58518",
        )
        axes[0].set_ylabel("Grid-mean target FPC (%)")
        axes[0].set_title("CNDV target PFT cover before and after the annual update")
        axes[0].grid(axis="y", alpha=0.25)
        axes[0].legend()
        colors = np.where(final_means - initial_means >= 0.0, "#4c78a8", "#f58518")
        axes[1].bar(x, final_means - initial_means, color=colors)
        axes[1].axhline(0.0, color="black", linewidth=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels([str(i) for i in pft_ids])
        axes[1].set_xlabel("CLM PFT id")
        axes[1].set_ylabel("Change (percentage point)")
        axes[1].grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(chart_path, dpi=180)
        plt.close(fig)

        grid_abs_change = np.bincount(
            gidx[natural], weights=np.abs(dfpc[natural]), minlength=grid_count
        )
        fig, ax = plt.subplots(figsize=(11, 6.5))
        points = ax.scatter(
            initial["lon"],
            initial["lat"],
            c=grid_abs_change,
            s=18,
            cmap="magma",
            linewidths=0,
        )
        fig.colorbar(points, ax=ax, label="Sum of absolute target FPC changes (pp)")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title(
            f"Spatial magnitude of target-cover change, "
            f"{initial['mcdate']} to {final['mcdate']}"
        )
        ax.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(change_map_path, dpi=180)
        plt.close(fig)

        fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharex=True, sharey=True)
        for ax, values, title in (
            (axes[0], dominant0, f"Dominant natural PFT, mcdate {initial['mcdate']}"),
            (axes[1], dominant1, f"Dominant natural PFT, mcdate {final['mcdate']}"),
        ):
            points = ax.scatter(
                initial["lon"],
                initial["lat"],
                c=values,
                s=18,
                cmap="tab20",
                vmin=0,
                vmax=16,
                linewidths=0,
            )
            ax.set_title(title)
            ax.set_xlabel("Longitude")
            ax.grid(alpha=0.2)
        axes[0].set_ylabel("Latitude")
        fig.colorbar(points, ax=axes, label="CLM PFT id", ticks=np.arange(0, 17, 2))
        fig.subplots_adjust(left=0.07, right=0.9, bottom=0.1, top=0.9, wspace=0.08)
        fig.savefig(dominant_map_path, dpi=180)
        plt.close(fig)
    except ImportError:
        chart_path = Path("matplotlib-not-installed")
        change_map_path = Path("matplotlib-not-installed")
        dominant_map_path = Path("matplotlib-not-installed")

    summary_lines = [
        f"initial_file={initial_path}",
        f"final_file={final_path}",
        f"initial_mcdate={initial['mcdate']}",
        f"final_mcdate={final['mcdate']}",
        f"initial_mcsec={initial['mcsec']}",
        f"final_mcsec={final['mcsec']}",
        f"numpft={initial['numpft']}",
        f"natural_pft_slots={int(natural.sum())}",
        f"soil_gridcells={int(soil_grid.sum())}",
        f"natural_initial_grid_mean_fpc_pct={natural_initial_grid_mean:.15g}",
        f"natural_final_grid_mean_fpc_pct={natural_final_grid_mean:.15g}",
        f"natural_delta_grid_mean_fpc_pct_point={natural_delta_grid_mean:.15g}",
        f"bare_initial_grid_mean_fpc_pct={bare_initial_grid_mean:.15g}",
        f"bare_final_grid_mean_fpc_pct={bare_final_grid_mean:.15g}",
        f"crop15_initial_grid_mean_fpc_pct={crop_initial_grid_mean:.15g}",
        f"crop15_final_grid_mean_fpc_pct={crop_final_grid_mean:.15g}",
        f"dominant_natural_pft_changed_gridcells={dominant_changed_gridcells}",
        f"fpc_changed_slots_gt_1e-8_pct_point={int(fpc_changed.sum())}",
        f"fpc_material_changed_slots_ge_0.01_pct_point={int(fpc_material.sum())}",
        f"nind_changed_slots_gt_1e-12={int(nind_changed.sum())}",
        f"pft_established_slots_proxy={int((~alive0 & alive1 & natural).sum())}",
        f"pft_lost_slots_proxy={int((alive0 & ~alive1 & natural).sum())}",
        f"total_abs_fpc_change_pct_point={float(np.abs(dfpc[natural]).sum()):.15g}",
        f"max_abs_fpc_change_pct_point={float(np.abs(dfpc[natural]).max()):.15g}",
        f"total_abs_nind_change={float(np.abs(dnind[natural]).sum()):.15g}",
        f"max_abs_nind_change={float(np.abs(dnind[natural]).max()):.15g}",
        f"initial_max_grid_fpc_closure_error_pct_point={float(closure_error0.max()):.15g}",
        f"final_max_grid_fpc_closure_error_pct_point={float(closure_error1.max()):.15g}",
        f"by_type_csv={by_type_path}",
        f"top_changes_csv={top_path}",
        f"dominant_transitions_csv={transitions_path}",
        f"chart={chart_path}",
        f"total_abs_change_map={change_map_path}",
        f"dominant_pft_map={dominant_map_path}",
    ] + restart_lines
    summary_path = output_dir / "pft_change_summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
