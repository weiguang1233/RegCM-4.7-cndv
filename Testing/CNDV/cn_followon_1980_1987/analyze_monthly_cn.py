#!/usr/bin/env python3
"""Aggregate daily vegetation and restart-checkpoint ecosystem C/N diagnostics."""

from __future__ import annotations

import csv
import json
import math
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import netcdf_file


VERSIONS = {"RegCM4.7": "regcm47", "RegCM5": "regcm5"}
GRID_FIELDS = (
    "TBOT", "QBOT", "WIND", "RAIN", "SNOW", "FSDS", "FLDS", "BTRAN",
    "SOILWATER_10CM", "FPG", "SMINN", "SMINN_TO_PLANT", "NDEP_TO_SMINN",
    "NFIX_TO_SMINN", "GROSS_NMIN", "DROUGHT_DAYS", "DROUGHT_DAYS20", "AGDD",
)
FLUX_FIELDS = (
    "FPSN", "GPP", "INIT_GPP", "MR", "GR", "AR", "NPP", "AGNPP", "BGNPP",
    "AVAILC", "PLANT_NDEMAND", "PLANT_NALLOC", "PLANT_CALLOC", "EXCESS_CFLUX",
    "DOWNREG", "NEE", "HR", "LITHR", "TOTFIRE",
)
STATE_FIELDS = (
    "ELAI", "TLAI", "BTRAN", "TOTVEGC", "TOTVEGN", "TOTPFTC", "TOTPFTN",
    "LEAFC", "LEAFC_STORAGE", "LEAFC_XFER", "FROOTC", "FROOTC_STORAGE",
    "FROOTC_XFER", "LIVESTEMC", "LIVESTEMC_STORAGE", "LIVESTEMC_XFER",
    "DEADSTEMC", "DEADSTEMC_STORAGE", "DEADSTEMC_XFER", "LIVECROOTC",
    "LIVECROOTC_STORAGE", "LIVECROOTC_XFER", "DEADCROOTC",
    "DEADCROOTC_STORAGE", "DEADCROOTC_XFER", "WOODC", "CPOOL", "XSMRPOOL",
    "DISPVEGC", "STORVEGC", "LEAFN", "LEAFN_STORAGE", "LEAFN_XFER", "FROOTN",
    "FROOTN_STORAGE", "FROOTN_XFER", "LIVESTEMN", "LIVESTEMN_STORAGE",
    "LIVESTEMN_XFER", "DEADSTEMN", "DEADSTEMN_STORAGE", "DEADSTEMN_XFER",
    "LIVECROOTN", "LIVECROOTN_STORAGE", "LIVECROOTN_XFER", "DEADCROOTN",
    "DEADCROOTN_STORAGE", "DEADCROOTN_XFER", "NPOOL", "RETRANSN", "DISPVEGN",
    "STORVEGN", "TOTLITC", "TOTSOMC", "TOTECOSYSC", "SOILC", "LITTERC",
    "TOTLITN", "TOTSOMN", "TOTECOSYSN", "ANNSUM_NPP", "TEMPSUM_POTENTIAL_GPP",
)
STATIC_FIELDS = (
    "pfts1d_wtgcell", "pfts1d_wtxy", "pfts1d_itypveg",
    "cols1d_wtgcell", "cols1d_wtxy", "area", "landfrac",
)
TIME_FIELDS = ("time", "time_bounds")
CARBON_FLUXES = ("GPP", "NPP", "AR", "HR", "NEE", "TOTFIRE")
RESTART_FIELDS = (
    "mcdate", "mcsec", "pfts1d_itypveg", "pfts1d_wtxy", "PFT_WTGCELL",
    "cols1d_wtxy", "leafc", "leafc_storage", "leafc_xfer", "frootc",
    "frootc_storage", "frootc_xfer", "livestemc", "livestemc_storage",
    "livestemc_xfer", "deadstemc", "deadstemc_storage", "deadstemc_xfer",
    "livecrootc", "livecrootc_storage", "livecrootc_xfer", "deadcrootc",
    "deadcrootc_storage", "deadcrootc_xfer", "cpool", "totvegc", "leafn",
    "leafn_storage", "leafn_xfer", "frootn", "frootn_storage", "frootn_xfer",
    "livestemn", "livestemn_storage", "livestemn_xfer", "deadstemn",
    "deadstemn_storage", "deadstemn_xfer", "livecrootn", "livecrootn_storage",
    "livecrootn_xfer", "deadcrootn", "deadcrootn_storage", "deadcrootn_xfer",
    "retransn", "npool", "totvegn", "annsum_npp", "cwdc", "totlitc",
    "totsomc", "prod10c", "prod100c", "sminn", "litr1n", "litr2n",
    "litr3n", "cwdn", "soil1n", "soil2n", "soil3n", "soil4n", "prod10n",
    "prod100n",
)
HV_FIELDS = (
    "mcdate", "mcsec", "pfts1d_itypveg", "pfts1d_wtxy", "FPCGRID", "NIND",
)


def text(value: object) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def available_variables(path: Path) -> set[str]:
    header = subprocess.run(
        ["ncdump", "-h", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    variables = header.split("variables:", 1)[1].split("// global attributes:", 1)[0]
    pattern = re.compile(
        r"^\s*(?:byte|char|short|int|int64|float|double|ubyte|ushort|uint|uint64|string)"
        r"\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(|;)", re.MULTILINE,
    )
    return set(pattern.findall(variables))


def read_subset(path: Path, requested: tuple[str, ...], temporary: Path) -> dict:
    available = available_variables(path)
    selected = [name for name in requested if name in available]
    source = path
    try:
        with netcdf_file(source, "r", mmap=False):
            pass
    except TypeError:
        source = temporary / f"{path.name}.classic.nc"
        subprocess.run(["nccopy", "-k", "64-bit-offset", str(path), str(source)], check=True)
    result: dict[str, object] = {"variables": {}, "dimensions": {}}
    with netcdf_file(source, "r", mmap=False) as dataset:
        result["dimensions"] = dict(dataset.dimensions)
        for name in selected:
            variable = dataset.variables[name]
            result["variables"][name] = {
                "dimensions": tuple(variable.dimensions),
                "data": np.array(variable.data, copy=True),
                "units": text(getattr(variable, "units", "")),
            }
    if source != path:
        source.unlink()
    return result


def parse_origin(units: str) -> datetime:
    prefix = "hours since "
    if not units.startswith(prefix):
        raise ValueError(f"unsupported time units: {units}")
    value = units[len(prefix):].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"unsupported time origin: {value}")


def finite(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return np.where(np.isfinite(values) & (np.abs(values) < 1.0e19), values, np.nan)


def weighted_mean(values: np.ndarray, weights: np.ndarray, selected: np.ndarray, grid_count: int) -> float:
    valid = selected & np.isfinite(values) & np.isfinite(weights)
    return float(np.sum(values[valid] * weights[valid]) / grid_count)


def aggregate(
    values: np.ndarray,
    dimensions: tuple[str, ...],
    dataset: dict,
    natural_only: bool,
    pft_weights: np.ndarray | None = None,
    pft_types: np.ndarray | None = None,
) -> float:
    values = finite(values)
    variables = dataset["variables"]
    grid_count = int(dataset["dimensions"]["gridcell"])
    if "pft" in dimensions:
        if values.ndim != 1 or dimensions.index("pft") != 0:
            raise ValueError(f"unexpected PFT shape {values.shape} {dimensions}")
        if pft_weights is None or pft_types is None:
            weight_name = "pfts1d_wtgcell" if "pfts1d_wtgcell" in variables else "pfts1d_wtxy"
            weights = finite(variables[weight_name]["data"])
            pft = np.asarray(variables["pfts1d_itypveg"]["data"], dtype=np.int64)
        else:
            weights = pft_weights
            pft = pft_types
        selected = (pft >= 1) & (pft <= (14 if natural_only else 16))
        return weighted_mean(values, weights, selected, grid_count)
    if "column" in dimensions:
        if values.ndim != 1 or dimensions.index("column") != 0:
            raise ValueError(f"unexpected column shape {values.shape} {dimensions}")
        weight_name = "cols1d_wtgcell" if "cols1d_wtgcell" in variables else "cols1d_wtxy"
        weights = finite(variables[weight_name]["data"])
        return weighted_mean(values, weights, np.ones(values.shape, dtype=bool), grid_count)
    if "gridcell" in dimensions:
        if values.ndim != 1 or dimensions.index("gridcell") != 0:
            raise ValueError(f"unexpected grid shape {values.shape} {dimensions}")
        return float(np.nanmean(values))
    return float(np.nanmean(values))


def aggregate_tape(
    files: list[Path],
    fields: tuple[str, ...],
    natural_only: bool,
    fixed_pft_weights: np.ndarray,
    pft_types: np.ndarray,
) -> tuple[dict, dict]:
    rows: dict[datetime, dict[str, float]] = {}
    durations: dict[datetime, float] = {}
    units: dict[str, str] = {}
    request = TIME_FIELDS + fields + STATIC_FIELDS
    with tempfile.TemporaryDirectory(prefix="cndv_cn_subset_") as name:
        temporary = Path(name)
        for path in files:
            dataset = read_subset(path, request, temporary)
            variables = dataset["variables"]
            if "pfts1d_itypveg" in variables:
                history_pft_types = np.asarray(variables["pfts1d_itypveg"]["data"], dtype=np.int64)
                if not np.array_equal(history_pft_types, pft_types):
                    raise ValueError(f"PFT ordering differs between history and initial restart: {path}")
            origin = parse_origin(variables["time"]["units"])
            times = np.asarray(variables["time"]["data"], dtype=np.float64).reshape(-1)
            bounds = np.asarray(variables["time_bounds"]["data"], dtype=np.float64)
            if bounds.shape[0] != times.size or bounds.shape[1] != 2:
                raise ValueError(f"unexpected time bounds in {path}")
            for index, hours in enumerate(times):
                stamp = origin + timedelta(hours=float(hours))
                if stamp in rows:
                    raise ValueError(f"duplicate time {stamp} in tape")
                row: dict[str, float] = {}
                for field in fields:
                    if field not in variables:
                        continue
                    variable = variables[field]
                    data = variable["data"]
                    dims = variable["dimensions"]
                    if "time" in dims:
                        axis = dims.index("time")
                        sample = np.take(data, index, axis=axis)
                        sample_dims = tuple(dim for position, dim in enumerate(dims) if position != axis)
                    else:
                        sample, sample_dims = data, dims
                    row[field] = aggregate(
                        sample,
                        sample_dims,
                        dataset,
                        natural_only,
                        pft_weights=fixed_pft_weights,
                        pft_types=pft_types,
                    )
                    units[field] = variable["units"]
                if "pfts1d_itypveg" in variables and (
                    "pfts1d_wtgcell" in variables or "pfts1d_wtxy" in variables
                ):
                    pft = pft_types
                    weights = fixed_pft_weights
                    row["FIXED_1980_NATURAL_PFT_WEIGHT_PCT"] = float(
                        np.nansum(weights[(pft >= 1) & (pft <= 14)])
                        / int(dataset["dimensions"]["gridcell"]) * 100.0
                    )
                    units["FIXED_1980_NATURAL_PFT_WEIGHT_PCT"] = "%"
                rows[stamp] = row
                durations[stamp] = float(bounds[index, 1] - bounds[index, 0]) * 3600.0
    return rows, {"units": units, "durations": durations}


def load_initial_pft_weights(output: Path) -> tuple[np.ndarray, np.ndarray]:
    files = sorted(output.glob("*.clm.regcm.r.1980010100.nc"))
    if len(files) != 1:
        raise ValueError(f"expected one 1980 initial restart in {output}, found {len(files)}")
    request = ("mcdate", "mcsec", "pfts1d_itypveg", "pfts1d_wtxy", "PFT_WTGCELL")
    with tempfile.TemporaryDirectory(prefix="cndv_cn_weights_") as name:
        temporary = Path(name)
        dataset = read_subset(files[0], request, temporary)
    variables = dataset["variables"]
    weight_name = "pfts1d_wtxy" if "pfts1d_wtxy" in variables else "PFT_WTGCELL"
    weights = finite(variables[weight_name]["data"])
    types = np.asarray(variables["pfts1d_itypveg"]["data"], dtype=np.int64)
    return weights, types


def load_version(output: Path) -> tuple[list[dict], dict[str, str]]:
    fixed_pft_weights, pft_types = load_initial_pft_weights(output)
    specifications = (
        ("h0", GRID_FIELDS, False),
        ("h1", FLUX_FIELDS, True),
        ("h2", STATE_FIELDS, True),
    )
    merged: dict[datetime, dict[str, float]] = defaultdict(dict)
    reference_times: set[datetime] | None = None
    durations: dict[datetime, float] = {}
    units: dict[str, str] = {}
    for tape, fields, natural_only in specifications:
        files = sorted(output.glob(f"*.clm.regcm.{tape}.*.nc"))
        if not files:
            raise FileNotFoundError(f"no {tape} files in {output}")
        rows, metadata = aggregate_tape(
            files,
            fields,
            natural_only,
            fixed_pft_weights,
            pft_types,
        )
        if reference_times is None:
            reference_times = set(rows)
        elif set(rows) != reference_times:
            raise ValueError(f"history times differ on {tape}")
        for stamp, values in rows.items():
            merged[stamp].update(values)
        units.update(metadata["units"])
        durations.update(metadata["durations"])
    result = []
    for stamp in sorted(merged):
        row = merged[stamp]
        row["datetime"] = stamp.isoformat(sep=" ")
        row["interval_seconds"] = durations[stamp]
        vegc, vegn = row.get("TOTVEGC", math.nan), row.get("TOTVEGN", math.nan)
        row["VEGETATION_CN_RATIO"] = vegc / vegn if vegn > 0.0 else math.nan
        ecosysc, ecosysn = row.get("TOTECOSYSC", math.nan), row.get("TOTECOSYSN", math.nan)
        row["ECOSYSTEM_CN_RATIO"] = ecosysc / ecosysn if ecosysn > 0.0 else math.nan
        result.append(row)
    return result, units


def restart_date(mcdate: int, mcsec: int) -> datetime:
    base = datetime.strptime(str(mcdate), "%Y%m%d")
    return base + timedelta(seconds=mcsec)


def load_restart_states(output: Path) -> list[dict]:
    files = sorted(output.glob("*.clm.regcm.r.*.nc"))
    if not files:
        raise FileNotFoundError(f"no CLM restart files in {output}")
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="cndv_cn_restart_") as name:
        temporary = Path(name)
        for path in files:
            dataset = read_subset(path, RESTART_FIELDS, temporary)
            variables = dataset["variables"]
            required = {
                "mcdate", "mcsec", "pfts1d_itypveg", "totvegc",
                "cols1d_wtxy", "cwdc", "totlitc", "totsomc", "sminn",
            }
            missing = sorted(required - variables.keys())
            if missing:
                raise ValueError(f"restart fields missing from {path}: {missing}")
            grid_count = int(dataset["dimensions"]["gridcell"])
            pft = np.asarray(variables["pfts1d_itypveg"]["data"], dtype=np.int64)
            pft_weight_name = "pfts1d_wtxy" if "pfts1d_wtxy" in variables else "PFT_WTGCELL"
            pft_weights = finite(variables[pft_weight_name]["data"])
            col_weights = finite(variables["cols1d_wtxy"]["data"])

            def pft_mean(field: str, natural: bool = True) -> float:
                values = finite(variables[field]["data"])
                selected = (pft >= 1) & (pft <= (14 if natural else 16))
                return weighted_mean(values, pft_weights, selected, grid_count)

            def pft_sum(fields: tuple[str, ...], natural: bool = True) -> float:
                return sum(pft_mean(field, natural=natural) for field in fields)

            def col_mean(field: str) -> float:
                values = finite(variables[field]["data"])
                return weighted_mean(values, col_weights, np.ones(values.shape, dtype=bool), grid_count)

            def col_sum(fields: tuple[str, ...]) -> float:
                return sum(col_mean(field) for field in fields)

            mcdate = int(np.asarray(variables["mcdate"]["data"]).reshape(-1)[0])
            mcsec = int(np.asarray(variables["mcsec"]["data"]).reshape(-1)[0])
            stamp = restart_date(mcdate, mcsec)
            vegetation_c = pft_mean("totvegc")
            vegetation_n_fields = (
                "leafn", "frootn", "livestemn", "deadstemn", "livecrootn",
                "deadcrootn", "leafn_storage", "frootn_storage",
                "livestemn_storage", "deadstemn_storage", "livecrootn_storage",
                "deadcrootn_storage", "leafn_xfer", "frootn_xfer",
                "livestemn_xfer", "deadstemn_xfer", "livecrootn_xfer",
                "deadcrootn_xfer", "npool", "retransn",
            )
            vegetation_n = pft_sum(vegetation_n_fields)
            all_vegetation_c = pft_mean("totvegc", natural=False)
            all_vegetation_n = pft_sum(vegetation_n_fields, natural=False)
            litter_c = col_sum(("cwdc", "totlitc"))
            soil_c = col_mean("totsomc")
            product_c = col_sum(("prod10c", "prod100c"))
            litter_n = col_sum(("cwdn", "litr1n", "litr2n", "litr3n"))
            soil_n = col_sum(("soil1n", "soil2n", "soil3n", "soil4n"))
            mineral_n = col_mean("sminn")
            product_n = col_sum(("prod10n", "prod100n"))
            ecosystem_c = all_vegetation_c + litter_c + soil_c + product_c
            ecosystem_organic_n = all_vegetation_n + litter_n + soil_n + product_n
            ecosystem_n = ecosystem_organic_n + mineral_n
            natural_fpc_pct = float(
                np.nansum(pft_weights[(pft >= 1) & (pft <= 14)]) / grid_count * 100.0
            )
            row: dict[str, object] = {
                "datetime": stamp.isoformat(sep=" "),
                "mcdate": mcdate,
                "mcsec": mcsec,
                "source_file": path.name,
                "NATURAL_VEGETATION_C": vegetation_c,
                "NATURAL_VEGETATION_N": vegetation_n,
                "NATURAL_VEGETATION_CN_RATIO": vegetation_c / vegetation_n if vegetation_n > 0 else math.nan,
                "NATURAL_FPC_PCT": natural_fpc_pct,
                "ALL_VEGETATION_C": all_vegetation_c,
                "ALL_VEGETATION_N": all_vegetation_n,
                "LITTER_C": litter_c,
                "SOIL_ORGANIC_C": soil_c,
                "WOOD_PRODUCT_C": product_c,
                "ECOSYSTEM_C": ecosystem_c,
                "LITTER_N": litter_n,
                "SOIL_ORGANIC_N": soil_n,
                "MINERAL_N": mineral_n,
                "WOOD_PRODUCT_N": product_n,
                "ECOSYSTEM_ORGANIC_N": ecosystem_organic_n,
                "ECOSYSTEM_N": ecosystem_n,
                "ECOSYSTEM_CN_RATIO": ecosystem_c / ecosystem_n if ecosystem_n > 0 else math.nan,
            }
            for field in (
                "leafc", "leafc_storage", "leafc_xfer", "frootc", "frootc_storage",
                "frootc_xfer", "livestemc", "deadstemc", "livecrootc", "deadcrootc",
                "cpool", "leafn", "leafn_storage", "leafn_xfer", "frootn",
                "frootn_storage", "frootn_xfer", "livestemn", "deadstemn",
                "livecrootn", "deadcrootn", "npool", "retransn", "annsum_npp",
            ):
                if field in variables:
                    row[field.upper()] = pft_mean(field)
            rows.append(row)
    rows.sort(key=lambda row: row["datetime"])
    if len({row["datetime"] for row in rows}) != len(rows):
        raise ValueError(f"duplicate restart timestamps in {output}")
    return rows


def load_hv_states(output: Path) -> list[dict]:
    files = sorted(output.glob("*.clm.regcm.hv.*.nc"))
    if len(files) != 7:
        raise ValueError(f"expected 7 annual CNDV history files in {output}, found {len(files)}")
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="cndv_cn_hv_") as name:
        temporary = Path(name)
        for path in files:
            dataset = read_subset(path, HV_FIELDS, temporary)
            variables = dataset["variables"]
            grid_count = int(dataset["dimensions"]["gridcell"])
            pft = np.asarray(variables["pfts1d_itypveg"]["data"], dtype=np.int64)
            natural = (pft >= 1) & (pft <= 14)
            weights = finite(variables["pfts1d_wtxy"]["data"])
            fpc = finite(np.asarray(variables["FPCGRID"]["data"]).reshape(-1))
            nind = finite(np.asarray(variables["NIND"]["data"]).reshape(-1))
            mcdate = int(np.asarray(variables["mcdate"]["data"]).reshape(-1)[0])
            mcsec = int(np.asarray(variables["mcsec"]["data"]).reshape(-1)[0])
            stamp = restart_date(mcdate, mcsec)
            valid_nind = natural & np.isfinite(weights) & np.isfinite(nind)
            rows.append(
                {
                    "datetime": stamp.isoformat(sep=" "),
                    "source_file": path.name,
                    "APPLIED_NATURAL_PFT_WEIGHT_PCT": float(np.nansum(weights[natural]) / grid_count * 100.0),
                    "CNDV_TARGET_NATURAL_FPC_PCT": float(np.nansum(fpc[natural]) / grid_count),
                    "APPLIED_FPC_WEIGHTED_NIND": float(np.nansum(weights[valid_nind] * nind[valid_nind]) / grid_count),
                }
            )
    rows.sort(key=lambda row: row["datetime"])
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = sorted({key for row in rows for key in row}, key=lambda x: (x not in ("version", "datetime", "year"), x))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def annual_summary(version: str, rows: list[dict]) -> list[dict]:
    groups: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        stamp = datetime.fromisoformat(row["datetime"])
        groups[stamp.year - 1 if stamp.month == 1 and stamp.day == 1 else stamp.year].append(row)
    result = []
    state_fields = (
        "TOTVEGC", "TOTVEGN", "VEGETATION_CN_RATIO",
        "LEAFC", "FROOTC", "WOODC", "STORVEGC", "STORVEGN", "CPOOL", "NPOOL",
        "FIXED_1980_NATURAL_PFT_WEIGHT_PCT",
    )
    for year in sorted(groups):
        samples = sorted(groups[year], key=lambda row: row["datetime"])
        if year < 1980 or year > 1986:
            continue
        final = samples[-1]
        item: dict[str, object] = {
            "version": version,
            "year": year,
            "records": len(samples),
            "state_datetime": final["datetime"],
            "pft_weight_basis": "fixed_1980_restart",
        }
        for field in state_fields:
            if field in final:
                item[field] = final[field]
        for field in CARBON_FLUXES:
            total = sum(
                float(row[field]) * float(row["interval_seconds"])
                for row in samples if field in row and math.isfinite(float(row[field]))
            )
            item[f"ANNUAL_{field}_gC_m2"] = total
        result.append(item)
    return result


def make_chart(
    rows_by_version: dict[str, list[dict]],
    restarts_by_version: dict[str, list[dict]],
    output: Path,
) -> None:
    metrics = (
        ("TOTVEGC", "Vegetation C (fixed 1980 PFT weights)", "gC m$^{-2}$"),
        ("TOTVEGN", "Vegetation N (fixed 1980 PFT weights)", "gN m$^{-2}$"),
        ("ECOSYSTEM_C", "Ecosystem C (restart checkpoints)", "gC m$^{-2}$"),
        ("ECOSYSTEM_ORGANIC_N", "Ecosystem organic N (restart checkpoints)", "gN m$^{-2}$"),
    )
    colors = {"RegCM4.7": "#1f77b4", "RegCM5": "#d62728"}
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    for axis, (field, title, unit) in zip(axes.flat, metrics):
        source = restarts_by_version if field.startswith("ECOSYSTEM_") else rows_by_version
        for version, rows in source.items():
            dates = [datetime.fromisoformat(row["datetime"]) for row in rows]
            values = [row.get(field, math.nan) for row in rows]
            axis.plot(dates, values, label=version, color=colors[version], linewidth=1.8)
        axis.set_title(title)
        axis.set_ylabel(unit)
        axis.grid(alpha=0.25)
    axes[0, 0].legend(frameon=False)
    fig.suptitle("CNDV carbon and nitrogen pools: continuous restart, 1980–1986")
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def make_checkpoint_component_chart(restarts_by_version: dict[str, list[dict]], output: Path) -> None:
    versions = ("RegCM4.7", "RegCM5")
    carbon = (
        ("ALL_VEGETATION_C", "vegetation"),
        ("LITTER_C", "litter + CWD"),
        ("SOIL_ORGANIC_C", "soil organic"),
        ("WOOD_PRODUCT_C", "wood product"),
    )
    nitrogen = (
        ("ALL_VEGETATION_N", "vegetation"),
        ("LITTER_N", "litter + CWD"),
        ("SOIL_ORGANIC_N", "soil organic"),
        ("WOOD_PRODUCT_N", "wood product"),
    )
    fig, axes = plt.subplots(4, 2, figsize=(14, 13), sharex="col", sharey="row")
    for column, version in enumerate(versions):
        rows = restarts_by_version[version]
        dates = [datetime.fromisoformat(row["datetime"]) for row in rows]
        for field, label in carbon:
            axes[0, column].plot(dates, [row[field] for row in rows], marker="o", label=label)
        for field, label in nitrogen:
            axes[1, column].plot(dates, [row[field] for row in rows], marker="o", label=label)
        axes[2, column].plot(dates, [row["MINERAL_N"] for row in rows], marker="o", color="#9467bd")
        axes[3, column].plot(
            dates, [row["NATURAL_VEGETATION_CN_RATIO"] for row in rows], marker="o", color="#2ca02c"
        )
        axes[0, column].set_title(version)
        for row_index in range(4):
            axes[row_index, column].grid(alpha=0.25)
    axes[0, 0].set_ylabel("C pool (gC m$^{-2}$)")
    axes[1, 0].set_ylabel("Organic N pool (gN m$^{-2}$)")
    axes[2, 0].set_ylabel("Mineral N (gN m$^{-2}$)")
    axes[3, 0].set_ylabel("Natural vegetation C:N")
    axes[0, 1].legend(frameon=False, fontsize=9)
    axes[1, 1].legend(frameon=False, fontsize=9)
    fig.suptitle("CNDV carbon and nitrogen components at restart checkpoints")
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def make_fpc_chart(
    restarts_by_version: dict[str, list[dict]],
    hv_by_version: dict[str, list[dict]],
    output: Path,
) -> None:
    colors = {"RegCM4.7": "#1f77b4", "RegCM5": "#d62728"}
    fig, axis = plt.subplots(figsize=(10, 5.5))
    for version in ("RegCM4.7", "RegCM5"):
        restart_rows = restarts_by_version[version]
        hv_rows = hv_by_version[version]
        axis.plot(
            [datetime.fromisoformat(row["datetime"]) for row in restart_rows],
            [row["NATURAL_FPC_PCT"] for row in restart_rows],
            color=colors[version], marker="o", linewidth=1.8, label=f"{version} applied PFT weight",
        )
        axis.plot(
            [datetime.fromisoformat(row["datetime"]) for row in hv_rows],
            [row["CNDV_TARGET_NATURAL_FPC_PCT"] for row in hv_rows],
            color=colors[version], marker="x", linestyle="--", linewidth=1.5, label=f"{version} CNDV target",
        )
    axis.set_ylabel("Natural vegetation cover (%)")
    axis.set_title("Applied PFT area and annual CNDV target")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: analyze_monthly_cn.py REGCM47_OUTPUT REGCM5_OUTPUT ANALYSIS_DIR", file=sys.stderr)
        return 2
    output47, output5, analysis = map(Path, sys.argv[1:])
    analysis.mkdir(parents=True, exist_ok=True)
    outputs = {"RegCM4.7": output47, "RegCM5": output5}
    rows_by_version: dict[str, list[dict]] = {}
    restarts_by_version: dict[str, list[dict]] = {}
    hv_by_version: dict[str, list[dict]] = {}
    units: dict[str, str] = {}
    for version, output in outputs.items():
        rows, version_units = load_version(output)
        rows_by_version[version] = rows
        restarts_by_version[version] = load_restart_states(output)
        hv_by_version[version] = load_hv_states(output)
        units.update(version_units)

    if [row["datetime"] for row in rows_by_version["RegCM4.7"]] != [row["datetime"] for row in rows_by_version["RegCM5"]]:
        raise ValueError("cross-version monthly timestamps differ")
    for version, rows in rows_by_version.items():
        if len(rows) != 2557:
            raise ValueError(f"{version}: expected 2557 daily records, found {len(rows)}")
        stamps = [datetime.fromisoformat(row["datetime"]) for row in rows]
        expected_stamps = [datetime(1980, 1, 2) + timedelta(days=index) for index in range(2557)]
        if stamps != expected_stamps or stamps[-1] != datetime(1987, 1, 1):
            raise ValueError(f"{version}: daily timeline is incomplete or non-contiguous")
        for field in ("TOTVEGC", "TOTVEGN"):
            values = np.asarray([row.get(field, math.nan) for row in rows])
            if not np.all(np.isfinite(values)) or np.min(values) < -1.0e-8:
                raise ValueError(f"{version}: invalid {field}")
        restart_rows = restarts_by_version[version]
        if len(restart_rows) != 9:
            raise ValueError(f"{version}: expected 9 restart checkpoints, found {len(restart_rows)}")
        if restart_rows[0]["datetime"] != "1980-01-01 00:00:00" or restart_rows[-1]["datetime"] != "1987-01-01 00:00:00":
            raise ValueError(f"{version}: restart endpoints are incomplete")
        for field in ("NATURAL_VEGETATION_C", "NATURAL_VEGETATION_N", "ECOSYSTEM_C", "ECOSYSTEM_N"):
            values = np.asarray([row[field] for row in restart_rows], dtype=np.float64)
            if not np.all(np.isfinite(values)) or np.min(values) < -1.0e-8:
                raise ValueError(f"{version}: invalid restart {field}")
        hv_rows = hv_by_version[version]
        if len(hv_rows) != 7 or not all(math.isfinite(row["CNDV_TARGET_NATURAL_FPC_PCT"]) for row in hv_rows):
            raise ValueError(f"{version}: invalid annual CNDV FPC targets")

    monthly = [dict(version=version, **row) for version, rows in rows_by_version.items() for row in rows]
    annual = [item for version, rows in rows_by_version.items() for item in annual_summary(version, rows)]
    expected_annual_records = {1980: 366, 1981: 365, 1982: 365, 1983: 365, 1984: 366, 1985: 365, 1986: 365}
    for item in annual:
        if item["records"] != expected_annual_records[item["year"]]:
            raise ValueError(
                f"{item['version']} {item['year']}: expected "
                f"{expected_annual_records[item['year']]} records, found {item['records']}"
            )
    restart_rows = [dict(version=version, **row) for version, rows in restarts_by_version.items() for row in rows]
    hv_rows = [dict(version=version, **row) for version, rows in hv_by_version.items() for row in rows]
    write_csv(analysis / "daily_carbon_nitrogen_pools.csv", monthly)
    write_csv(analysis / "annual_carbon_nitrogen_summary.csv", annual)
    write_csv(analysis / "restart_carbon_nitrogen_checkpoints.csv", restart_rows)
    write_csv(analysis / "annual_cndv_fpc_targets.csv", hv_rows)
    make_chart(rows_by_version, restarts_by_version, analysis / "carbon_nitrogen_pools_1980_1986.png")
    make_checkpoint_component_chart(
        restarts_by_version, analysis / "carbon_nitrogen_components_checkpoints.png"
    )
    make_fpc_chart(restarts_by_version, hv_by_version, analysis / "cndv_fpc_actual_vs_target.png")

    summary: dict[str, object] = {
        "period": "1980-01-01 through 1987-01-01",
        "history_record_period": "1980-01-02 through 1987-01-01",
        "daily_records_per_version": 2557,
        "versions": {},
        "quality_control": {
            "daily_timestamps_contiguous": True,
            "restart_endpoints_complete": True,
            "annual_record_counts": expected_annual_records,
            "daily_pft_weight_basis": "fixed weights from the 1980-01-01 restart; actual dynamic regional pools use restart checkpoints",
        },
    }
    for version, rows in rows_by_version.items():
        carbon = np.asarray([row["TOTVEGC"] for row in rows])
        nitrogen = np.asarray([row["TOTVEGN"] for row in rows])
        checkpoints = restarts_by_version[version]
        initial_checkpoint = checkpoints[0]
        final_checkpoint = checkpoints[-1]
        checkpoint_carbon = np.asarray([row["NATURAL_VEGETATION_C"] for row in checkpoints])
        checkpoint_nitrogen = np.asarray([row["NATURAL_VEGETATION_N"] for row in checkpoints])
        carbon_closure = np.asarray(
            [row["NPP"] - (row["GPP"] - row["AR"]) for row in rows], dtype=np.float64
        )
        max_carbon_closure = float(np.nanmax(np.abs(carbon_closure)))
        if max_carbon_closure > 1.0e-8:
            raise ValueError(f"{version}: NPP != GPP - AR; max residual {max_carbon_closure}")
        summary["versions"][version] = {
            "initial_vegetation_c_gC_m2": float(initial_checkpoint["NATURAL_VEGETATION_C"]),
            "minimum_checkpoint_vegetation_c_gC_m2": float(np.min(checkpoint_carbon)),
            "minimum_checkpoint_vegetation_c_date": checkpoints[int(np.argmin(checkpoint_carbon))]["datetime"],
            "final_vegetation_c_gC_m2": float(final_checkpoint["NATURAL_VEGETATION_C"]),
            "vegetation_c_change_pct": float(
                (final_checkpoint["NATURAL_VEGETATION_C"] / initial_checkpoint["NATURAL_VEGETATION_C"] - 1.0) * 100.0
            ),
            "minimum_fixed_1980_weight_daily_vegetation_c_gC_m2": float(np.min(carbon)),
            "minimum_fixed_1980_weight_daily_vegetation_c_date": rows[int(np.argmin(carbon))]["datetime"],
            "initial_vegetation_n_gN_m2": float(initial_checkpoint["NATURAL_VEGETATION_N"]),
            "minimum_checkpoint_vegetation_n_gN_m2": float(np.min(checkpoint_nitrogen)),
            "minimum_checkpoint_vegetation_n_date": checkpoints[int(np.argmin(checkpoint_nitrogen))]["datetime"],
            "final_vegetation_n_gN_m2": float(final_checkpoint["NATURAL_VEGETATION_N"]),
            "vegetation_n_change_pct": float(
                (final_checkpoint["NATURAL_VEGETATION_N"] / initial_checkpoint["NATURAL_VEGETATION_N"] - 1.0) * 100.0
            ),
            "minimum_fixed_1980_weight_daily_vegetation_n_gN_m2": float(np.min(nitrogen)),
            "minimum_fixed_1980_weight_daily_vegetation_n_date": rows[int(np.argmin(nitrogen))]["datetime"],
            "final_vegetation_cn_ratio": float(final_checkpoint["NATURAL_VEGETATION_CN_RATIO"]),
            "restart_checkpoints": len(checkpoints),
            "initial_ecosystem_c_gC_m2": float(initial_checkpoint["ECOSYSTEM_C"]),
            "final_ecosystem_c_gC_m2": float(final_checkpoint["ECOSYSTEM_C"]),
            "initial_ecosystem_organic_n_gN_m2": float(initial_checkpoint["ECOSYSTEM_ORGANIC_N"]),
            "final_ecosystem_organic_n_gN_m2": float(final_checkpoint["ECOSYSTEM_ORGANIC_N"]),
            "initial_mineral_n_gN_m2": float(initial_checkpoint["MINERAL_N"]),
            "final_mineral_n_gN_m2": float(final_checkpoint["MINERAL_N"]),
            "final_ecosystem_n_gN_m2": float(final_checkpoint["ECOSYSTEM_N"]),
            "final_natural_fpc_pct": float(final_checkpoint["NATURAL_FPC_PCT"]),
            "final_cndv_target_natural_fpc_pct": float(hv_by_version[version][-1]["CNDV_TARGET_NATURAL_FPC_PCT"]),
            "max_abs_daily_npp_minus_gpp_plus_ar_gC_m2_s": max_carbon_closure,
        }
    left = rows_by_version["RegCM4.7"]
    right = rows_by_version["RegCM5"]
    first_divergence = None
    for lrow, rrow in zip(left, right):
        if abs(lrow["TOTVEGC"] - rrow["TOTVEGC"]) > 1.0e-10 or abs(lrow["TOTVEGN"] - rrow["TOTVEGN"]) > 1.0e-10:
            first_divergence = lrow["datetime"]
            break
    summary["cross_version"] = {
        "first_fixed_1980_weight_daily_carbon_or_nitrogen_divergence": first_divergence,
        "final_vegetation_c_ratio_regcm5_over_regcm47": float(
            restarts_by_version["RegCM5"][-1]["NATURAL_VEGETATION_C"]
            / restarts_by_version["RegCM4.7"][-1]["NATURAL_VEGETATION_C"]
        ),
        "final_vegetation_n_ratio_regcm5_over_regcm47": float(
            restarts_by_version["RegCM5"][-1]["NATURAL_VEGETATION_N"]
            / restarts_by_version["RegCM4.7"][-1]["NATURAL_VEGETATION_N"]
        ),
        "final_ecosystem_c_ratio_regcm5_over_regcm47": float(
            restarts_by_version["RegCM5"][-1]["ECOSYSTEM_C"]
            / restarts_by_version["RegCM4.7"][-1]["ECOSYSTEM_C"]
        ),
        "final_ecosystem_n_ratio_regcm5_over_regcm47": float(
            restarts_by_version["RegCM5"][-1]["ECOSYSTEM_N"]
            / restarts_by_version["RegCM4.7"][-1]["ECOSYSTEM_N"]
        ),
        "final_ecosystem_organic_n_ratio_regcm5_over_regcm47": float(
            restarts_by_version["RegCM5"][-1]["ECOSYSTEM_ORGANIC_N"]
            / restarts_by_version["RegCM4.7"][-1]["ECOSYSTEM_ORGANIC_N"]
        ),
    }
    (analysis / "carbon_nitrogen_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (analysis / "units.json").write_text(
        json.dumps(units, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    print("CNDV_CN_ANALYSIS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
