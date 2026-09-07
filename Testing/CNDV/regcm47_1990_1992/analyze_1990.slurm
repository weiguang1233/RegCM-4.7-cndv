#!/bin/bash
#SBATCH -J c47yr90_pft
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
python=/public/home/elpt_2024_000795/anaconda3/bin/python3
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

initial="$first/output/c47yr1990.clm.regcm.hv.1991.nc"
final="$first/output/c47yr1990.clm.regcm.hv.1992.nc"
restart="$first/output/c47yr1990.clm.regcm.r.1991010100.nc"

for file in "$initial" "$final" "$restart"; do
  test -s "$file"
  ncdump -h "$file" >/dev/null
done

test -s "$script_dir/analyze_pft_change.py"
"$python" "$script_dir/analyze_pft_change.py" \
  "$initial" "$final" "$first/analysis" "$restart"

summary="$first/analysis/pft_change_summary.txt"
grep -qx 'initial_mcdate=19900101' "$summary"
grep -qx 'final_mcdate=19910101' "$summary"
grep -qx 'qa_fpc_closure_ok=true' "$summary"
grep -qx 'qa_restart_soil_crosscheck_ok=true' "$summary"
grep -qx 'qa_drought_days_reset_ok=true' "$summary"
printf 'PFT_YEAR1_ANALYSIS_OK\n'
