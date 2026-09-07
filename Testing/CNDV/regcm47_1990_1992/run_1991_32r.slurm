#!/bin/bash
#SBATCH -J c47yr91_run
#SBATCH -p cpu_parallel
#SBATCH -N 1
#SBATCH -n 32
#SBATCH --ntasks-per-node=32
#SBATCH -t 04:00:00
#SBATCH -o logs/run.%j.out
#SBATCH -e logs/run.%j.err

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

run=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_year2_regcm47_1991
exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin/regcmMPICN_CNDV_CLM45
cd "$run"

test -x "$exe"
test -s input/c47yr1990_DOMAIN000.nc
test -s input/c47yr1990_CLM45_surface.nc
test -s input/c47yr1990_SST.nc
test -s input/c47yr1990_ICBC.1991010100.nc
test -s output/c47yr1990_SAV.1991010100.nc
test -s output/c47yr1990.clm.regcm.r.1991010100.nc
test -s output/c47yr1990.clm.regcm.rh0.1991010100.nc

mpirun -n "${SLURM_NTASKS:-32}" "$exe" cndv_year2_1991.in
printf 'MODEL_YEAR2_RUN_OK\n'
