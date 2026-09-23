#!/bin/bash
#SBATCH -J build47_histfix
#SBATCH -p cpu_single
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH -t 01:00:00
#SBATCH -o logs/build47_histfix.%j.out
#SBATCH -e logs/build47_histfix.%j.err

set -euo pipefail
export LANG=C
export LC_ALL=C
export OMP_NUM_THREADS=1

module purge
module load compiler/intel/2021.3.0
module load mpi/intelmpi/2021.3.0
module load mathlib/hdf5/intel/1.8.20
module load mathlib/netcdf/intel/4.4.1
module load mathlib/zlib/intel/1.2.11
hash -r

base=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv
source_file="$base/source/Main/clmlib/clm4.5/mod_clm_histfile.F90"
binary="$base/source/Main/regcm"
target="$base/install/bin/regcmMPICN_CNDV_CLM45_histfix"

grep -q 'if ( .not. if_stop ) then' "$source_file"
grep -q 'periodic model restart can close the history file' "$source_file"
cd "$base/source"
# RegCM 4.7's generated Makefiles do not encode every Fortran-module
# dependency.  A parallel rebuild can therefore compile a consumer before
# its updated .mod file exists.  Keep this targeted rebuild serial.
make -j 1
test -x "$binary"
cp -p "$binary" "$target"
chmod 755 "$target"
sha256sum "$source_file" "$target"
printf 'REGCM47_HISTORY_REOPEN_FIX_BUILD_OK=%s\n' "$target"
