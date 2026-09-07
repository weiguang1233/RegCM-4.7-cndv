#!/usr/bin/env python3
"""Require RegCM4.7 and RegCM5 to start from the same soil-PFT state."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

from strict_compare_io import aligned_masks, closure_error, read_hv, soil_table


def max_abs(values: np.ndarray) -> float:
    return float(np.max(np.abs(values))) if values.size else 0.0


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: validate_initial_gate.py REGCM47_HV REGCM5_HV OUTPUT_DIR", file=sys.stderr)
        return 2
    path47, path5, output_dir = map(Path, sys.argv[1:])
    output_dir.mkdir(parents=True, exist_ok=True)
    state47 = read_hv(path47)
    state5 = read_hv(path5)
    table47 = soil_table(state47)
    table5 = soil_table(state5)
    mask47, mask5 = aligned_masks(state47["regcm_mask"], state5["regcm_mask"])

    coordinate_error = max(
        max_abs(np.asarray(state47["lon"]) - np.asarray(state5["lon"])),
        max_abs(np.asarray(state47["lat"]) - np.asarray(state5["lat"])),
    ) if len(np.asarray(state47["lon"])) == len(np.asarray(state5["lon"])) else float("inf")
    mapping_equal = bool(np.array_equal(table47["keys"], table5["keys"]))
    fpc_error = max_abs(table47["fpc"] - table5["fpc"]) if mapping_equal else float("inf")
    nind_error = max_abs(table47["nind"] - table5["nind"]) if mapping_equal else float("inf")
    closure47 = closure_error(state47, table47)
    closure5 = closure_error(state5, table5)
    mask_equal = bool(np.array_equal(mask47, mask5))
    dates_ok = bool(
        state47["mcdate"] == 19900101
        and state5["mcdate"] == 19900101
        and state47["mcsec"] == 0
        and state5["mcsec"] == 0
    )
    qa = {
        "dates": dates_ok,
        "numpft": state47["numpft"] == 17 and state5["numpft"] == 17,
        "grid_count": len(np.asarray(state47["lon"])) == len(np.asarray(state5["lon"])),
        "mask": mask_equal,
        "coordinates": coordinate_error <= 1.0e-10,
        "soil_mapping": mapping_equal,
        "initial_fpc": fpc_error <= 1.0e-12,
        "initial_nind": nind_error <= 1.0e-12,
        "closure": closure47 <= 1.0e-6 and closure5 <= 1.0e-6,
    }
    qa_all = all(qa.values())

    by_type = output_dir / "initial_state_difference_by_pft.csv"
    with by_type.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["pft_id", "max_abs_fpc_difference_pp", "max_abs_nind_difference"])
        if mapping_equal:
            for pft_id in range(17):
                selected = table47["pft"] == pft_id
                writer.writerow(
                    [
                        pft_id,
                        max_abs(table47["fpc"][selected] - table5["fpc"][selected]),
                        max_abs(table47["nind"][selected] - table5["nind"][selected]),
                    ]
                )

    lines = [
        f"regcm47_hv={path47}",
        f"regcm5_hv={path5}",
        f"regcm47_mcdate={state47['mcdate']}",
        f"regcm5_mcdate={state5['mcdate']}",
        f"regcm47_gridcells={len(np.asarray(state47['lon']))}",
        f"regcm5_gridcells={len(np.asarray(state5['lon']))}",
        f"regcm47_soil_pft_rows={len(table47['fpc'])}",
        f"regcm5_soil_pft_rows={len(table5['fpc'])}",
        f"regcm_mask_different_cells={int(np.count_nonzero(mask47 != mask5)) if mask47.shape == mask5.shape else -1}",
        f"coordinate_max_abs_error_degrees={coordinate_error:.15g}",
        f"initial_fpc_max_abs_error_pct_point={fpc_error:.15g}",
        f"initial_nind_max_abs_error={nind_error:.15g}",
        f"regcm47_closure_max_abs_error_pct_point={closure47:.15g}",
        f"regcm5_closure_max_abs_error_pct_point={closure5:.15g}",
    ]
    lines.extend(f"qa_{name}={str(value).lower()}" for name, value in qa.items())
    lines.append(f"qa_all={str(qa_all).lower()}")
    summary = output_dir / "initial_gate_summary.txt"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if not qa_all:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
