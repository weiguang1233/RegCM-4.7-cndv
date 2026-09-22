#!/bin/bash
#SBATCH -J cndv_lai47
#SBATCH -p cpu_parallel
#SBATCH -N 2
#SBATCH -n 128
#SBATCH --ntasks-per-node=64
#SBATCH -t 01:00:00

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

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv-experiments/legacy-lai47/bin/regcmMPICN_CNDV_CLM45_lai47
namelist="$root/regcm5_lai47_1979_startup.in"
output="$root/regcm5_lai47_startup/output"

cd "$root"
test -x "$exe"
test -s "$namelist"
test -d "$output"
test -z "$(find "$output" -maxdepth 1 -type f -print -quit)"
sha256sum "$exe" "$namelist" regcm5_legacy_lai.patch
mpirun -n 128 "$exe" "$namelist"
printf 'LAI_ABLATION_RUN_OK job=%s\n' "${SLURM_JOB_ID:-unknown}"
