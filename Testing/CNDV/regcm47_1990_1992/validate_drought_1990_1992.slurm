#!/bin/bash
#SBATCH -J c47yr91_d20
#SBATCH -p debug
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 00:15:00
#SBATCH -o logs/drought.%j.out
#SBATCH -e logs/drought.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C
export OMP_NUM_THREADS=1

first=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_crossyear_regcm47_1990
run=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_year2_regcm47_1991
python=/public/home/elpt_2024_000795/anaconda3/bin/python3
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

year1="$first/output/c47yr1990.clm.regcm.r.1991010100.nc"
history="$run/output/c47yr1990.clm.regcm.h0.199201.nc"
year2="$run/output/c47yr1990.clm.regcm.r.1992010100.nc"
result="$run/analysis/drought_recurrence"

for file in "$year1" "$history" "$year2"; do
  test -s "$file"
  ncdump -h "$file" >/dev/null
done

test -s "$script_dir/validate_drought_recurrence.py"
"$python" "$script_dir/validate_drought_recurrence.py" \
  "$year1" "$history" "$year2" "$result"

summary="$result/drought_recurrence_summary.txt"
test -s "$summary"
test -s "$result/drought_recurrence_by_column.csv"
grep -qx 'qa_history_carries_year1_d20=true' "$summary"
grep -qx 'qa_year2_d20_recurrence_ok=true' "$summary"
grep -qx 'qa_year2_drought_days_reset_ok=true' "$summary"

printf 'DROUGHT_RECURRENCE_OK\n'
