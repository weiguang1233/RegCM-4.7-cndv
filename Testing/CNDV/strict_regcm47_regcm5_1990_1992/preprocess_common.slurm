#!/bin/bash
#SBATCH -J cndvab_pre
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

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_strict_compare_regcm47_regcm5_1990_1992
input="$root/common_input"
bin=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin
cd "$root"

test -d "$input"
test -x "$bin/terrainCN_CNDV_CLM45"
test -x "$bin/mksurfdataCN_CNDV_CLM45"
test -x "$bin/sstCN_CNDV_CLM45"
test -x "$bin/icbcCN_CNDV_CLM45"

"$bin/terrainCN_CNDV_CLM45" common_preprocess_regcm47.in
./add_areacella_compat.sh \
  "$input/cndvab_DOMAIN000.nc" \
  "$root/preprocess_output/cndvab_DOMAIN000.pre_areacella.nc"
"$bin/mksurfdataCN_CNDV_CLM45" common_preprocess_regcm47.in
"$bin/sstCN_CNDV_CLM45" common_preprocess_regcm47.in
"$bin/icbcCN_CNDV_CLM45" common_preprocess_regcm47.in

test -s "$input/cndvab_DOMAIN000.nc"
test -s "$input/cndvab_CLM45_surface.nc"
test -s "$input/cndvab_SST.nc"
test -s "$input/cndvab_ICBC.1990010100.nc"
test -s "$input/cndvab_ICBC.1992010100.nc"

count=0
while IFS= read -r -d '' file; do
  test -s "$file"
  ncdump -h "$file" >/dev/null
  count=$((count + 1))
done < <(find "$input" -maxdepth 1 -type f -name '*.nc' -print0)
test "$count" -ge 28

find "$input" -maxdepth 1 -type f -print0 \
  | LC_ALL=C sort -z \
  | xargs -0 sha256sum > "$root/analysis/common_input_sha256.txt"
sha256sum "$root/preprocess_output/cndvab_DOMAIN000.pre_areacella.nc" \
  > "$root/analysis/original_regcm47_domain_sha256.txt"
printf 'COMMON_INPUT_NETCDF_OK=%d\n' "$count"
printf 'COMMON_INPUT_PREPROCESS_OK\n'
