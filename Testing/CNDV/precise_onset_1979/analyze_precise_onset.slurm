#!/bin/bash
#SBATCH -J cndv79ana
#SBATCH -p cpu_single
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 06:00:00
#SBATCH -o logs/analysis.%j.out
#SBATCH -e logs/analysis.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C

module purge
module load compiler/intel/2021.3.0
module load mathlib/netcdf/intel/4.4.1
hash -r

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
python=/public/home/elpt_2024_000795/anaconda3/bin/python3
cd "$root"
command -v ncdump >/dev/null
command -v nccopy >/dev/null
"$python" analyze_precise_onset.py --root "$root" --phase all
"$python" audit_precise_results.py --analysis-dir "$root/analysis"
test -s analysis/daily_regional_timeseries.csv
test -s analysis/daily_first_divergence.csv
test -s analysis/annual_update_before_after.csv
test -s analysis/annual_cndv_hv_summary.csv
test -s analysis/annual_cndv_hv_by_pft.csv
test -s analysis/precision_audit_summary.json
printf 'PRECISE_ONSET_ANALYSIS_OK\n'
