#!/bin/bash
#SBATCH -J cndv_lai_build
#SBATCH -p cpu_single
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 16
#SBATCH -t 01:00:00

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

model_root=/public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv
source_root="$model_root/source"
source_file="$source_root/Main/clmlib/clm4.5/mod_clm_cnvegstructupdate.F90"
test_root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
patch_file="$test_root/regcm5_legacy_lai.patch"
experiment_root=/public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv-experiments/legacy-lai47
experiment_binary="$experiment_root/bin/regcmMPICN_CNDV_CLM45_lai47"
baseline_binary="$model_root/install/bin/regcmMPICN_CNDV_CLM45"
expected_source_sha=64f7ba79f20531d4023a36b237e9282661b782a765f712232252c475487d238f
expected_baseline_sha=$(sha256sum "$baseline_binary" | awk '{print $1}')
backup=$(mktemp /tmp/mod_clm_cnvegstructupdate.XXXXXX.F90)

restore_baseline() {
  cp -p "$backup" "$source_file"
  touch "$source_file"
  make -C "$source_root" -j "${SLURM_CPUS_PER_TASK:-16}"
  rm -f "$backup"
}
trap restore_baseline EXIT

test "$(sha256sum "$source_file" | awk '{print $1}')" = "$expected_source_sha"
test -s "$patch_file"
cp -p "$source_file" "$backup"

patch --batch --forward -p1 -d "$source_root" < "$patch_file"
patched_source_sha=$(sha256sum "$source_file" | awk '{print $1}')
test "$patched_source_sha" != "$expected_source_sha"
make -C "$source_root" -j "${SLURM_CPUS_PER_TASK:-16}"

mkdir -p "$experiment_root/bin"
cp -p "$source_root/Main/regcm" "$experiment_binary"
chmod 755 "$experiment_binary"
sha256sum "$patch_file" "$source_file" "$experiment_binary" \
  > "$experiment_root/build_sha256.txt"
{
  printf 'BASELINE_SOURCE_SHA256=%s\n' "$expected_source_sha"
  printf 'PATCHED_SOURCE_SHA256=%s\n' "$patched_source_sha"
  printf 'BASELINE_BINARY_SHA256=%s\n' "$expected_baseline_sha"
  printf 'BUILD_UTC=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'BUILD_JOB=%s\n' "${SLURM_JOB_ID:-unknown}"
} > "$experiment_root/build_metadata.txt"

restore_baseline
trap - EXIT
test "$(sha256sum "$source_file" | awk '{print $1}')" = "$expected_source_sha"
test "$(sha256sum "$baseline_binary" | awk '{print $1}')" = "$expected_baseline_sha"
printf 'LAI_ABLATION_BUILD_OK binary=%s\n' "$experiment_binary"
