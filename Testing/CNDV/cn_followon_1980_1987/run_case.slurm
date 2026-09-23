#!/bin/bash
#SBATCH -J cndvcn
#SBATCH -p cpu_parallel
#SBATCH -N 2
#SBATCH -n 128
#SBATCH --ntasks-per-node=64
#SBATCH -t 12:00:00

set -euo pipefail
export LANG=C
export LC_ALL=C
export OMP_NUM_THREADS=1
ulimit -s unlimited
ulimit -c unlimited

module purge
module load compiler/intel/2021.3.0
module load mpi/intelmpi/2021.3.0
module load mathlib/hdf5/intel/1.8.20
module load mathlib/netcdf/intel/4.4.1
module load mathlib/zlib/intel/1.2.11
hash -r

version=${VERSION:?VERSION must be regcm47 or regcm5}
mode=${MODE:?MODE must be exact_smoke, expanded_smoke, histfix_probe, full, or full_fixed}
case "$version" in
  regcm47)
    exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin/regcmMPICN_CNDV_CLM45
    ;;
  regcm5)
    exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv/install/bin/regcmMPICN_CNDV_CLM45
    ;;
  *) printf 'invalid VERSION=%s\n' "$version" >&2; exit 2 ;;
esac
if [ -n "${EXE_OVERRIDE:-}" ]; then
  exe=$EXE_OVERRIDE
fi
case "$mode" in
  exact_smoke|expanded_smoke|histfix_probe) final=1980020100 ;;
  full|full_fixed) final=1987010100 ;;
  *) printf 'invalid MODE=%s\n' "$mode" >&2; exit 2 ;;
esac

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_cn_followon_1980_1987
namelist="$root/${version}_${mode}.in"
output="$root/${version}_${mode}/output"

cd "$root"
test -x "$exe"
test -s "$namelist"
test -s "$output/cndvab_SAV.1980010100.nc"
test -s "$output/cndvab.clm.regcm.r.1980010100.nc"
test -z "$(find "$output" -maxdepth 1 -type f -name '*.h[0-9].*.nc' -print -quit)"

date -u '+UTC_START=%Y-%m-%dT%H:%M:%SZ'
printf 'VERSION=%s MODE=%s MPI_TASKS=%s HOST=%s\n' \
  "$version" "$mode" "${SLURM_NTASKS:-128}" "$(hostname)"
sha256sum "$exe" "$namelist" "$output"/*1980010100.nc
mpirun -n 128 "$exe" "$namelist"
test -s "$output/cndvab_SAV.${final}.nc"
test -s "$output/cndvab.clm.regcm.r.${final}.nc"
grep -q "mdate2 = ${final}" "$namelist"
date -u '+UTC_END=%Y-%m-%dT%H:%M:%SZ'
printf 'CNDV_CN_RUN_OK version=%s mode=%s final=%s\n' "$version" "$mode" "$final"
