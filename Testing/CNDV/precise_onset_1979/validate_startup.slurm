#!/bin/bash
#SBATCH -J cndv79gate
#SBATCH -p cpu_single
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 01:00:00
#SBATCH -o logs/startup_gate.%j.out
#SBATCH -e logs/startup_gate.%j.err

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

for version in regcm47 regcm5; do
  output="$root/${version}_startup/output"
  test "$(find "$output" -maxdepth 1 -type f -name '*.h0.*.nc' | wc -l)" -ge 1
  test "$(find "$output" -maxdepth 1 -type f -name '*.h1.*.nc' | wc -l)" -ge 1
  test "$(find "$output" -maxdepth 1 -type f -name '*.h2.*.nc' | wc -l)" -ge 1
  test "$(find "$output" -maxdepth 1 -type f -name '*.r.*.nc' | wc -l)" -ge 1
  h2_file=$(find "$output" -maxdepth 1 -type f -name '*.h2.*.nc' -print -quit)
  h1_file=$(find "$output" -maxdepth 1 -type f -name '*.h1.*.nc' -print -quit)
  ncdump -h "$h2_file" > "analysis/${version}_startup_h2_header.txt"
  ncdump -h "$h1_file" > "analysis/${version}_startup_h1_header.txt"
  grep -q 'TOTVEGC' "analysis/${version}_startup_h2_header.txt"
  grep -q 'INIT_GPP' "analysis/${version}_startup_h1_header.txt"
done

"$python" analyze_precise_onset.py --root "$root" --phase startup
test -s analysis/startup_regional_timeseries.csv
test -s analysis/startup_first_divergence.csv
printf 'PRECISE_ONSET_STARTUP_GATE_OK\n'
