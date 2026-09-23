#!/bin/bash
set -euo pipefail

root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_cn_followon_1980_1987
cd "$root"

build47=$(sbatch --parsable build_regcm47_histfix.slurm)
printf 'REGCM47_BUILD_JOB=%s\n' "$build47"

smoke47=$(sbatch --parsable --dependency="afterok:${build47}" \
  --job-name=cn_regcm47_exact_smoke \
  --output=regcm47_exact_smoke/logs/run.%j.out \
  --error=regcm47_exact_smoke/logs/run.%j.err \
  --export=ALL,VERSION=regcm47,MODE=exact_smoke,EXE_OVERRIDE=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin/regcmMPICN_CNDV_CLM45_histfix run_case.slurm)
smoke5=$(sbatch --parsable \
  --job-name=cn_regcm5_exact_smoke \
  --output=regcm5_exact_smoke/logs/run.%j.out \
  --error=regcm5_exact_smoke/logs/run.%j.err \
  --export=ALL,VERSION=regcm5,MODE=exact_smoke run_case.slurm)
probe47=$(sbatch --parsable --dependency="afterok:${build47}" \
  --job-name=cn_regcm47_histfix_probe \
  --output=regcm47_histfix_probe/logs/run.%j.out \
  --error=regcm47_histfix_probe/logs/run.%j.err \
  --export=ALL,VERSION=regcm47,MODE=histfix_probe,EXE_OVERRIDE=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin/regcmMPICN_CNDV_CLM45_histfix run_case.slurm)
printf 'SMOKE_JOB version=regcm47 mode=exact_smoke id=%s\n' "$smoke47"
printf 'SMOKE_JOB version=regcm5 mode=exact_smoke id=%s\n' "$smoke5"
printf 'SMOKE_JOB version=regcm47 mode=histfix_probe id=%s\n' "$probe47"

gate=$(sbatch --parsable --dependency="afterok:${smoke47}:${smoke5}:${probe47}" validate_smoke.slurm)
printf 'SMOKE_GATE_JOB=%s\n' "$gate"

full47=$(sbatch --parsable --dependency="afterok:${gate}" \
  --job-name=cn80_87_47 \
  --output=regcm47_full_fixed/logs/run.%j.out \
  --error=regcm47_full_fixed/logs/run.%j.err \
  --export=ALL,VERSION=regcm47,MODE=full_fixed,EXE_OVERRIDE=/public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin/regcmMPICN_CNDV_CLM45_histfix run_case.slurm)
full5=$(sbatch --parsable --dependency="afterok:${gate}" \
  --job-name=cn80_87_5 \
  --output=regcm5_full/logs/run.%j.out \
  --error=regcm5_full/logs/run.%j.err \
  --export=ALL,VERSION=regcm5,MODE=full run_case.slurm)
printf 'FULL_REGCM47_JOB=%s\n' "$full47"
printf 'FULL_REGCM5_JOB=%s\n' "$full5"

analysis=$(sbatch --parsable --dependency="afterok:${full47}:${full5}" analyze_monthly_cn.slurm)
printf 'ANALYSIS_JOB=%s\n' "$analysis"

printf '%s\n' "$build47 $smoke47 $smoke5 $probe47 $gate $full47 $full5 $analysis" > analysis/submitted_job_ids.txt
