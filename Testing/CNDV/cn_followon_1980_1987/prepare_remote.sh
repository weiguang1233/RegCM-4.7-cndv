#!/bin/bash
set -euo pipefail

source_root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
target_root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_cn_followon_1980_1987
script_root=$(cd "$(dirname "$0")" && pwd)

test -s "$source_root/regcm47_1979_daily.in"
test -s "$source_root/regcm5_1979_daily.in"

mkdir -p "$target_root"/{analysis,logs}
for version in regcm47 regcm5; do
  for mode in exact_smoke expanded_smoke full; do
    mkdir -p "$target_root/${version}_${mode}"/{output,logs}
  done
done
mkdir -p "$target_root/regcm47_full_fixed"/{output,logs}
mkdir -p "$target_root/regcm47_histfix_probe"/{output,logs}

install_monthly_cn_history() {
  local namelist=$1
  local block=$2
  local temporary
  temporary=$(mktemp "$namelist.XXXXXX")
  awk -v block="$block" '
    /^[[:space:]]*&clm_inparm/ { in_clm=1 }
    in_clm && /^[[:space:]]*hist_empty_htapes[[:space:]]*=/ {
      skipping=1
      next
    }
    skipping {
      if ($0 ~ /^[[:space:]]*\/[[:space:]]*$/) {
        while ((getline line < block) > 0) print line
        close(block)
        print
        skipping=0
        in_clm=0
      }
      next
    }
    { print }
  ' "$namelist" > "$temporary"
  mv "$temporary" "$namelist"
}

make_restart_namelist() {
  local version=$1
  local mode=$2
  local end_date=$3
  local source_namelist="$source_root/${version}_1979_daily.in"
  local target_namelist="$target_root/${version}_${mode}.in"
  local source_output="$source_root/${version}_daily/output"
  local target_output="$target_root/${version}_${mode}/output"

  cp -p "$source_namelist" "$target_namelist"
  sed -i \
    -e 's/ifrest = .false./ifrest = .true./' \
    -e 's/mdate1 = 1979010100/mdate1 = 1980010100/' \
    -e "s/mdate2 = 1980010100/mdate2 = ${end_date}/" \
    -e "s|$source_output|$target_output|" \
    "$target_namelist"

  if [ "$mode" = expanded_smoke ]; then
    install_monthly_cn_history "$target_namelist" "$script_root/history_monthly_cn.nml"
  fi

  shopt -s nullglob
  restart_files=("$source_output"/*1980010100.nc)
  shopt -u nullglob
  test "${#restart_files[@]}" -ge 5
  cp -p "${restart_files[@]}" "$target_output/"

  grep -q 'ifrest = .true.' "$target_namelist"
  grep -q 'mdate0 = 1979010100' "$target_namelist"
  grep -q 'mdate1 = 1980010100' "$target_namelist"
  grep -q "mdate2 = ${end_date}" "$target_namelist"
  grep -q "$target_output" "$target_namelist"
  test -s "$target_output/cndvab_SAV.1980010100.nc"
  test -s "$target_output/cndvab.clm.regcm.r.1980010100.nc"
  for tape in rh0 rh1 rh2; do
    test -s "$target_output/cndvab.clm.regcm.${tape}.1980010100.nc"
  done
}

for version in regcm47 regcm5; do
  make_restart_namelist "$version" exact_smoke 1980020100
  make_restart_namelist "$version" expanded_smoke 1980020100
  make_restart_namelist "$version" full 1987010100
done
make_restart_namelist regcm47 full_fixed 1987010100
make_restart_namelist regcm47 histfix_probe 1980020100

# Exercise the repaired close/reopen path every day.  This changes only the
# frequency of RegCM/CLM restart checkpoints, not the integration equations.
sed -i 's/savfrq = 365\./savfrq = 1./' "$target_root/regcm47_histfix_probe.in"
grep -q 'savfrq = 1.' "$target_root/regcm47_histfix_probe.in"

for nml in "$target_root"/*_expanded_smoke.in; do
  grep -q 'hist_nhtfrq = 0, 0, 0' "$nml"
  grep -q "'TOTECOSYSC'" "$nml"
  grep -q "'TOTECOSYSN'" "$nml"
done
for nml in "$target_root"/*_full.in; do
  grep -q 'hist_nhtfrq = 24, 24, 24' "$nml"
  if grep -q "'TOTECOSYSC'" "$nml"; then
    printf 'full continuation must preserve the original history configuration: %s\n' "$nml" >&2
    exit 4
  fi
done
grep -q 'hist_nhtfrq = 24, 24, 24' "$target_root/regcm47_full_fixed.in"
if grep -q "'TOTECOSYSC'" "$target_root/regcm47_full_fixed.in"; then
  printf 'fixed RegCM4.7 continuation must preserve the original history fields\n' >&2
  exit 5
fi

sha256sum "$target_root"/*.in "$target_root"/*.sh "$target_root"/*.slurm \
  "$target_root"/*.py "$target_root"/*.nml "$target_root"/*.md \
  > "$target_root/analysis/test_definition_sha256.txt"

printf 'CNDV_CN_FOLLOWON_PREPARED=%s\n' "$target_root"
