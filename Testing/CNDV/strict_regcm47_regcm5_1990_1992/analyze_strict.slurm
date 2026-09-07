#!/bin/bash
#SBATCH -J cndvab_qa
#SBATCH -p debug
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 00:30:00
#SBATCH -o logs/strict_analysis.%j.out
#SBATCH -e logs/strict_analysis.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C
export OMP_NUM_THREADS=1

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_strict_compare_regcm47_regcm5_1990_1992
python=/public/home/elpt_2024_000795/anaconda3/bin/python3
output47="$root/regcm47_full/output"
output5="$root/regcm5_full/output"
analysis="$root/analysis/strict"
cd "$root"

for output in "$output47" "$output5"; do
  for year in 1991 1992 1993; do
    test -s "$output/cndvab.clm.regcm.hv.$year.nc"
    ncdump -h "$output/cndvab.clm.regcm.hv.$year.nc" >/dev/null
  done
  for stamp in 1991010100 1992010100; do
    test -s "$output/cndvab.clm.regcm.r.$stamp.nc"
    ncdump -h "$output/cndvab.clm.regcm.r.$stamp.nc" >/dev/null
  done
done

mkdir -p "$analysis/regcm47_year1" "$analysis/regcm47_year2" \
  "$analysis/regcm5_year1" "$analysis/regcm5_year2"

"$python" analyze_pft_change_regcm47.py \
  "$output47/cndvab.clm.regcm.hv.1991.nc" \
  "$output47/cndvab.clm.regcm.hv.1992.nc" \
  "$analysis/regcm47_year1" \
  "$output47/cndvab.clm.regcm.r.1991010100.nc"
"$python" analyze_pft_change_regcm47.py \
  "$output47/cndvab.clm.regcm.hv.1992.nc" \
  "$output47/cndvab.clm.regcm.hv.1993.nc" \
  "$analysis/regcm47_year2" \
  "$output47/cndvab.clm.regcm.r.1992010100.nc" \
  "$output47/cndvab.clm.regcm.r.1991010100.nc"
"$python" analyze_pft_change_regcm5.py \
  "$output5/cndvab.clm.regcm.hv.1991.nc" \
  "$output5/cndvab.clm.regcm.hv.1992.nc" \
  "$analysis/regcm5_year1" \
  "$output5/cndvab.clm.regcm.r.1991010100.nc"
"$python" analyze_pft_change_regcm5.py \
  "$output5/cndvab.clm.regcm.hv.1992.nc" \
  "$output5/cndvab.clm.regcm.hv.1993.nc" \
  "$analysis/regcm5_year2" \
  "$output5/cndvab.clm.regcm.r.1992010100.nc" \
  "$output5/cndvab.clm.regcm.r.1991010100.nc"

"$python" analyze_strict_compare.py "$output47" "$output5" "$analysis"
summary="$analysis/strict_comparison_summary.txt"
test -s "$summary"
test -s "$analysis/strict_pft_comparison_by_type.csv"
test -s "$analysis/strict_paired_grid_summary.csv"
test -s "$analysis/strict_comparison.png"
grep -qx 'qa_common_initial_state=true' "$summary"
grep -qx 'qa_common_grid_and_mapping=true' "$summary"
grep -qx 'qa_each_version_fpc_closure=true' "$summary"
grep -qx 'qa_each_version_restart_drought_reset=true' "$summary"
grep -qx 'qa_each_version_drought_recurrence=true' "$summary"
grep -qx 'qa_data_valid=true' "$summary"
printf 'STRICT_CROSS_VERSION_ANALYSIS_OK\n'
