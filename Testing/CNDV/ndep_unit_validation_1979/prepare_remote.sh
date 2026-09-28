#!/bin/bash
set -euo pipefail
root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_ndep_unit_validation_1979
source_root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
mkdir -p "$root"/{analysis,logs,build,bin}
for version in regcm47 regcm5; do
  variants=(baseline ndepfix)
  test "$version" = regcm5 && variants+=(lai47 lai47_ndepfix)
  for variant in "${variants[@]}"; do
    for phase in startup month; do
      case_dir="$root/${version}_${variant}_${phase}"
      mkdir -p "$case_dir"/{output,logs}
      test -z "$(find "$case_dir/output" -maxdepth 1 -type f -print -quit)"
      nml="$root/${version}_${variant}_${phase}.in"
      source="$source_root/${version}_1979_startup.in"
      test "$phase" = month && source="$source_root/${version}_1979_daily.in"
      cp -p "$source" "$nml"
      if [ "$phase" = month ]; then
        sed -i 's/mdate2 = 1980010100/mdate2 = 1979020100/; s/savfrq = 365\./savfrq = 31./' "$nml"
      fi
      sed -i "s|$source_root/${version}_startup/output|$case_dir/output|; s|$source_root/${version}_daily/output|$case_dir/output|" "$nml"
      grep -q 'ifrest = .false.' "$nml"
      grep -q 'ichem = 0' "$nml"
      grep -q "$case_dir/output" "$nml"
    done
  done
done
sha256sum "$root"/*.in "$root"/*.patch "$root"/*.slurm "$root"/*.py \
  > "$root/analysis/test_definition_sha256.txt"
printf 'NDEP_VALIDATION_PREPARED=%s\n' "$root"
