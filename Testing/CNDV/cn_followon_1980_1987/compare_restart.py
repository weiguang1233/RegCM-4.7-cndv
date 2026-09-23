#!/usr/bin/env python3
"""Compare model-state restart variables exactly while ignoring file metadata."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file


# CLM stores the active history-file path in its restart.  Two otherwise
# identical experiments in different output directories necessarily differ in
# this character field; it is I/O metadata, not prognostic model state.
NON_STATE_VARIABLES = {"locfnh", "locfnhr"}


def classic_copy(path: Path, directory: Path) -> Path:
    try:
        with netcdf_file(path, "r", mmap=False):
            return path
    except TypeError:
        target = directory / f"{path.name}.classic.nc"
        subprocess.run(["nccopy", "-k", "64-bit-offset", str(path), str(target)], check=True)
        return target


def read(path: Path, directory: Path) -> tuple[dict, dict]:
    source = classic_copy(path, directory)
    with netcdf_file(source, "r", mmap=False) as dataset:
        dims = dict(dataset.dimensions)
        variables = {
            name: (tuple(var.dimensions), np.array(var.data, copy=True))
            for name, var in dataset.variables.items()
            if name not in NON_STATE_VARIABLES
        }
    return dims, variables


def equal(left: np.ndarray, right: np.ndarray) -> bool:
    if np.issubdtype(left.dtype, np.inexact):
        return np.array_equal(left, right, equal_nan=True)
    return np.array_equal(left, right)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: compare_restart.py LEFT.nc RIGHT.nc", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="cndv_restart_compare_") as temporary:
        directory = Path(temporary)
        left_dims, left_vars = read(Path(sys.argv[1]), directory)
        right_dims, right_vars = read(Path(sys.argv[2]), directory)
    if left_dims != right_dims or left_vars.keys() != right_vars.keys():
        print("restart schema differs", file=sys.stderr)
        return 1
    for name in left_vars:
        left_axes, left_values = left_vars[name]
        right_axes, right_values = right_vars[name]
        if left_axes != right_axes or not equal(left_values, right_values):
            delta = "n/a"
            if left_values.shape == right_values.shape and np.issubdtype(left_values.dtype, np.number):
                delta = str(float(np.nanmax(np.abs(left_values.astype(float) - right_values.astype(float)))))
            print(f"restart variable differs: {name}; max_abs={delta}", file=sys.stderr)
            return 1
    ignored = ",".join(sorted(NON_STATE_VARIABLES))
    print(f"RESTART_MODEL_STATE_EXACTLY_IDENTICAL ignored_io_metadata={ignored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
