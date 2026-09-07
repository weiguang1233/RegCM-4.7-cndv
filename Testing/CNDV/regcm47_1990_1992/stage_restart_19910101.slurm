#!/bin/bash
#SBATCH -J c47yr91_stage
#SBATCH -p debug
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 00:15:00
#SBATCH -o logs/stage.%j.out
#SBATCH -e logs/stage.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C

first=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_crossyear_regcm47_1990
run=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_year2_regcm47_1991

for name in \
  c47yr1990_SAV.1991010100.nc \
  c47yr1990.clm.regcm.r.1991010100.nc \
  c47yr1990.clm.regcm.rh0.1991010100.nc; do
  source_file="$first/output/$name"
  target_file="$run/output/$name"
  test -s "$source_file"
  ncdump -h "$source_file" >/dev/null
  if test -e "$target_file"; then
    cmp -s "$source_file" "$target_file"
  else
    cp -p "$source_file" "$target_file"
  fi
  cmp -s "$source_file" "$target_file"
  sha256sum "$source_file" "$target_file"
done

printf 'RESTART_STAGE_OK\n'
