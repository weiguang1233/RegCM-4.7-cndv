#!/bin/bash
set -euo pipefail

source_root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_maxrun_regcm47_regcm5_1979_2016
target_root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
script_root=$(cd "$(dirname "$0")" && pwd)

test -s "$source_root/regcm47_37_year.in"
test -s "$source_root/regcm5_37_year.in"
test -d "$source_root/common_input"
if [ -d "$target_root" ] && find "$target_root" -path '*/output/*' -type f -print -quit | grep -q .; then
  printf 'refusing to overwrite existing precision-test output under %s\n' "$target_root" >&2
  exit 3
fi

mkdir -p "$target_root"/analysis "$target_root"/logs
for version in regcm47 regcm5; do
  for phase in startup daily; do
    mkdir -p "$target_root/${version}_${phase}/output" \
      "$target_root/${version}_${phase}/logs"
  done
done
mkdir -p "$target_root/regcm5_lai47_startup/output" \
  "$target_root/regcm5_lai47_startup/logs"

install_history_block() {
  local namelist=$1
  local block=$2
  sed -i \
    -e '/^[[:space:]]*hist_empty_htapes[[:space:]]*=/d' \
    -e '/^[[:space:]]*hist_nhtfrq[[:space:]]*=/d' \
    -e '/^[[:space:]]*hist_dov2xy[[:space:]]*=/d' \
    -e '/^[[:space:]]*hist_type1d_pertape[[:space:]]*=/d' \
    -e '/^[[:space:]]*hist_avgflag_pertape[[:space:]]*=/d' \
    -e '/^[[:space:]]*hist_fincl[1-6][[:space:]]*=/d' \
    "$namelist"
  sed -i "/^[[:space:]]*create_crop_landunit[[:space:]]*=[[:space:]]*\.false\.,/r $block" "$namelist"
}

for version in regcm47 regcm5; do
  source_namelist="$source_root/${version}_37_year.in"

  daily="$target_root/${version}_1979_daily.in"
  cp -p "$source_namelist" "$daily"
  sed -i \
    -e 's/mdate2 = 2016010100/mdate2 = 1980010100/' \
    -e "s|$source_root/${version}_long/output|$target_root/${version}_daily/output|" \
    "$daily"
  install_history_block "$daily" "$script_root/history_daily.nml"

  startup="$target_root/${version}_1979_startup.in"
  cp -p "$source_namelist" "$startup"
  sed -i \
    -e 's/mdate2 = 2016010100/mdate2 = 1979010200/' \
    -e 's/savfrq = 365\./savfrq = 1./' \
    -e "s|$source_root/${version}_long/output|$target_root/${version}_startup/output|" \
    "$startup"
  install_history_block "$startup" "$script_root/history_hourly.nml"
done

lai_namelist="$target_root/regcm5_lai47_1979_startup.in"
cp -p "$target_root/regcm5_1979_startup.in" "$lai_namelist"
sed -i \
  "s|$target_root/regcm5_startup/output|$target_root/regcm5_lai47_startup/output|" \
  "$lai_namelist"

for nml in "$target_root"/*.in; do
  grep -q 'mdate0 = 1979010100' "$nml"
  grep -q 'mdate1 = 1979010100' "$nml"
  grep -q 'hist_fincl2' "$nml"
  grep -q 'hist_fincl3' "$nml"
  grep -q 'create_crop_landunit = .false.' "$nml"
done
grep -q 'mdate2 = 1979010200' "$target_root"/*_startup.in
grep -q 'savfrq = 1\.' "$target_root"/*_startup.in
grep -q 'mdate2 = 1980010100' "$target_root"/*_daily.in
grep -q 'hist_nhtfrq = 1, 1, 1' "$target_root"/*_startup.in
grep -q 'hist_nhtfrq = 24, 24, 24' "$target_root"/*_daily.in
grep -q "$target_root/regcm47_startup/output" "$target_root/regcm47_1979_startup.in"
grep -q "$target_root/regcm5_startup/output" "$target_root/regcm5_1979_startup.in"
grep -q "$target_root/regcm47_daily/output" "$target_root/regcm47_1979_daily.in"
grep -q "$target_root/regcm5_daily/output" "$target_root/regcm5_1979_daily.in"
grep -q "$target_root/regcm5_lai47_startup/output" "$lai_namelist"

cp -p "$script_root"/README_ZH.md "$target_root/"
cp -p "$script_root"/prepare_remote.sh "$target_root/"
cp -p "$script_root"/history_*.nml "$target_root/"
cp -p "$script_root"/run_case.slurm "$target_root/"
cp -p "$script_root"/validate_startup.slurm "$target_root/"
cp -p "$script_root"/analyze_precise_onset.py "$target_root/"
cp -p "$script_root"/audit_precise_results.py "$target_root/"
cp -p "$script_root"/analyze_precise_onset.slurm "$target_root/"
cp -p "$script_root"/submit_precise_onset.sh "$target_root/"
cp -p "$script_root"/regcm5_legacy_lai.patch "$target_root/"
cp -p "$script_root"/build_lai_ablation.slurm "$target_root/"
cp -p "$script_root"/run_lai_ablation.slurm "$target_root/"
cp -p "$script_root"/analyze_lai_ablation.py "$target_root/"
cp -p "$script_root"/analyze_lai_ablation.slurm "$target_root/"
cp -p "$script_root"/submit_lai_ablation.sh "$target_root/"

sha256sum "$target_root"/*.in "$target_root"/*.nml "$target_root"/*.slurm \
  "$target_root"/*.py "$target_root"/*.sh "$target_root"/*.md \
  "$target_root"/*.patch \
  > "$target_root/analysis/test_definition_sha256.txt"

printf 'PRECISE_ONSET_TEST_PREPARED=%s\n' "$target_root"
