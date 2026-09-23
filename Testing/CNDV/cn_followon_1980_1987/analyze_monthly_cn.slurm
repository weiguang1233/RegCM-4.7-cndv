#!/bin/bash
#SBATCH -J cndvcn_analysis
#SBATCH -p cpu_single
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 02:00:00
#SBATCH -o logs/analysis.%j.out
#SBATCH -e logs/analysis.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C
export OMP_NUM_THREADS=1

module purge
module load compiler/intel/2021.3.0
module load mathlib/hdf5/intel/1.8.20
module load mathlib/netcdf/intel/4.4.1
module load mathlib/zlib/intel/1.2.11

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_cn_followon_1980_1987
python=/public/home/elpt_2024_000795/anaconda3/bin/python3
cd "$root"

for version in regcm47 regcm5; do
  case_dir="${version}_full"
  test "$version" = regcm47 && case_dir=regcm47_full_fixed
  log=$(find "$root/${case_dir}/logs" -maxdepth 1 -type f -name 'run.*.out' | sort | tail -1)
  test -n "$log"
  test "$(grep -c 'Annual CNDV calculations are complete' "$log")" -eq 7
  grep -q 'Final time  1987-01-01 00:00:00 UTC reached' "$log"
  grep -q 'simulation successfully reached end' "$log"
done

"$python" analyze_monthly_cn.py \
  "$root/regcm47_full_fixed/output" \
  "$root/regcm5_full/output" \
  "$root/analysis"

sha256sum analysis/daily_carbon_nitrogen_pools.csv \
  analysis/annual_carbon_nitrogen_summary.csv \
  analysis/annual_cndv_fpc_targets.csv \
  analysis/restart_carbon_nitrogen_checkpoints.csv \
  analysis/carbon_nitrogen_summary.json \
  analysis/carbon_nitrogen_pools_1980_1986.png \
  analysis/carbon_nitrogen_components_checkpoints.png \
  analysis/cndv_fpc_actual_vs_target.png \
  > analysis/result_sha256.txt
printf 'CNDV_CN_ANALYSIS_PASS\n'
