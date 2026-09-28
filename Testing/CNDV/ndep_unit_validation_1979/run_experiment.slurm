#!/bin/bash
#SBATCH -J cndv_ndep_test
#SBATCH -p cpu_parallel
#SBATCH -N 2
#SBATCH -n 128
#SBATCH --ntasks-per-node=64
#SBATCH -t 01:00:00

set -euo pipefail
export LANG=C LC_ALL=C OMP_NUM_THREADS=1
ulimit -s unlimited
module purge
module load compiler/intel/2021.3.0 mpi/intelmpi/2021.3.0
module load mathlib/hdf5/intel/1.8.20 mathlib/netcdf/intel/4.4.1 mathlib/zlib/intel/1.2.11
hash -r
root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_ndep_unit_validation_1979
version=${VERSION:?}
variant=${VARIANT:?}
phase=${PHASE:?}
case "$version:$variant" in
  regcm47:baseline) exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin/regcmMPICN_CNDV_CLM45_histfix ;;
  regcm5:baseline) exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv/install/bin/regcmMPICN_CNDV_CLM45 ;;
  regcm5:lai47) exe=/public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv-experiments/legacy-lai47/bin/regcmMPICN_CNDV_CLM45_lai47 ;;
  regcm47:ndepfix|regcm5:ndepfix|regcm5:lai47_ndepfix) exe="$root/bin/${version}_${variant}" ;;
  *) exit 2 ;;
esac
case "$phase" in
  startup) final=1979010200 ;;
  month) final=1979020100 ;;
  *) exit 2 ;;
esac
case_dir="$root/${version}_${variant}_${phase}"
test -x "$exe"
test -z "$(find "$case_dir/output" -maxdepth 1 -type f -print -quit)"
cd "$root"
printf 'CASE=%s_%s_%s\n' "$version" "$variant" "$phase"
sha256sum "$exe" "${version}_${variant}_${phase}.in"
mpirun -n 128 "$exe" "${version}_${variant}_${phase}.in"
test -s "$case_dir/output/cndvab.clm.regcm.r.${final}.nc"
test -s "$case_dir/output/cndvab_SAV.${final}.nc"
printf 'NDEP_VALIDATION_RUN_OK version=%s variant=%s phase=%s\n' "$version" "$variant" "$phase"
