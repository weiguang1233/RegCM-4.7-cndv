#!/bin/bash
#SBATCH -J cndvab_gate
#SBATCH -p debug
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 00:15:00
#SBATCH -o logs/initial_gate.%j.out
#SBATCH -e logs/initial_gate.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_strict_compare_regcm47_regcm5_1990_1992
python=/public/home/elpt_2024_000795/anaconda3/bin/python3
cd "$root"

file47="$root/regcm47_smoke/output/cndvab.clm.regcm.hv.1991.nc"
file5="$root/regcm5_smoke/output/cndvab.clm.regcm.hv.1991.nc"
for file in "$file47" "$file5"; do
  test -s "$file"
  ncdump -h "$file" >/dev/null
done

"$python" validate_initial_gate.py "$file47" "$file5" "$root/analysis/initial_gate"
grep -qx 'qa_all=true' "$root/analysis/initial_gate/initial_gate_summary.txt"
printf 'STRICT_INITIAL_STATE_GATE_OK\n'
