#!/usr/bin/env python3
"""Compare baseline RegCM4.7/RegCM5 with the one-change RegCM5 LAI experiment."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import analyze_precise_onset as onset


ROOT = Path("/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979")
CASES = {
    "RegCM4.7 baseline": "regcm47",
    "RegCM5 baseline": "regcm5",
    "RegCM5 + RegCM4.7 LAI": "regcm5_lai47",
}
FOCUS = (
    "NATURAL_FPC_PCT", "LEAFC", "TLAI", "ELAI", "BTRAN", "INIT_GPP",
    "GPP", "NPP", "TOTVEGC", "TOTVEGN", "CUM_INIT_GPP", "CUM_GPP",
    "CUM_NPP", "TBOT", "QBOT", "WIND", "RAIN", "SNOW", "FSDS", "FLDS",
    "SOILWATER_10CM", "FPG", "SMINN", "DOWNREG", "PLANT_NDEMAND",
    "PLANT_NALLOC",
)


def write_rows(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rows = {}
    for label, directory in CASES.items():
        rows[label], _ = onset.load_phase(ROOT, directory, "startup")
        if len(rows[label]) != 24:
            raise ValueError(f"{label}: expected 24 records, got {len(rows[label])}")

    comparison = []
    for reference in ("RegCM4.7 baseline", "RegCM5 baseline"):
        candidate = "RegCM5 + RegCM4.7 LAI"
        for row in onset.compare_rows(rows[reference], rows[candidate]):
            if row["metric"] not in FOCUS:
                continue
            comparison.append({
                "reference": reference,
                "candidate": candidate,
                **row,
            })
    write_rows(ROOT / "analysis" / "lai_ablation_comparison_long.csv", comparison)

    snapshots = []
    for label, values in rows.items():
        for hour in (1, 12, 24):
            row = values[hour - 1]
            for metric in FOCUS:
                if metric in row:
                    snapshots.append({
                        "case": label,
                        "hour": hour,
                        "datetime": row["datetime"],
                        "metric": metric,
                        "value": row[metric],
                    })
    write_rows(ROOT / "analysis" / "lai_ablation_snapshots.csv", snapshots)

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "record_counts": {name: len(value) for name, value in rows.items()},
        "experiment": "RegCM5 with only the RegCM4.7 legacy leafC-to-LAI block",
        "outputs": [
            "lai_ablation_comparison_long.csv",
            "lai_ablation_snapshots.csv",
        ],
    }
    with (ROOT / "analysis" / "lai_ablation_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
