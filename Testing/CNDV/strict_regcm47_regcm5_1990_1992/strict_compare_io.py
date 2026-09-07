#!/usr/bin/env python3
"""Read the NetCDF-3 and NetCDF-4 files used by the strict CNDV comparison."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
from scipy.io import netcdf_file


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.size == 1:
        return _decode(value.reshape(-1)[0])
    return str(value)


def read_variables(path: Path, names: tuple[str, ...]) -> tuple[dict[str, np.ndarray], dict[str, dict[str, str]]]:
    """Return copied arrays and selected attributes from either supported container."""
    arrays: dict[str, np.ndarray] = {}
    attrs: dict[str, dict[str, str]] = {}
    if h5py.is_hdf5(path):
        with h5py.File(path, "r") as dataset:
            for name in names:
                variable = dataset[name]
                arrays[name] = np.asarray(variable[...]).copy()
                attrs[name] = {
                    key: _decode(variable.attrs[key])
                    for key in ("units", "_FillValue", "missing_value")
                    if key in variable.attrs
                }
    else:
        with netcdf_file(path, "r", mmap=False) as dataset:
            for name in names:
                variable = dataset.variables[name]
                arrays[name] = np.asarray(variable.data).copy()
                attrs[name] = {
                    key: _decode(getattr(variable, key))
                    for key in ("units", "_FillValue", "missing_value")
                    if hasattr(variable, key)
                }
    return arrays, attrs


def vector(array: np.ndarray, name: str) -> np.ndarray:
    result = np.asarray(array).squeeze()
    if result.ndim != 1:
        raise ValueError(f"{name} is not a vector after singleton removal: {result.shape}")
    return result


def scalar(array: np.ndarray, name: str) -> int:
    result = np.asarray(array).reshape(-1)
    if result.size != 1:
        raise ValueError(f"{name} is not scalar: {np.asarray(array).shape}")
    return int(result[0])


def read_hv(path: Path) -> dict[str, np.ndarray | int]:
    names = (
        "FPCGRID",
        "NIND",
        "pfts1d_itypveg",
        "pfts1d_ityplun",
        "pfts1d_gridcell",
        "longxy",
        "latixy",
        "regcm_mask",
        "mcdate",
        "mcsec",
        "numpft",
    )
    arrays, _ = read_variables(path, names)
    return {
        "path": path,
        "fpc": vector(arrays["FPCGRID"], "FPCGRID").astype(np.float64),
        "nind": vector(arrays["NIND"], "NIND").astype(np.float64),
        "pft": vector(arrays["pfts1d_itypveg"], "pfts1d_itypveg").astype(np.int64),
        "landunit": vector(arrays["pfts1d_ityplun"], "pfts1d_ityplun").astype(np.int64),
        "gridcell": vector(arrays["pfts1d_gridcell"], "pfts1d_gridcell").astype(np.int64),
        "lon": vector(arrays["longxy"], "longxy").astype(np.float64),
        "lat": vector(arrays["latixy"], "latixy").astype(np.float64),
        "regcm_mask": np.asarray(arrays["regcm_mask"]).squeeze().astype(np.int64),
        "mcdate": scalar(arrays["mcdate"], "mcdate"),
        "mcsec": scalar(arrays["mcsec"], "mcsec"),
        "numpft": scalar(arrays["numpft"], "numpft"),
    }


def grid_index(ids: np.ndarray, size: int) -> np.ndarray:
    if ids.min() >= 1 and ids.max() <= size:
        return ids - 1
    if ids.min() >= 0 and ids.max() < size:
        return ids
    raise ValueError("pfts1d_gridcell is neither zero- nor one-based")


def soil_table(state: dict[str, np.ndarray | int]) -> dict[str, np.ndarray]:
    pft = np.asarray(state["pft"])
    landunit = np.asarray(state["landunit"])
    fpc = np.asarray(state["fpc"])
    nind = np.asarray(state["nind"])
    valid = np.isfinite(fpc) & np.isfinite(nind) & (np.abs(fpc) < 1.0e19) & (np.abs(nind) < 1.0e19)
    selected = valid & (landunit == 1) & (pft >= 0) & (pft <= 16)
    gridcell = np.asarray(state["gridcell"])[selected]
    pft_selected = pft[selected]
    order = np.lexsort((pft_selected, gridcell))
    gridcell = gridcell[order]
    pft_selected = pft_selected[order]
    keys = np.column_stack((gridcell, pft_selected))
    if np.unique(keys, axis=0).shape[0] != keys.shape[0]:
        raise ValueError("soil PFT key is not unique")
    expected = len(np.asarray(state["lon"])) * 17
    if keys.shape[0] != expected:
        raise ValueError(f"expected {expected} soil PFT rows, found {keys.shape[0]}")
    return {
        "keys": keys,
        "gridcell": gridcell,
        "pft": pft_selected,
        "fpc": fpc[selected][order],
        "nind": nind[selected][order],
    }


def aligned_masks(left: np.ndarray, right: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    left = np.asarray(left).squeeze()
    right = np.asarray(right).squeeze()
    if left.shape == right.shape:
        return left, right
    if left.T.shape == right.shape:
        return left.T, right
    if left.shape == right.T.shape:
        return left, right.T
    raise ValueError(f"regcm_mask shapes cannot be aligned: {left.shape}, {right.shape}")


def closure_error(state: dict[str, np.ndarray | int], table: dict[str, np.ndarray]) -> float:
    count = len(np.asarray(state["lon"]))
    index = grid_index(table["gridcell"], count)
    total = np.bincount(index, weights=table["fpc"], minlength=count)
    return float(np.max(np.abs(total - 100.0)))


def read_history(path: Path) -> dict[str, np.ndarray | str]:
    names = ("lon", "lat", "DROUGHT_DAYS", "DROUGHT_DAYS20", "time", "regcm_mask")
    arrays, attrs = read_variables(path, names)
    return {
        "path": path,
        "lon": vector(arrays["lon"], "lon").astype(np.float64),
        "lat": vector(arrays["lat"], "lat").astype(np.float64),
        "drought": vector(arrays["DROUGHT_DAYS"], "DROUGHT_DAYS").astype(np.float64),
        "drought20": vector(arrays["DROUGHT_DAYS20"], "DROUGHT_DAYS20").astype(np.float64),
        "time": float(np.asarray(arrays["time"]).reshape(-1)[0]),
        "time_units": attrs["time"].get("units", ""),
        "regcm_mask": np.asarray(arrays["regcm_mask"]).squeeze().astype(np.int64),
    }


def read_restart_drought(path: Path) -> dict[str, np.ndarray | int]:
    names = (
        "drought_days",
        "drought_days20",
        "cols1d_ityplun",
        "cols1d_ityp",
        "cols1d_wtxy",
        "cols1d_wtlnd",
        "cols1d_lon",
        "cols1d_lat",
        "mcdate",
        "mcsec",
    )
    arrays, _ = read_variables(path, names)
    drought = vector(arrays["drought_days"], "drought_days").astype(np.float64)
    drought20 = vector(arrays["drought_days20"], "drought_days20").astype(np.float64)
    landunit = vector(arrays["cols1d_ityplun"], "cols1d_ityplun").astype(np.int64)
    column_type = vector(arrays["cols1d_ityp"], "cols1d_ityp").astype(np.int64)
    wtxy = vector(arrays["cols1d_wtxy"], "cols1d_wtxy").astype(np.float64)
    wtlnd = vector(arrays["cols1d_wtlnd"], "cols1d_wtlnd").astype(np.float64)
    lon = vector(arrays["cols1d_lon"], "cols1d_lon").astype(np.float64)
    lat = vector(arrays["cols1d_lat"], "cols1d_lat").astype(np.float64)
    shape = drought.shape
    for name, values in (
        ("drought_days20", drought20),
        ("cols1d_ityplun", landunit),
        ("cols1d_ityp", column_type),
        ("cols1d_wtxy", wtxy),
        ("cols1d_wtlnd", wtlnd),
        ("cols1d_lon", lon),
        ("cols1d_lat", lat),
    ):
        if values.shape != shape:
            raise ValueError(f"restart {name} shape differs from drought_days")
    finite = lambda values: np.isfinite(values) & (np.abs(values) < 1.0e19)
    selected = (
        (landunit == 1)
        & (column_type == 1)
        & (wtxy > 0.0)
        & (wtlnd > 0.0)
        & finite(wtxy)
        & finite(wtlnd)
        & finite(lon)
        & finite(lat)
        & finite(drought)
        & finite(drought20)
    )
    order = np.lexsort((lon[selected], lat[selected]))
    return {
        "path": path,
        "lon": lon[selected][order],
        "lat": lat[selected][order],
        "drought": drought[selected][order],
        "drought20": drought20[selected][order],
        "mcdate": scalar(arrays["mcdate"], "mcdate"),
        "mcsec": scalar(arrays["mcsec"], "mcsec"),
    }
