#!/bin/bash
#SBATCH -J cndv_ndep_build
#SBATCH -p cpu_single
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH -t 01:00:00
#SBATCH -o logs/build.%j.out
#SBATCH -e logs/build.%j.err

set -euo pipefail
export LANG=C LC_ALL=C OMP_NUM_THREADS=1
module purge
module load compiler/intel/2021.3.0 mpi/intelmpi/2021.3.0
module load mathlib/hdf5/intel/1.8.20 mathlib/netcdf/intel/4.4.1 mathlib/zlib/intel/1.2.11
hash -r

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_ndep_unit_validation_1979
version=${VERSION:?}
case "$version" in
  regcm47) model=RegCM-4.7-cndv ;;
  regcm5) model=RegCM5-cndv ;;
  *) exit 2 ;;
esac
baseline=/public/home/elpt_2024_000795/packages/RegCM/$model/source
experiment="$root/build/$version"
test ! -e "$experiment"
mkdir -p "$experiment" "$root/bin"
# Copy the configured build with independent objects and generated Makefiles.
rsync -a --exclude=.git "$baseline/" "$experiment/"
while IFS= read -r makefile; do
  sed -i "s|$baseline|$experiment|g" "$makefile"
done < <(find "$experiment" -type f \( -name Makefile -o -name config.status -o -name makeinc \))
patch --batch --forward -p1 -d "$experiment" < "$root/${version}_ndep_units.patch"
make -C "$experiment" -j 1
test -x "$experiment/Main/regcm"
cp -p "$experiment/Main/regcm" "$root/bin/${version}_ndepfix"
sha256sum "$experiment/Main/clmlib/clm4.5/mod_clm_cnndynamics.F90" \
  "$root/bin/${version}_ndepfix" > "$root/analysis/${version}_build_sha256.txt"
if [ "$version" = regcm5 ]; then
  patch --batch --forward -p1 -d "$experiment" < "$root/regcm5_legacy_lai.patch"
  make -C "$experiment" -j 1
  cp -p "$experiment/Main/regcm" "$root/bin/regcm5_lai47_ndepfix"
  sha256sum "$experiment/Main/clmlib/clm4.5/mod_clm_cnvegstructupdate.F90" \
    "$root/bin/regcm5_lai47_ndepfix" > "$root/analysis/regcm5_lai47_build_sha256.txt"
fi
printf 'NDEP_EXPERIMENT_BUILD_OK version=%s\n' "$version"
