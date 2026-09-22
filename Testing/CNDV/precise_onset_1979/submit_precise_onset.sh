#!/bin/bash
set -euo pipefail

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
cd "$root"

startup47=$(sbatch --parsable --job-name=c79s47 \
  --output=regcm47_startup/logs/run.%j.out \
  --error=regcm47_startup/logs/run.%j.err \
  --export=ALL,VERSION=regcm47,PHASE=startup run_case.slurm)
startup5=$(sbatch --parsable --job-name=c79s5 \
  --output=regcm5_startup/logs/run.%j.out \
  --error=regcm5_startup/logs/run.%j.err \
  --export=ALL,VERSION=regcm5,PHASE=startup run_case.slurm)

gate=$(sbatch --parsable --dependency="afterok:${startup47}:${startup5}" \
  validate_startup.slurm)

daily47=$(sbatch --parsable --dependency="afterok:${gate}" \
  --job-name=c79d47 \
  --output=regcm47_daily/logs/run.%j.out \
  --error=regcm47_daily/logs/run.%j.err \
  --export=ALL,VERSION=regcm47,PHASE=daily run_case.slurm)
daily5=$(sbatch --parsable --dependency="afterok:${gate}" \
  --job-name=c79d5 \
  --output=regcm5_daily/logs/run.%j.out \
  --error=regcm5_daily/logs/run.%j.err \
  --export=ALL,VERSION=regcm5,PHASE=daily run_case.slurm)

analysis=$(sbatch --parsable --dependency="afterok:${daily47}:${daily5}" \
  analyze_precise_onset.slurm)

printf 'STARTUP_REGCM47_JOB=%s\n' "$startup47"
printf 'STARTUP_REGCM5_JOB=%s\n' "$startup5"
printf 'STARTUP_GATE_JOB=%s\n' "$gate"
printf 'DAILY_REGCM47_JOB=%s\n' "$daily47"
printf 'DAILY_REGCM5_JOB=%s\n' "$daily5"
printf 'FINAL_ANALYSIS_JOB=%s\n' "$analysis"
printf '%s\n' "$startup47 $startup5 $gate $daily47 $daily5 $analysis" \
  > analysis/submitted_job_ids.txt

