#!/bin/bash
#SBATCH -J cndv_ndep_analysis
#SBATCH -p cpu_single
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 01:00:00
#SBATCH -o logs/analysis.%j.out
#SBATCH -e logs/analysis.%j.err
set -euo pipefail
export LANG=C LC_ALL=C OMP_NUM_THREADS=1
module purge
module load compiler/intel/2021.3.0 mathlib/netcdf/intel/4.4.1
module load mathlib/hdf5/intel/1.8.20 mathlib/zlib/intel/1.2.11
root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_ndep_unit_validation_1979
cd "$root"
for case_name in regcm47_baseline regcm47_ndepfix regcm5_baseline regcm5_ndepfix regcm5_lai47 regcm5_lai47_ndepfix; do
  for phase in startup month; do
    log=$(find "$root/${case_name}_${phase}/logs" -maxdepth 1 -type f -name 'run.*.out' | sort | tail -n 1)
    test -n "$log"
    grep -aq 'simulation successfully reached end' "$log"
    grep -aq 'NDEP_VALIDATION_RUN_OK' "$log"
  done
done
/public/home/elpt_2024_000795/anaconda3/bin/python3 analyze_experiments.py "$root"
sha256sum analysis/*timeseries.csv analysis/*comparison_long.csv analysis/ndep_validation_summary.json analysis/history_units.json analysis/independent_output_checks.json \
  > analysis/result_sha256.txt
