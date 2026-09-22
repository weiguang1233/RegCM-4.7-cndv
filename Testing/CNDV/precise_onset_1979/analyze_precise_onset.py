#!/usr/bin/env python3
"""Analyze the hourly and daily 1979 RegCM4.7/RegCM5 onset experiments."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file


GRID_COUNT = 1193
VERSIONS = {"RegCM4.7": "regcm47", "RegCM5": "regcm5"}

GRID_FIELDS = (
    "TBOT", "QBOT", "WIND", "RAIN", "SNOW", "FSDS", "FLDS", "BTRAN",
    "SOILWATER_10CM", "FPG", "SMINN", "SMINN_TO_PLANT",
    "NDEP_TO_SMINN", "NFIX_TO_SMINN", "GROSS_NMIN", "DROUGHT_DAYS",
    "DROUGHT_DAYS20", "AGDD",
)
FLUX_FIELDS = (
    "FPSN", "GPP", "INIT_GPP", "MR", "GR", "AR", "NPP", "AGNPP",
    "BGNPP", "AVAILC", "PLANT_NDEMAND", "PLANT_NALLOC", "PLANT_CALLOC",
    "EXCESS_CFLUX", "DOWNREG",
)
STATE_FIELDS = (
    "ELAI", "TLAI", "BTRAN", "TOTVEGC", "TOTVEGN", "LEAFC", "FROOTC",
    "WOODC", "CPOOL", "XSMRPOOL", "DISPVEGC", "STORVEGC", "DISPVEGN",
    "STORVEGN", "LEAFN", "FROOTN", "LIVESTEMN", "DEADSTEMN",
    "LIVECROOTN", "DEADCROOTN", "NPOOL", "RETRANSN", "ANNSUM_NPP",
    "TEMPSUM_POTENTIAL_GPP", "ANNSUM_POTENTIAL_GPP",
)

PFT_STATIC_FIELDS = ("pfts1d_wtgcell", "pfts1d_wtxy", "pfts1d_itypveg")
TIME_FIELDS = ("time", "time_bounds")


def text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def available_variables(path: Path) -> set[str]:
    header = subprocess.run(
        ["ncdump", "-h", str(path)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout
    variables = header.split("variables:", 1)[1].split("// global attributes:", 1)[0]
    pattern = re.compile(
        r"^\s*(?:byte|char|short|int|int64|float|double|ubyte|ushort|uint|uint64|string)"
        r"\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|;)", re.MULTILINE,
    )
    return set(pattern.findall(variables))


def read_subset(path: Path, requested: tuple[str, ...], temp_dir: Path) -> dict:
    available = available_variables(path)
    selected = [name for name in requested if name in available]
    if "time" in available and "time" not in selected:
        selected.insert(0, "time")
    if not selected:
        raise ValueError(f"no requested variables found in {path}")

    result: dict[str, object] = {"variables": {}, "dimensions": {}}
    # RegCM4.7 writes NetCDF-3 while RegCM5 can write NetCDF-4/HDF5.  SciPy
    # handles the former directly; for the latter, nccopy (from the NetCDF
    # module already used by the model) makes a temporary 64-bit-offset copy.
    source = path
    try:
        probe = netcdf_file(source, "r", mmap=False)
        probe.close()
    except TypeError:
        source = temp_dir / f"{path.name}.classic.nc"
        subprocess.run(
            ["nccopy", "-k", "64-bit-offset", str(path), str(source)],
            check=True,
        )
    with netcdf_file(source, "r", mmap=False) as dataset:
        result["dimensions"] = dict(dataset.dimensions)
        for name in selected:
            variable = dataset.variables[name]
            result["variables"][name] = {
                "dimensions": tuple(variable.dimensions),
                "data": np.array(variable.data, copy=True),
                "units": text(getattr(variable, "units", "")),
            }
    return result


def parse_times(dataset: dict) -> list[datetime]:
    variable = dataset["variables"]["time"]
    units = variable["units"]
    prefix = "hours since "
    if not units.startswith(prefix):
        raise ValueError(f"unsupported time units: {units}")
    origin_text = units[len(prefix):].strip()
    origin = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            origin = datetime.strptime(origin_text, fmt)
            break
        except ValueError:
            pass
    if origin is None:
        raise ValueError(f"unsupported time origin: {origin_text}")
    return [origin + timedelta(hours=float(value)) for value in variable["data"]]


def finite(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    return np.where(np.isfinite(result) & (np.abs(result) < 1.0e19), result, np.nan)


def aggregate_slice(values: np.ndarray, dimensions: tuple[str, ...], dataset: dict) -> float:
    values = finite(values)
    if "pft" in dimensions:
        axis = dimensions.index("pft")
        if values.ndim != 1 or axis != 0:
            raise ValueError(f"unexpected PFT field shape {values.shape} {dimensions}")
        variables = dataset["variables"]
        weight_name = "pfts1d_wtgcell" if "pfts1d_wtgcell" in variables else "pfts1d_wtxy"
        weights = finite(variables[weight_name]["data"])
        pft = np.asarray(dataset["variables"]["pfts1d_itypveg"]["data"], dtype=np.int64)
        selected = (pft >= 1) & (pft <= 14) & np.isfinite(values) & np.isfinite(weights)
        return float(np.sum(weights[selected] * values[selected]) / GRID_COUNT)
    if "gridcell" in dimensions:
        axis = dimensions.index("gridcell")
        if values.ndim != 1 or axis != 0:
            raise ValueError(f"unexpected grid field shape {values.shape} {dimensions}")
        return float(np.nanmean(values))
    if values.size == 1:
        return float(values.reshape(-1)[0])
    # A dov2xy history tape stores grid variables on the model x/y axes rather
    # than the internal gridcell axis.  Ocean/off-domain fill values have
    # already been converted to NaN by finite(), so this is the land mean.
    if values.ndim >= 1:
        return float(np.nanmean(values))
    raise ValueError(f"cannot aggregate dimensions {dimensions} shape {values.shape}")


def aggregate_tape(files: list[Path], fields: tuple[str, ...], pft_output: bool) -> tuple[dict, dict]:
    rows: dict[datetime, dict[str, float]] = {}
    units: dict[str, str] = {}
    requested = TIME_FIELDS + fields + (PFT_STATIC_FIELDS if pft_output else ())
    with tempfile.TemporaryDirectory(prefix="cndv79_subset_") as temporary:
        temp_dir = Path(temporary)
        for path in files:
            dataset = read_subset(path, requested, temp_dir)
            times = parse_times(dataset)
            variables = dataset["variables"]
            if pft_output:
                if "pfts1d_itypveg" not in variables:
                    raise ValueError(f"pfts1d_itypveg missing from {path}")
                weight_name = (
                    "pfts1d_wtgcell" if "pfts1d_wtgcell" in variables
                    else "pfts1d_wtxy" if "pfts1d_wtxy" in variables
                    else ""
                )
                if not weight_name:
                    raise ValueError(f"PFT gridcell weight missing from {path}")
                weights = finite(variables[weight_name]["data"])
                pft = np.asarray(variables["pfts1d_itypveg"]["data"], dtype=np.int64)
                natural = (pft >= 1) & (pft <= 14)
                natural_fpc = float(np.nansum(weights[natural]) / GRID_COUNT * 100.0)
            for index, stamp in enumerate(times):
                row = rows.setdefault(stamp, {})
                if pft_output:
                    row["NATURAL_FPC_PCT"] = natural_fpc
                    units["NATURAL_FPC_PCT"] = "%"
                for name in fields:
                    if name not in variables:
                        continue
                    variable = variables[name]
                    dimensions = variable["dimensions"]
                    data = variable["data"]
                    if "time" in dimensions:
                        time_axis = dimensions.index("time")
                        sample = np.take(data, index, axis=time_axis)
                        sample_dimensions = tuple(
                            dim for axis, dim in enumerate(dimensions) if axis != time_axis
                        )
                    else:
                        sample = data
                        sample_dimensions = dimensions
                    row[name] = aggregate_slice(sample, sample_dimensions, dataset)
                    units[name] = variable["units"]
    return rows, units


def load_phase(root: Path, version_dir: str, phase: str) -> tuple[list[dict], dict]:
    output = root / f"{version_dir}_{phase}" / "output"
    tape_specs = (
        ("h0", GRID_FIELDS, False),
        ("h1", FLUX_FIELDS, True),
        ("h2", STATE_FIELDS, True),
    )
    merged: dict[datetime, dict[str, float]] = {}
    units: dict[str, str] = {}
    for tape, fields, pft_output in tape_specs:
        files = sorted(output.glob(f"*.clm.regcm.{tape}.*.nc"))
        if not files:
            raise FileNotFoundError(f"no {tape} files in {output}")
        tape_rows, tape_units = aggregate_tape(files, fields, pft_output)
        for stamp, values in tape_rows.items():
            merged.setdefault(stamp, {}).update(values)
        units.update(tape_units)

    rows = []
    interval_seconds = 3600.0 if phase == "startup" else 86400.0
    cumulative = {
        "GPP": 0.0, "INIT_GPP": 0.0, "NPP": 0.0, "AR": 0.0,
        "MR": 0.0, "GR": 0.0, "EXCESS_CFLUX": 0.0,
    }
    cumulative_precip = 0.0
    for stamp in sorted(merged):
        values = dict(merged[stamp])
        for metric in cumulative:
            value = values.get(metric, float("nan"))
            if math.isfinite(value):
                cumulative[metric] += value * interval_seconds
            values[f"CUM_{metric}"] = cumulative[metric]
            units[f"CUM_{metric}"] = "gC/m^2"
        rain = values.get("RAIN", float("nan"))
        snow = values.get("SNOW", float("nan"))
        if math.isfinite(rain) and math.isfinite(snow):
            cumulative_precip += (rain + snow) * interval_seconds
        values["CUM_PRECIP"] = cumulative_precip
        units["CUM_PRECIP"] = "mm"
        if all(math.isfinite(values.get(name, float("nan"))) for name in ("GPP", "AR", "NPP")):
            values["NPP_BALANCE_ERROR"] = values["NPP"] - (values["GPP"] - values["AR"])
            units["NPP_BALANCE_ERROR"] = "gC/m^2/s"
        values["datetime"] = stamp.isoformat(sep=" ")
        rows.append(values)
    return rows, units


def write_wide(path: Path, version_rows: dict[str, list[dict]]) -> None:
    metrics = sorted({key for rows in version_rows.values() for row in rows for key in row if key != "datetime"})
    fields = ["version", "datetime"] + metrics
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for version, rows in version_rows.items():
            for row in rows:
                writer.writerow({"version": version, **row})


def compare_rows(left: list[dict], right: list[dict]) -> list[dict]:
    left_by_time = {row["datetime"]: row for row in left}
    right_by_time = {row["datetime"]: row for row in right}
    if left_by_time.keys() != right_by_time.keys():
        raise ValueError("cross-version history timestamps differ")
    result = []
    for stamp in left_by_time:
        lrow, rrow = left_by_time[stamp], right_by_time[stamp]
        for metric in sorted((set(lrow) & set(rrow)) - {"datetime"}):
            lv, rv = lrow[metric], rrow[metric]
            if not (isinstance(lv, (int, float)) and isinstance(rv, (int, float))):
                continue
            ratio = float("nan") if abs(lv) < 1.0e-20 else rv / lv * 100.0
            relative = abs(rv - lv) / max(abs(lv), 1.0e-20)
            result.append({
                "datetime": stamp,
                "metric": metric,
                "regcm47": lv,
                "regcm5": rv,
                "regcm5_minus_regcm47": rv - lv,
                "regcm5_over_regcm47_pct": ratio,
                "absolute_relative_difference": relative,
            })
    return result


def first_divergence(comparison: list[dict]) -> list[dict]:
    rules = {
        "CUM_INIT_GPP": (0.05, 0.10), "CUM_GPP": (0.05, 0.10),
        "CUM_NPP": (0.05, 0.10), "CUM_AR": (0.05, 0.10),
        "TOTVEGC": (0.01, 0.10), "TOTVEGN": (0.001, 0.10),
        "LEAFC": (0.01, 0.10), "FROOTC": (0.01, 0.10),
        "WOODC": (0.01, 0.10), "ELAI": (0.01, 0.10),
        "DOWNREG": (0.02, 0.10), "FPG": (0.02, 0.10),
        "BTRAN": (0.02, 0.10), "SMINN": (0.001, 0.10),
        "TBOT": (0.20, 0.0), "FSDS": (1.0, 0.0),
        "CUM_PRECIP": (1.0, 0.0),
    }
    by_metric: dict[str, list[dict]] = {}
    for row in comparison:
        by_metric.setdefault(row["metric"], []).append(row)
    result = []
    for metric, (absolute_threshold, relative_threshold) in rules.items():
        selected = None
        for row in by_metric.get(metric, []):
            lv = float(row["regcm47"])
            difference = abs(float(row["regcm5_minus_regcm47"]))
            relative = float(row["absolute_relative_difference"])
            enough_base = abs(lv) >= absolute_threshold
            if enough_base and difference >= absolute_threshold and relative >= relative_threshold:
                selected = row
                break
        result.append({
            "metric": metric,
            "absolute_threshold": absolute_threshold,
            "relative_threshold": relative_threshold,
            "first_divergence_datetime": "" if selected is None else selected["datetime"],
            "regcm47": "" if selected is None else selected["regcm47"],
            "regcm5": "" if selected is None else selected["regcm5"],
            "regcm5_minus_regcm47": "" if selected is None else selected["regcm5_minus_regcm47"],
            "regcm5_over_regcm47_pct": "" if selected is None else selected["regcm5_over_regcm47_pct"],
        })
    return result


def write_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def aggregate_restart(path: Path) -> dict[str, float]:
    nitrogen = (
        "leafn", "frootn", "livestemn", "deadstemn", "livecrootn", "deadcrootn",
        "leafn_storage", "frootn_storage", "livestemn_storage", "deadstemn_storage",
        "livecrootn_storage", "deadcrootn_storage", "leafn_xfer", "frootn_xfer",
        "livestemn_xfer", "deadstemn_xfer", "livecrootn_xfer", "deadcrootn_xfer",
        "npool", "retransn",
    )
    requested = (
        "pfts1d_wtxy", "pfts1d_itypveg", "totvegc", "leafc", "frootc",
        "livestemc", "deadstemc", "livecrootc", "deadcrootc", "cpool",
        "xsmrpool", "elai", "tlai", "annsum_npp", "fpcgrid", "nind", "present",
    ) + nitrogen
    with tempfile.TemporaryDirectory(prefix="cndv79_restart_") as temporary:
        dataset = read_subset(path, requested, Path(temporary))
    variables = dataset["variables"]
    weights = finite(variables["pfts1d_wtxy"]["data"])
    pft = np.asarray(variables["pfts1d_itypveg"]["data"], dtype=np.int64)
    natural = (pft >= 1) & (pft <= 14)

    def agg(name: str) -> float:
        values = finite(variables[name]["data"])
        selected = natural & np.isfinite(values) & np.isfinite(weights)
        return float(np.sum(weights[selected] * values[selected]) / GRID_COUNT)

    result = {
        "NATURAL_FPC_PCT": float(np.sum(finite(variables["fpcgrid"]["data"])[natural]) / GRID_COUNT * 100.0),
        "TOTVEGC": agg("totvegc"),
        "LEAFC": agg("leafc"),
        "FROOTC": agg("frootc"),
        "WOODC": sum(agg(name) for name in ("livestemc", "deadstemc", "livecrootc", "deadcrootc")),
        "CPOOL": agg("cpool"),
        "XSMRPOOL": agg("xsmrpool"),
        "ELAI": agg("elai"),
        "TLAI": agg("tlai"),
        "ANNSUM_NPP": agg("annsum_npp"),
        "WEIGHTED_NIND": agg("nind"),
    }
    result["TOTVEGN"] = sum(agg(name) for name in nitrogen)
    return result


def annual_before_after(root: Path, daily_rows: dict[str, list[dict]]) -> list[dict]:
    result = []
    for version, version_dir in VERSIONS.items():
        pre = daily_rows[version][-1]
        restart_files = sorted((root / f"{version_dir}_daily" / "output").glob("*.clm.regcm.r.*.nc"))
        if not restart_files:
            raise FileNotFoundError(f"no daily restart for {version}")
        post = aggregate_restart(restart_files[-1])
        for metric in (
            "NATURAL_FPC_PCT", "TOTVEGC", "TOTVEGN", "LEAFC", "FROOTC",
            "WOODC", "CPOOL", "XSMRPOOL", "ELAI", "TLAI", "ANNSUM_NPP",
        ):
            before = float(pre.get(metric, float("nan")))
            after = float(post.get(metric, float("nan")))
            result.append({
                "version": version,
                "metric": metric,
                "pre_dv_last_history": before,
                "post_dv_restart": after,
                "post_minus_pre": after - before,
                "post_over_pre_pct": float("nan") if abs(before) < 1.0e-20 else after / before * 100.0,
                "restart_file": restart_files[-1].name,
            })
    return result


def aggregate_hv(path: Path) -> tuple[dict[str, float], dict[int, dict[str, float]]]:
    requested = ("pfts1d_wtxy", "pfts1d_itypveg", "FPCGRID", "NIND")
    with tempfile.TemporaryDirectory(prefix="cndv79_hv_") as temporary:
        dataset = read_subset(path, requested, Path(temporary))
    variables = dataset["variables"]
    weights = finite(variables["pfts1d_wtxy"]["data"])
    pft = np.asarray(variables["pfts1d_itypveg"]["data"], dtype=np.int64)
    fpc = finite(variables["FPCGRID"]["data"])[-1]
    nind = finite(variables["NIND"]["data"])[-1]
    natural = (pft >= 1) & (pft <= 14)
    summary = {
        # HV FPCGRID is already written in percent, unlike the fractional
        # fpcgrid field in restart files.
        "NATURAL_FPC_PCT": float(np.nansum(fpc[natural]) / GRID_COUNT),
        "WEIGHTED_NIND": float(np.nansum(weights[natural] * nind[natural]) / GRID_COUNT),
        "FPC_WEIGHTED_NIND": float(
            np.nansum((fpc[natural] / 100.0) * nind[natural]) / GRID_COUNT
        ),
    }
    by_pft = {}
    for pft_type in range(1, 15):
        selected = pft == pft_type
        by_pft[pft_type] = {
            "FPC_PCT": float(np.nansum(fpc[selected]) / GRID_COUNT),
            "WEIGHTED_NIND": float(
                np.nansum(weights[selected] * nind[selected]) / GRID_COUNT
            ),
            "FPC_WEIGHTED_NIND": float(
                np.nansum((fpc[selected] / 100.0) * nind[selected]) / GRID_COUNT
            ),
        }
    return summary, by_pft


def annual_hv_change(root: Path) -> tuple[list[dict], list[dict]]:
    summary_rows = []
    pft_rows = []
    for version, version_dir in VERSIONS.items():
        files = sorted((root / f"{version_dir}_daily" / "output").glob("*.clm.regcm.hv.*.nc"))
        if len(files) != 2:
            raise ValueError(f"expected initial and post-DV HV files for {version}, got {files}")
        initial, initial_pft = aggregate_hv(files[0])
        final, final_pft = aggregate_hv(files[-1])
        for metric in initial:
            before = initial[metric]
            after = final[metric]
            summary_rows.append({
                "version": version,
                "metric": metric,
                "initial_hv": before,
                "post_dv_hv": after,
                "post_minus_initial": after - before,
                "post_over_initial_pct": (
                    float("nan") if abs(before) < 1.0e-20 else after / before * 100.0
                ),
                "initial_file": files[0].name,
                "post_dv_file": files[-1].name,
            })
        for pft_type in range(1, 15):
            for metric in initial_pft[pft_type]:
                before = initial_pft[pft_type][metric]
                after = final_pft[pft_type][metric]
                pft_rows.append({
                    "version": version,
                    "pft_type": pft_type,
                    "metric": metric,
                    "initial_hv": before,
                    "post_dv_hv": after,
                    "post_minus_initial": after - before,
                    "post_over_initial_pct": (
                        float("nan") if abs(before) < 1.0e-20 else after / before * 100.0
                    ),
                })
    return summary_rows, pft_rows


def analyze_phase(root: Path, phase: str) -> tuple[dict[str, list[dict]], dict]:
    analysis = root / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    version_rows: dict[str, list[dict]] = {}
    all_units: dict[str, str] = {}
    for version, version_dir in VERSIONS.items():
        rows, units = load_phase(root, version_dir, phase)
        version_rows[version] = rows
        all_units.update(units)

    expected = 24 if phase == "startup" else 365
    counts = {version: len(rows) for version, rows in version_rows.items()}
    if any(count != expected for count in counts.values()):
        raise ValueError(f"{phase} expected {expected} records per version, got {counts}")

    comparison = compare_rows(version_rows["RegCM4.7"], version_rows["RegCM5"])
    divergence = first_divergence(comparison)
    write_wide(analysis / f"{phase}_regional_timeseries.csv", version_rows)
    write_rows(analysis / f"{phase}_comparison_long.csv", comparison)
    write_rows(analysis / f"{phase}_first_divergence.csv", divergence)
    return version_rows, {"record_counts": counts, "units": all_units}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--phase", choices=("startup", "daily", "all"), default="all")
    args = parser.parse_args()
    root = args.root.resolve()
    validation: dict[str, object] = {
        "root": str(root),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phases": {},
    }

    startup_rows = None
    daily_rows = None
    if args.phase in ("startup", "all"):
        startup_rows, details = analyze_phase(root, "startup")
        validation["phases"]["startup"] = details
    if args.phase in ("daily", "all"):
        daily_rows, details = analyze_phase(root, "daily")
        validation["phases"]["daily"] = details
        before_after = annual_before_after(root, daily_rows)
        write_rows(root / "analysis" / "annual_update_before_after.csv", before_after)
        hv_summary, hv_by_pft = annual_hv_change(root)
        write_rows(root / "analysis" / "annual_cndv_hv_summary.csv", hv_summary)
        write_rows(root / "analysis" / "annual_cndv_hv_by_pft.csv", hv_by_pft)

    with (root / "analysis" / "validation_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(validation, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
