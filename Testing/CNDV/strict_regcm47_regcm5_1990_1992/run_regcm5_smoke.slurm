#!/bin/bash
#SBATCH -J cndvab_5s
#SBATCH -p debug
#SBATCH -N 1
#SBATCH -n 4
#SBATCH --ntasks-per-node=4
#SBATCH -t 00:30:00
#SBATCH -o regcm5_smoke/logs/run.%j.out
#SBATCH -e regcm5_smoke/logs/run.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C
export OMP_NUM_THREADS=1
ulimit -s unlimited

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
test -s common_input/cndvab_DOMAIN000.nc
test -s common_input/cndvab_CLM45_surface.nc
test -s common_input/cndvab_SST.nc
test -s common_input/cndvab_ICBC.1990010100.nc
mpirun -n 4 "$exe" regcm5_smoke.in
printf 'REGCM5_COMMON_INPUT_SMOKE_OK\n'
