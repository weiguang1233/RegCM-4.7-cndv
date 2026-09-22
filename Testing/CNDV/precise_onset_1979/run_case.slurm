#!/bin/bash
#SBATCH -J cndv79loc
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
phase=${PHASE:?PHASE must be startup or daily}
case "$version" in
  regcm47)
    exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin/regcmMPICN_CNDV_CLM45
    ;;
  regcm5)
    exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv/install/bin/regcmMPICN_CNDV_CLM45
    ;;
  *)
    printf 'invalid VERSION=%s\n' "$version" >&2
    exit 2
    ;;
esac
case "$phase" in
  startup|daily) ;;
  *)
    printf 'invalid PHASE=%s\n' "$phase" >&2
    exit 2
    ;;
esac

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
namelist="$root/${version}_1979_${phase}.in"
output="$root/${version}_${phase}/output"

cd "$root"
test -x "$exe"
test -s "$namelist"
test -d "$output"
test -z "$(find "$output" -maxdepth 1 -type f -print -quit)"

date -u '+UTC_START=%Y-%m-%dT%H:%M:%SZ'
printf 'VERSION=%s PHASE=%s MPI_TASKS=%s HOST=%s\n' \
  "$version" "$phase" "${SLURM_NTASKS:-128}" "$(hostname)"
sha256sum "$exe" "$namelist"
mpirun -n 128 "$exe" "$namelist"
date -u '+UTC_END=%Y-%m-%dT%H:%M:%SZ'
printf 'PRECISE_ONSET_RUN_OK version=%s phase=%s\n' "$version" "$phase"

