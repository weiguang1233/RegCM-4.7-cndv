#!/usr/bin/env python3
"""Independent consistency audit for the precise CNDV onset experiment."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float:
    return float(row[key])


def ratio_pct(numerator: float, denominator: float) -> float:
    return numerator / denominator * 100.0


def by_case_hour(rows: list[dict[str, str]], case: str, hour: int, metric: str) -> float:
    selected = [
        row for row in rows
        if row["case"] == case and int(row["hour"]) == hour and row["metric"] == metric
    ]
    if len(selected) != 1:
        raise ValueError(f"expected one {case=} {hour=} {metric=}, got {len(selected)}")
    return number(selected[0], "value")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-dir", type=Path, required=True)
    args = parser.parse_args()
    directory = args.analysis_dir.resolve()

    startup = read(directory / "startup_regional_timeseries.csv")
    daily = read(directory / "daily_regional_timeseries.csv")
    ablation = read(directory / "lai_ablation_snapshots.csv")
    annual_update = read(directory / "annual_update_before_after.csv")
    hv = read(directory / "annual_cndv_hv_summary.csv")

    startup_by_version = {
        version: [row for row in startup if row["version"] == version]
        for version in ("RegCM4.7", "RegCM5")
    }
    daily_by_version = {
        version: [row for row in daily if row["version"] == version]
        for version in ("RegCM4.7", "RegCM5")
    }
    checks = {
        "startup_has_24_records_each": all(
            len(rows) == 24 for rows in startup_by_version.values()
        ),
        "daily_has_365_records_each": all(
            len(rows) == 365 for rows in daily_by_version.values()
        ),
        "startup_timestamps_paired": (
            [row["datetime"] for row in startup_by_version["RegCM4.7"]]
            == [row["datetime"] for row in startup_by_version["RegCM5"]]
        ),
        "daily_timestamps_paired": (
            [row["datetime"] for row in daily_by_version["RegCM4.7"]]
            == [row["datetime"] for row in daily_by_version["RegCM5"]]
        ),
    }

    balance = {}
    for version, rows in daily_by_version.items():
        errors = [abs(number(row, "NPP_BALANCE_ERROR")) for row in rows]
        balance[version] = max(errors)
    checks["npp_balance_below_1e-10"] = max(balance.values()) < 1.0e-10

    first47 = startup_by_version["RegCM4.7"][0]
    first5 = startup_by_version["RegCM5"][0]
    initial_relative_difference = {}
    for metric in ("NATURAL_FPC_PCT", "LEAFC", "TOTVEGC", "TOTVEGN"):
        left = number(first47, metric)
        right = number(first5, metric)
        initial_relative_difference[metric] = abs(right - left) / max(abs(left), 1.0e-30)
    checks["initial_core_state_matches"] = max(initial_relative_difference.values()) < 1.0e-8

    last47 = daily_by_version["RegCM4.7"][-1]
    last5 = daily_by_version["RegCM5"][-1]
    annual_metrics = {}
    for metric in (
        "CUM_PRECIP", "CUM_GPP", "CUM_AR", "CUM_NPP", "ANNSUM_NPP",
        "TOTVEGC", "TOTVEGN", "LEAFC", "FROOTC", "WOODC", "TLAI", "ELAI",
    ):
        value47 = number(last47, metric)
        value5 = number(last5, metric)
        annual_metrics[metric] = {
            "regcm47": value47,
            "regcm5": value5,
            "regcm5_over_regcm47_pct": ratio_pct(value5, value47),
        }

    cases = ("RegCM4.7 baseline", "RegCM5 baseline", "RegCM5 + RegCM4.7 LAI")
    ablation_metrics = {}
    for metric in ("TLAI", "ELAI", "BTRAN", "CUM_GPP", "CUM_NPP", "TOTVEGC"):
        values = {case: by_case_hour(ablation, case, 24, metric) for case in cases}
        ablation_metrics[metric] = values
        values["ablation_over_regcm47_pct"] = ratio_pct(
            values["RegCM5 + RegCM4.7 LAI"], values["RegCM4.7 baseline"]
        )
        if abs(values["RegCM5 baseline"]) > 1.0e-30:
            values["ablation_over_regcm5_fold"] = (
                values["RegCM5 + RegCM4.7 LAI"] / values["RegCM5 baseline"]
            )
    checks["lai_ablation_matches_regcm47_tlai"] = (
        abs(
            ablation_metrics["TLAI"]["RegCM5 + RegCM4.7 LAI"]
            - ablation_metrics["TLAI"]["RegCM4.7 baseline"]
        ) / ablation_metrics["TLAI"]["RegCM4.7 baseline"] < 1.0e-5
    )

    hv_by_version_metric = {(row["version"], row["metric"]): row for row in hv}
    annual_hv = {}
    for version in ("RegCM4.7", "RegCM5"):
        annual_hv[version] = {}
        for metric in ("NATURAL_FPC_PCT", "WEIGHTED_NIND", "FPC_WEIGHTED_NIND"):
            row = hv_by_version_metric[(version, metric)]
            annual_hv[version][metric] = {
                "initial": number(row, "initial_hv"),
                "post_dv": number(row, "post_dv_hv"),
                "post_over_initial_pct": number(row, "post_over_initial_pct"),
            }
    checks["initial_hv_fpc_matches"] = math.isclose(
        annual_hv["RegCM4.7"]["NATURAL_FPC_PCT"]["initial"],
        annual_hv["RegCM5"]["NATURAL_FPC_PCT"]["initial"],
        rel_tol=0.0, abs_tol=1.0e-12,
    )
    checks["initial_hv_nind_matches"] = math.isclose(
        annual_hv["RegCM4.7"]["FPC_WEIGHTED_NIND"]["initial"],
        annual_hv["RegCM5"]["FPC_WEIGHTED_NIND"]["initial"],
        rel_tol=0.0, abs_tol=1.0e-12,
    )

    pool_metrics = {
        "TOTVEGC", "TOTVEGN", "LEAFC", "FROOTC", "WOODC", "ELAI", "TLAI"
    }
    pool_rows = [row for row in annual_update if row["metric"] in pool_metrics]
    maximum_dv_pool_relative_change = max(
        abs(number(row, "post_dv_restart") - number(row, "pre_dv_last_history"))
        / max(abs(number(row, "pre_dv_last_history")), 1.0e-30)
        for row in pool_rows
    )
    checks["dv_does_not_directly_rewrite_cn_pools"] = maximum_dv_pool_relative_change < 1.0e-7

    result = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pass": all(checks.values()),
        "checks": checks,
        "record_counts": {
            "startup": {key: len(value) for key, value in startup_by_version.items()},
            "daily": {key: len(value) for key, value in daily_by_version.items()},
        },
        "maximum_absolute_daily_npp_balance_error": balance,
        "initial_relative_difference": initial_relative_difference,
        "annual_metrics": annual_metrics,
        "hour24_lai_ablation": ablation_metrics,
        "annual_hv": annual_hv,
        "maximum_dv_pool_relative_change": maximum_dv_pool_relative_change,
    }
    output = directory / "precision_audit_summary.json"
    with output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
