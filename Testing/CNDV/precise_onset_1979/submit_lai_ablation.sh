#!/bin/bash
set -euo pipefail

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
cd "$root"

build=$(sbatch --parsable \
  --output=logs/lai_build.%j.out \
  --error=logs/lai_build.%j.err \
  build_lai_ablation.slurm)
run=$(sbatch --parsable --dependency="afterok:${build}" \
  --output=regcm5_lai47_startup/logs/run.%j.out \
  --error=regcm5_lai47_startup/logs/run.%j.err \
  run_lai_ablation.slurm)
analysis=$(sbatch --parsable --dependency="afterok:${run}" \
  --output=logs/lai_analysis.%j.out \
  --error=logs/lai_analysis.%j.err \
  analyze_lai_ablation.slurm)

printf 'LAI_BUILD_JOB=%s\n' "$build"
printf 'LAI_RUN_JOB=%s\n' "$run"
printf 'LAI_ANALYSIS_JOB=%s\n' "$analysis"
printf '%s\n' "$build $run $analysis" > analysis/lai_ablation_job_ids.txt
