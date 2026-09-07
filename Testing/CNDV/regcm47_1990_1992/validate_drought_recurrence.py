#!/usr/bin/env python3
"""Validate the annual CNDV drought-state recurrence across two restarts."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file


FILL_LIMIT = 1.0e19
# History fields are float32; near 365 days one ULP is about 3.1e-5 day.
HISTORY_TOLERANCE_DAYS = 5.0e-5


def array(ds, name: str) -> np.ndarray:
    return np.array(ds.variables[name].data, copy=True)


def scalar(ds, name: str) -> int:
    return int(np.asarray(ds.variables[name].data).reshape(()))


def finite(values: np.ndarray) -> np.ndarray:
    return np.isfinite(values) & (np.abs(values) < FILL_LIMIT)


def active_soil(ds) -> np.ndarray:
    landunit = np.asarray(array(ds, "cols1d_ityplun"), dtype=np.int64)
    column_type = np.asarray(array(ds, "cols1d_ityp"), dtype=np.int64)
    wtxy = np.asarray(array(ds, "cols1d_wtxy"), dtype=np.float64)
    wtlnd = np.asarray(array(ds, "cols1d_wtlnd"), dtype=np.float64)
    return (
        (landunit == 1)
        & (column_type == 1)
        & (wtxy > 0.0)
        & (wtlnd > 0.0)
        & finite(wtxy)
        & finite(wtlnd)
    )


def coordinate_index(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    column_lon: np.ndarray,
    column_lat: np.ndarray,
) -> np.ndarray:
    """Map active columns to history grid cells by rounded coordinates."""
    lookup = {
        (round(float(lon), 10), round(float(lat), 10)): index
        for index, (lon, lat) in enumerate(zip(grid_lon, grid_lat))
    }
    result = np.asarray(
        [
            lookup.get((round(float(lon), 10), round(float(lat), 10)), -1)
            for lon, lat in zip(column_lon, column_lat)
        ],
        dtype=np.int64,
    )
    if np.any(result < 0):
        raise ValueError("an active restart column cannot be matched to history lon/lat")
    if np.unique(result).size != result.size:
        raise ValueError("active soil columns do not map one-to-one to history grid cells")
    return result


def max_abs(values: np.ndarray) -> float:
    if values.size == 0:
        raise ValueError("cannot validate an empty array")
    return float(np.max(np.abs(values)))


def main() -> int:
    if len(sys.argv) != 5:
        print(
            "usage: validate_drought_recurrence.py YEAR1_RESTART "
            "YEAR2_PRE_DV_HISTORY YEAR2_RESTART OUTPUT_DIR",
            file=sys.stderr,
        )
        return 2

    year1_path, history_path, year2_path, output_dir = map(Path, sys.argv[1:])
    output_dir.mkdir(parents=True, exist_ok=True)

    with netcdf_file(year1_path, "r", mmap=False) as ds:
        year1_date = scalar(ds, "mcdate")
        year1_sec = scalar(ds, "mcsec")
        year1_mask = active_soil(ds)
        year1_d20_all = np.asarray(array(ds, "drought_days20"), dtype=np.float64)
        year1_lon_all = np.asarray(array(ds, "cols1d_lon"), dtype=np.float64)
        year1_lat_all = np.asarray(array(ds, "cols1d_lat"), dtype=np.float64)

    with netcdf_file(history_path, "r", mmap=False) as ds:
        history_lon = np.asarray(array(ds, "lon"), dtype=np.float64)
        history_lat = np.asarray(array(ds, "lat"), dtype=np.float64)
        history_drought = np.asarray(array(ds, "DROUGHT_DAYS"), dtype=np.float64)
        history_d20 = np.asarray(array(ds, "DROUGHT_DAYS20"), dtype=np.float64)
        history_time = np.asarray(array(ds, "time"), dtype=np.float64)
        if history_drought.ndim != 2 or history_drought.shape[0] != 1:
            raise ValueError("year-2 history must contain exactly one time record")
        if history_d20.shape != history_drought.shape or history_time.size != 1:
            raise ValueError("history drought arrays/time have incompatible shapes")
        if not np.isclose(history_time[0], 368904.0, rtol=0.0, atol=1.0e-9):
            raise ValueError(
                "year-2 pre-DV history is not the 1992-01-01 record: "
                f"time={history_time[0]} hours since 1949-12-01"
            )
        history_drought = history_drought[0]
        history_d20 = history_d20[0]

    with netcdf_file(year2_path, "r", mmap=False) as ds:
        year2_date = scalar(ds, "mcdate")
        year2_sec = scalar(ds, "mcsec")
        year2_mask = active_soil(ds)
        year2_drought_all = np.asarray(array(ds, "drought_days"), dtype=np.float64)
        year2_d20_all = np.asarray(array(ds, "drought_days20"), dtype=np.float64)
        year2_lon_all = np.asarray(array(ds, "cols1d_lon"), dtype=np.float64)
        year2_lat_all = np.asarray(array(ds, "cols1d_lat"), dtype=np.float64)

    if year1_date != 19910101 or year2_date != 19920101:
        raise ValueError(
            f"unexpected restart dates: year1={year1_date}, year2={year2_date}"
        )
    if year1_sec != 0 or year2_sec != 0:
        raise ValueError("annual restart seconds must both be zero")
    if year1_mask.shape != year2_mask.shape or not np.array_equal(
        year1_mask, year2_mask
    ):
        raise ValueError("active-soil column mask changed across the two restarts")
    if not np.allclose(year1_lon_all, year2_lon_all, rtol=0.0, atol=1.0e-10):
        raise ValueError("column longitudes changed across restarts")
    if not np.allclose(year1_lat_all, year2_lat_all, rtol=0.0, atol=1.0e-10):
        raise ValueError("column latitudes changed across restarts")

    mask = (
        year1_mask
        & finite(year1_d20_all)
        & finite(year2_drought_all)
        & finite(year2_d20_all)
    )
    if not np.any(mask):
        raise ValueError("no valid active-soil drought state")

    column_lon = year2_lon_all[mask]
    column_lat = year2_lat_all[mask]
    history_index = coordinate_index(
        history_lon, history_lat, column_lon, column_lat
    )
    old_d20 = year1_d20_all[mask]
    current_drought = history_drought[history_index]
    history_old_d20 = history_d20[history_index]
    final_drought = year2_drought_all[mask]
    final_d20 = year2_d20_all[mask]

    if not (
        np.all(finite(current_drought))
        and np.all(finite(history_old_d20))
        and np.all(finite(final_drought))
        and np.all(finite(final_d20))
    ):
        raise ValueError("history/restart comparison contains fill or non-finite values")

    expected = (19.0 * old_d20 + current_drought) / 20.0
    old_history_error = history_old_d20 - old_d20
    recurrence_error = final_d20 - expected
    reset_error = final_drought

    old_history_max = max_abs(old_history_error)
    recurrence_max = max_abs(recurrence_error)
    reset_max = max_abs(reset_error)
    old_history_ok = old_history_max <= HISTORY_TOLERANCE_DAYS
    recurrence_ok = recurrence_max <= HISTORY_TOLERANCE_DAYS
    reset_ok = reset_max <= 1.0e-12

    detail_path = output_dir / "drought_recurrence_by_column.csv"
    with detail_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "active_column_index",
                "longitude",
                "latitude",
                "year1_drought_days20",
                "year2_pre_dv_drought_days",
                "year2_pre_dv_drought_days20",
                "year2_expected_drought_days20",
                "year2_final_drought_days20",
                "recurrence_error_days",
                "year2_final_drought_days",
            ]
        )
        active_indices = np.flatnonzero(mask)
        for row in zip(
            active_indices,
            column_lon,
            column_lat,
            old_d20,
            current_drought,
            history_old_d20,
            expected,
            final_d20,
            recurrence_error,
            final_drought,
        ):
            writer.writerow(row)

    summary_lines = [
        f"year1_restart={year1_path}",
        f"year2_pre_dv_history={history_path}",
        f"year2_restart={year2_path}",
        f"year1_mcdate={year1_date}",
        f"year2_mcdate={year2_date}",
        f"year1_mcsec={year1_sec}",
        f"year2_mcsec={year2_sec}",
        f"history_time_hours={float(history_time[0]):.15g}",
        f"active_soil_columns={int(mask.sum())}",
        f"year1_drought_days20_min={float(np.min(old_d20)):.15g}",
        f"year1_drought_days20_mean={float(np.mean(old_d20)):.15g}",
        f"year1_drought_days20_max={float(np.max(old_d20)):.15g}",
        f"year2_pre_dv_drought_days_min={float(np.min(current_drought)):.15g}",
        f"year2_pre_dv_drought_days_mean={float(np.mean(current_drought)):.15g}",
        f"year2_pre_dv_drought_days_max={float(np.max(current_drought)):.15g}",
        f"year2_final_drought_days20_min={float(np.min(final_d20)):.15g}",
        f"year2_final_drought_days20_mean={float(np.mean(final_d20)):.15g}",
        f"year2_final_drought_days20_median={float(np.median(final_d20)):.15g}",
        f"year2_final_drought_days20_p95={float(np.percentile(final_d20, 95.0)):.15g}",
        f"year2_final_drought_days20_max={float(np.max(final_d20)):.15g}",
        f"year2_final_drought_days20_columns_gt_45={int(np.count_nonzero(final_d20 > 45.0))}",
        f"history_old_d20_vs_year1_restart_max_abs_error_days={old_history_max:.15g}",
        f"year2_d20_recurrence_max_abs_error_days={recurrence_max:.15g}",
        f"year2_d20_recurrence_rms_error_days={float(np.sqrt(np.mean(np.square(recurrence_error)))):.15g}",
        f"year2_final_drought_days_reset_max_abs_days={reset_max:.15g}",
        f"history_float_tolerance_days={HISTORY_TOLERANCE_DAYS:.15g}",
        f"qa_history_carries_year1_d20={str(old_history_ok).lower()}",
        f"qa_year2_d20_recurrence_ok={str(recurrence_ok).lower()}",
        f"qa_year2_drought_days_reset_ok={str(reset_ok).lower()}",
        f"detail_csv={detail_path}",
    ]
    summary_path = output_dir / "drought_recurrence_summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print("\n".join(summary_lines))

    if not old_history_ok:
        raise ValueError("year-2 pre-DV history does not carry the year-1 d20 state")
    if not recurrence_ok:
        raise ValueError("year-2 drought_days20 recurrence check failed")
    if not reset_ok:
        raise ValueError("year-2 drought_days was not reset after annual DV")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
