#!/bin/bash
set -euo pipefail
export LANG=C
export LC_ALL=C

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_strict_compare_regcm47_regcm5_1990_1992
cd "$root"

for file in \
  common_preprocess_regcm47.in \
  add_areacella_compat.sh \
  regcm47_smoke.in \
  regcm5_smoke.in \
  regcm47_two_year.in \
  regcm5_two_year.in \
  preprocess_common.slurm \
  run_regcm47_smoke.slurm \
  run_regcm5_smoke.slurm \
  validate_initial_gate.slurm \
  run_regcm47_full.slurm \
  run_regcm5_full.slurm \
  analyze_strict.slurm \
  validate_initial_gate.py \
  strict_compare_io.py \
  analyze_strict_compare.py \
  analyze_pft_change_regcm47.py \
  analyze_pft_change_regcm5.py
do
  test -s "$file"
done

mkdir -p \
  common_input \
  preprocess_output \
  regcm47_smoke/output regcm47_smoke/logs \
  regcm5_smoke/output regcm5_smoke/logs \
  regcm47_full/output regcm47_full/logs \
  regcm5_full/output regcm5_full/logs \
  analysis logs

if find common_input regcm47_smoke/output regcm5_smoke/output \
  regcm47_full/output regcm5_full/output -mindepth 1 -print -quit | grep -q .
then
  printf 'Refusing to submit: one or more input/output directories are not empty.\n' >&2
  exit 1
fi

sha256sum \
  common_preprocess_regcm47.in \
  add_areacella_compat.sh \
  regcm47_smoke.in \
  regcm5_smoke.in \
  regcm47_two_year.in \
  regcm5_two_year.in \
  preprocess_common.slurm \
  run_regcm47_smoke.slurm \
  run_regcm5_smoke.slurm \
  validate_initial_gate.slurm \
  run_regcm47_full.slurm \
  run_regcm5_full.slurm \
  analyze_strict.slurm \
  validate_initial_gate.py \
  strict_compare_io.py \
  analyze_strict_compare.py \
  > analysis/test_definition_sha256.txt

pre=$(sbatch --parsable preprocess_common.slurm)
smoke47=$(sbatch --parsable --dependency="afterok:$pre" run_regcm47_smoke.slurm)
smoke5=$(sbatch --parsable --dependency="afterok:$pre" run_regcm5_smoke.slurm)
gate=$(sbatch --parsable --dependency="afterok:$smoke47:$smoke5" validate_initial_gate.slurm)
full47=$(sbatch --parsable --dependency="afterok:$gate" run_regcm47_full.slurm)
full5=$(sbatch --parsable --dependency="afterok:$gate" run_regcm5_full.slurm)
analysis=$(sbatch --parsable --dependency="afterok:$full47:$full5" analyze_strict.slurm)

{
  printf 'preprocess=%s\n' "$pre"
  printf 'regcm47_smoke=%s\n' "$smoke47"
  printf 'regcm5_smoke=%s\n' "$smoke5"
  printf 'initial_gate=%s\n' "$gate"
  printf 'regcm47_full=%s\n' "$full47"
  printf 'regcm5_full=%s\n' "$full5"
  printf 'strict_analysis=%s\n' "$analysis"
} | tee analysis/submitted_jobs.txt
