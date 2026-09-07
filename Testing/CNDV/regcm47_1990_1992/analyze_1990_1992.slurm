#!/bin/bash
#SBATCH -J c47yr91_pft
#SBATCH -p debug
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 00:15:00
#SBATCH -o logs/analyze.%j.out
#SBATCH -e logs/analyze.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C
export OMP_NUM_THREADS=1

first=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_crossyear_regcm47_1990
run=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_year2_regcm47_1991
python=/public/home/elpt_2024_000795/anaconda3/bin/python3
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

initial="$first/output/c47yr1990.clm.regcm.hv.1991.nc"
year1="$first/output/c47yr1990.clm.regcm.hv.1992.nc"
year2="$run/output/c47yr1990.clm.regcm.hv.1993.nc"
restart="$run/output/c47yr1990.clm.regcm.r.1992010100.nc"
year1_restart="$first/output/c47yr1990.clm.regcm.r.1991010100.nc"

for file in "$initial" "$year1" "$year2" "$restart" "$year1_restart"; do
  test -s "$file"
  ncdump -h "$file" >/dev/null
done

test -s "$script_dir/analyze_pft_change.py"
test -s "$script_dir/analyze_three_year_states.py"
"$python" "$script_dir/analyze_pft_change.py" \
  "$year1" "$year2" "$run/analysis/year2_pair" "$restart" "$year1_restart"

"$python" "$script_dir/analyze_three_year_states.py" \
  "$initial" "$year1" "$year2" "$run/analysis/three_state"

for file in \
  "$run/analysis/year2_pair/pft_change_summary.txt" \
  "$run/analysis/year2_pair/pft_change_by_type.csv" \
  "$run/analysis/three_state/pft_three_state_summary.txt" \
  "$run/analysis/three_state/pft_three_state_by_type.csv" \
  "$run/analysis/three_state/pft_two_annual_updates.png" \
  "$run/analysis/three_state/pft_year2_abs_change_map.png"; do
  test -s "$file"
done

pair_summary="$run/analysis/year2_pair/pft_change_summary.txt"
three_summary="$run/analysis/three_state/pft_three_state_summary.txt"
grep -qx 'initial_mcdate=19910101' "$pair_summary"
grep -qx 'final_mcdate=19920101' "$pair_summary"
grep -qx 'qa_fpc_closure_ok=true' "$pair_summary"
grep -qx 'qa_restart_soil_crosscheck_ok=true' "$pair_summary"
grep -qx 'qa_drought_days_reset_ok=true' "$pair_summary"
grep -qx 'qa_initial_restart_natural_crosscheck_ok=true' "$pair_summary"
grep -qx 'initial_mcdate=19900101' "$three_summary"
grep -qx 'year1_mcdate=19910101' "$three_summary"
grep -qx 'year2_mcdate=19920101' "$three_summary"
grep -qx 'qa_mapping_equal=true' "$three_summary"
grep -qx 'qa_closure_ok=true' "$three_summary"

printf 'PFT_YEAR2_ANALYSIS_OK\n'
