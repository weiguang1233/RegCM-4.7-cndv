#!/bin/bash
#SBATCH -J c47yr90_pre
#SBATCH -p debug
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 01:30:00
#SBATCH -o logs/preprocess.%j.out
#SBATCH -e logs/preprocess.%j.err

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

run=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_crossyear_regcm47_1990
bin=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin
cd "$run"

"$bin/terrainCN_CNDV_CLM45" cndv_crossyear_1990.in
"$bin/mksurfdataCN_CNDV_CLM45" cndv_crossyear_1990.in
"$bin/sstCN_CNDV_CLM45" cndv_crossyear_1990.in
"$bin/icbcCN_CNDV_CLM45" cndv_crossyear_1990.in

count=0
for file in input/*.nc; do
  test -s "$file"
  ncdump -h "$file" >/dev/null
  count=$((count + 1))
done
printf 'PREPROCESS_NETCDF_OK=%d\n' "$count"
printf 'PREPROCESS_OK\n'
