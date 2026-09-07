#!/bin/bash
#SBATCH -J cndvab_5f
#SBATCH -p cpu_parallel
#SBATCH -N 1
#SBATCH -n 32
#SBATCH --ntasks-per-node=32
#SBATCH -t 04:00:00
#SBATCH -o regcm5_full/logs/run.%j.out
#SBATCH -e regcm5_full/logs/run.%j.err

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

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_strict_compare_regcm47_regcm5_1990_1992
exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv/install/bin/regcmMPICN_CNDV_CLM45
cd "$root"
test -x "$exe"
date -u '+UTC_START=%Y-%m-%dT%H:%M:%SZ'
hostname
module list
sha256sum "$exe"
sha256sum regcm5_two_year.in
mpirun -n 32 "$exe" regcm5_two_year.in
date -u '+UTC_END=%Y-%m-%dT%H:%M:%SZ'
printf 'REGCM5_STRICT_TWO_YEAR_OK\n'
