#!/usr/bin/env python3
"""Compare CNDV target PFT states at initialization and two year ends."""

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


def valid(values: np.ndarray) -> np.ndarray:
    return np.isfinite(values) & (np.abs(values) < 1.0e19)


def grid_index(ids: np.ndarray, size: int) -> np.ndarray:
    if ids.min() >= 1 and ids.max() <= size:
        return ids - 1
    if ids.min() >= 0 and ids.max() < size:
        return ids
    raise ValueError("pfts1d_gridcell has an unsupported index base")


def dominant_pft(
    fpc: np.ndarray,
    pft: np.ndarray,
    natural: np.ndarray,
    gidx: np.ndarray,
    grid_count: int,
) -> np.ndarray:
    result = np.zeros(grid_count, dtype=np.int64)
    best = np.zeros(grid_count, dtype=np.float64)
    for pft_id in range(1, 15):
        mask = natural & (pft == pft_id)
        ids = gidx[mask]
        values = fpc[mask]
        update = values > best[ids]
        best[ids[update]] = values[update]
        result[ids[update]] = pft_id
    return result


def main() -> int:
    if len(sys.argv) != 5:
        print(
            "usage: analyze_three_year_states.py INITIAL_HV YEAR1_HV YEAR2_HV OUTPUT_DIR",
            file=sys.stderr,
        )
        return 2

    paths = [Path(value) for value in sys.argv[1:4]]
    output_dir = Path(sys.argv[4])
    output_dir.mkdir(parents=True, exist_ok=True)
    states = [read_hv(path) for path in paths]

    for key in ("pft", "landunit", "gridcell", "numpft"):
        if not all(np.array_equal(states[0][key], state[key]) for state in states[1:]):
            raise ValueError(f"PFT mapping changed between annual files: {key}")
    for key in ("lat", "lon"):
        if not all(np.allclose(states[0][key], state[key], rtol=0.0, atol=1.0e-10) for state in states[1:]):
            raise ValueError(f"grid coordinates changed between annual files: {key}")

    pft = states[0]["pft"]
    landunit = states[0]["landunit"]
    fpc = [state["fpc"] for state in states]
    nind = [state["nind"] for state in states]
    state_valid = np.logical_and.reduce([valid(values) for values in fpc + nind])
    soil = state_valid & (landunit == 1) & (pft >= 0) & (pft <= 16)
    natural = soil & (pft >= 1) & (pft <= 14)
    if states[0]["numpft"] != 17:
        raise ValueError(f"this test expects 17 PFT slots, found {states[0]['numpft']}")
    if any(state["mcsec"] != 0 for state in states):
        raise ValueError("annual HV files must be written at 00:00:00")
    if not natural.any():
        raise ValueError("no valid natural-soil PFT slots")

    grid_count = len(states[0]["lat"])
    gidx = grid_index(states[0]["gridcell"], grid_count)
    soil_grid = np.bincount(gidx[soil], minlength=grid_count) > 0
    closure = []
    for values in fpc:
        total = np.bincount(gidx[soil], weights=values[soil], minlength=grid_count)
        closure.append(float(np.max(np.abs(total[soil_grid] - 100.0))))
    if any(value > 1.0e-6 for value in closure):
        raise ValueError(f"soil-PFT FPC closure failed: {closure}")

    delta1 = fpc[1] - fpc[0]
    delta2 = fpc[2] - fpc[1]
    nind_delta1 = nind[1] - nind[0]
    nind_delta2 = nind[2] - nind[1]
    alive = [natural & (values >= 1.0e-8) & (density >= 1.0e-10) for values, density in zip(fpc, nind)]

    by_type = output_dir / "pft_three_state_by_type.csv"
    with by_type.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "pft_id",
                "pft_name",
                "initial_grid_mean_fpc_pct",
                "year1_end_grid_mean_fpc_pct",
                "year2_end_grid_mean_fpc_pct",
                "year1_delta_pct_point",
                "year2_delta_pct_point",
                "year2_minus_year1_delta_pct_point",
                "year1_material_changed_slots_ge_0.01pp",
                "year2_material_changed_slots_ge_0.01pp",
                "year1_established_slots_proxy",
                "year1_lost_slots_proxy",
                "year2_established_slots_proxy",
                "year2_lost_slots_proxy",
                "year1_nind_delta_sum",
                "year2_nind_delta_sum",
            ]
        )
        for pft_id in range(17):
            mask = soil & (pft == pft_id)
            dynamic = natural & (pft == pft_id)
            means = [float(values[mask].sum() / grid_count) for values in fpc]
            writer.writerow(
                [
                    pft_id,
                    PFT_NAMES[pft_id],
                    *means,
                    means[1] - means[0],
                    means[2] - means[1],
                    (means[2] - means[1]) - (means[1] - means[0]),
                    int(np.count_nonzero(dynamic & (np.abs(delta1) >= 1.0e-2))),
                    int(np.count_nonzero(dynamic & (np.abs(delta2) >= 1.0e-2))),
                    int(np.count_nonzero(dynamic & ~alive[0] & alive[1])),
                    int(np.count_nonzero(dynamic & alive[0] & ~alive[1])),
                    int(np.count_nonzero(dynamic & ~alive[1] & alive[2])),
                    int(np.count_nonzero(dynamic & alive[1] & ~alive[2])),
                    float(nind_delta1[dynamic].sum()),
                    float(nind_delta2[dynamic].sum()),
                ]
            )

    material1 = natural & (np.abs(delta1) >= 1.0e-2)
    material2 = natural & (np.abs(delta2) >= 1.0e-2)
    both = material1 & material2
    same_direction = both & (np.sign(delta1) == np.sign(delta2))
    reversed_direction = both & (np.sign(delta1) != np.sign(delta2))
    abs_total1 = float(np.abs(delta1[natural]).sum())
    abs_total2 = float(np.abs(delta2[natural]).sum())
    annual_activity_ratio = abs_total2 / abs_total1 if abs_total1 > 0.0 else float("nan")

    natural_means = [float(values[natural].sum() / grid_count) for values in fpc]
    bare_means = [float(values[soil & (pft == 0)].sum() / grid_count) for values in fpc]
    crop_means = [float(values[soil & (pft == 15)].sum() / grid_count) for values in fpc]
    irrigated_means = [float(values[soil & (pft == 16)].sum() / grid_count) for values in fpc]
    dominant = [dominant_pft(values, pft, natural, gidx, grid_count) for values in fpc]

    summary_lines = [
        f"initial_file={paths[0]}",
        f"year1_file={paths[1]}",
        f"year2_file={paths[2]}",
        f"initial_mcdate={states[0]['mcdate']}",
        f"year1_mcdate={states[1]['mcdate']}",
        f"year2_mcdate={states[2]['mcdate']}",
        f"initial_mcsec={states[0]['mcsec']}",
        f"year1_mcsec={states[1]['mcsec']}",
        f"year2_mcsec={states[2]['mcsec']}",
        f"numpft={states[0]['numpft']}",
        f"soil_gridcells={int(soil_grid.sum())}",
        f"natural_pft_slots={int(natural.sum())}",
        f"initial_max_fpc_closure_error_pp={closure[0]:.15g}",
        f"year1_max_fpc_closure_error_pp={closure[1]:.15g}",
        f"year2_max_fpc_closure_error_pp={closure[2]:.15g}",
        f"natural_grid_mean_fpc_pct_initial={natural_means[0]:.15g}",
        f"natural_grid_mean_fpc_pct_year1={natural_means[1]:.15g}",
        f"natural_grid_mean_fpc_pct_year2={natural_means[2]:.15g}",
        f"natural_grid_mean_delta_year1_pp={natural_means[1] - natural_means[0]:.15g}",
        f"natural_grid_mean_delta_year2_pp={natural_means[2] - natural_means[1]:.15g}",
        f"bare_grid_mean_fpc_pct_initial={bare_means[0]:.15g}",
        f"bare_grid_mean_fpc_pct_year1={bare_means[1]:.15g}",
        f"bare_grid_mean_fpc_pct_year2={bare_means[2]:.15g}",
        f"crop15_grid_mean_fpc_pct_initial={crop_means[0]:.15g}",
        f"crop15_grid_mean_fpc_pct_year1={crop_means[1]:.15g}",
        f"crop15_grid_mean_fpc_pct_year2={crop_means[2]:.15g}",
        f"irrigated16_grid_mean_fpc_pct_initial={irrigated_means[0]:.15g}",
        f"irrigated16_grid_mean_fpc_pct_year1={irrigated_means[1]:.15g}",
        f"irrigated16_grid_mean_fpc_pct_year2={irrigated_means[2]:.15g}",
        f"year1_changed_natural_slots_gt_1e-8pp={int(np.count_nonzero(natural & (np.abs(delta1) > 1.0e-8)))}",
        f"year2_changed_natural_slots_gt_1e-8pp={int(np.count_nonzero(natural & (np.abs(delta2) > 1.0e-8)))}",
        f"year1_material_changed_natural_slots_ge_0.01pp={int(np.count_nonzero(material1))}",
        f"year2_material_changed_natural_slots_ge_0.01pp={int(np.count_nonzero(material2))}",
        f"material_changed_both_years_slots={int(np.count_nonzero(both))}",
        f"material_same_direction_both_years_slots={int(np.count_nonzero(same_direction))}",
        f"material_reversed_direction_both_years_slots={int(np.count_nonzero(reversed_direction))}",
        f"year1_total_abs_natural_fpc_change_pp={abs_total1:.15g}",
        f"year2_total_abs_natural_fpc_change_pp={abs_total2:.15g}",
        f"year2_to_year1_abs_change_ratio={annual_activity_ratio:.15g}",
        f"year1_established_natural_slots_proxy={int(np.count_nonzero(natural & ~alive[0] & alive[1]))}",
        f"year1_lost_natural_slots_proxy={int(np.count_nonzero(natural & alive[0] & ~alive[1]))}",
        f"year2_established_natural_slots_proxy={int(np.count_nonzero(natural & ~alive[1] & alive[2]))}",
        f"year2_lost_natural_slots_proxy={int(np.count_nonzero(natural & alive[1] & ~alive[2]))}",
        f"dominant_natural_pft_changed_gridcells_year1={int(np.count_nonzero(dominant[0] != dominant[1]))}",
        f"dominant_natural_pft_changed_gridcells_year2={int(np.count_nonzero(dominant[1] != dominant[2]))}",
        f"pft4_initial_grid_mean_fpc_pct={float(fpc[0][soil & (pft == 4)].sum() / grid_count):.15g}",
        f"pft4_year1_grid_mean_fpc_pct={float(fpc[1][soil & (pft == 4)].sum() / grid_count):.15g}",
        f"pft4_year2_grid_mean_fpc_pct={float(fpc[2][soil & (pft == 4)].sum() / grid_count):.15g}",
        f"qa_mapping_equal=true",
        f"qa_closure_ok=true",
        f"by_type_csv={by_type}",
    ]
    summary_path = output_dir / "pft_three_state_summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pft_ids = np.arange(17)
    pft_means = np.asarray(
        [[values[soil & (pft == pft_id)].sum() / grid_count for pft_id in pft_ids] for values in fpc]
    )
    aggregate = np.asarray([bare_means, natural_means, crop_means, irrigated_means]).T
    labels = [str(states[0]["mcdate"]), str(states[1]["mcdate"]), str(states[2]["mcdate"])]
    colors = ["#4c78a8", "#f58518", "#54a24b"]

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(14, 13),
        gridspec_kw={"height_ratios": [1.15, 1.0, 1.0]},
    )
    x0 = np.arange(4)
    width = 0.24
    for index, label in enumerate(labels):
        axes[0].bar(x0 + (index - 1) * width, aggregate[index], width, label=label, color=colors[index])
    axes[0].set_xticks(x0)
    axes[0].set_xticklabels(["Bare", "Natural PFTs 1–14", "Crop PFT15", "Irrigated PFT16"])
    axes[0].set_ylabel("Grid-mean target FPC (%)")
    axes[0].set_title("Target-cover composition at initialization and two year ends")
    axes[0].legend(title="Internal mcdate")
    axes[0].grid(axis="y", alpha=0.25)

    x1 = np.arange(17)
    axes[1].bar(x1, pft_means[1] - pft_means[0], 0.7, color="#4c78a8")
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set_xticks(x1)
    axes[1].set_xticklabels([str(value) for value in pft_ids])
    axes[1].set_ylabel("Annual target-FPC change (percentage points)")
    axes[1].set_title("First annual update by PFT (full scale)")
    axes[1].grid(axis="y", alpha=0.25)

    axes[2].bar(x1, pft_means[2] - pft_means[1], 0.7, color="#f58518")
    axes[2].axhline(0.0, color="black", linewidth=0.8)
    axes[2].set_xticks(x1)
    axes[2].set_xticklabels([str(value) for value in pft_ids])
    axes[2].set_xlabel("CLM PFT id")
    axes[2].set_ylabel("Annual target-FPC change (percentage points)")
    axes[2].set_title("Second annual update by PFT (zoomed; independent vertical scale)")
    axes[2].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    chart_path = output_dir / "pft_two_annual_updates.png"
    fig.savefig(chart_path, dpi=180, facecolor="white")
    plt.close(fig)

    grid_abs_delta2 = np.bincount(
        gidx[natural], weights=np.abs(delta2[natural]), minlength=grid_count
    )
    fig, ax = plt.subplots(figsize=(11, 6.5))
    points = ax.scatter(
        states[0]["lon"],
        states[0]["lat"],
        c=grid_abs_delta2,
        s=18,
        cmap="viridis",
        linewidths=0,
    )
    year2_label = str(states[1]["mcdate"])[:4]
    fig.colorbar(
        points,
        ax=ax,
        label=f"Sum |{year2_label} annual target-FPC change| (pp)",
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Spatial magnitude of the second annual CNDV update")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    map_path = output_dir / "pft_year2_abs_change_map.png"
    fig.savefig(map_path, dpi=180, facecolor="white")
    plt.close(fig)

    print("\n".join(summary_lines))
    print(f"chart={chart_path}")
    print(f"year2_map={map_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
