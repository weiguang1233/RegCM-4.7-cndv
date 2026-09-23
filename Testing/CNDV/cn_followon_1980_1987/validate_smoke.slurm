#!/bin/bash
#SBATCH -J cndvcn_gate
#SBATCH -p cpu_single
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 01:00:00
#SBATCH -o logs/gate.%j.out
#SBATCH -e logs/gate.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C

module purge
module load compiler/intel/2021.3.0
module load mathlib/hdf5/intel/1.8.20
module load mathlib/netcdf/intel/4.4.1
module load mathlib/zlib/intel/1.2.11

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_cn_followon_1980_1987
python=/public/home/elpt_2024_000795/anaconda3/bin/python3
cd "$root"

: > analysis/smoke_gate.txt
for version in regcm47 regcm5; do
  exact="$root/${version}_exact_smoke/output"
  test -s "$exact/cndvab_SAV.1980020100.nc"
  test -s "$exact/cndvab.clm.regcm.r.1980020100.nc"
  for tape in rh0 rh1 rh2; do
    test -s "$exact/cndvab.clm.regcm.${tape}.1980020100.nc"
  done
  h2=$(find "$exact" -maxdepth 1 -type f -name '*.clm.regcm.h2.*.nc' | sort | tail -1)
  test -n "$h2"
  header=$(mktemp)
  ncdump -h "$h2" > "$header"
  for field in TOTVEGC TOTVEGN LEAFC FROOTC WOODC LEAFN FROOTN NPOOL; do
    grep -q " ${field}(" "$header"
  done
  rm -f "$header"
  printf 'SMOKE_GATE_OK version=%s h2=%s\n' "$version" "$(basename "$h2")" \
    | tee -a analysis/smoke_gate.txt
done

probe="$root/regcm47_histfix_probe/output"
test -s "$probe/cndvab_SAV.1980020100.nc"
test -s "$probe/cndvab.clm.regcm.r.1980020100.nc"
probe_log=$(find "$root/regcm47_histfix_probe/logs" -maxdepth 1 -type f -name 'run.*.out' | sort | tail -1)
test -n "$probe_log"
test "$(grep -c 'Successfully wrote out restart data for CLM 4.5' "$probe_log")" -eq 31
! grep -q 'NetCDF: Variable not found' "$probe_log"
grep -q 'CNDV_CN_RUN_OK version=regcm47 mode=histfix_probe final=1980020100' "$probe_log"
"$python" compare_restart.py \
  "$root/regcm47_exact_smoke/output/cndvab.clm.regcm.r.1980020100.nc" \
  "$probe/cndvab.clm.regcm.r.1980020100.nc" | tee -a analysis/smoke_gate.txt
"$python" compare_restart.py \
  "$root/regcm47_exact_smoke/output/cndvab_SAV.1980020100.nc" \
  "$probe/cndvab_SAV.1980020100.nc" | tee -a analysis/smoke_gate.txt
printf 'REGCM47_HISTORY_REOPEN_GATE_OK daily_restart_cycles=31\n' \
  | tee -a analysis/smoke_gate.txt
printf 'HISTORY_RECONFIGURATION_PROBE_REJECTED_AS_EXPECTED: CLM requires unchanged history options on restart\n' \
  | tee -a analysis/smoke_gate.txt
printf 'CNDV_CN_SMOKE_GATE_PASS\n' | tee -a analysis/smoke_gate.txt
