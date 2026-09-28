#!/bin/bash
set -euo pipefail
root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_ndep_unit_validation_1979
cd "$root"
build47=${BUILD47:-$(sbatch --parsable --export=ALL,VERSION=regcm47 build_experiment.slurm)}
build5=${BUILD5:-$(sbatch --parsable --export=ALL,VERSION=regcm5 build_experiment.slurm)}
printf 'BUILD_REGCM47=%s\nBUILD_REGCM5=%s\n' "$build47" "$build5" | tee analysis/submitted_jobs.txt
jobs=()
for version in regcm47 regcm5; do
  variants=(baseline ndepfix)
  test "$version" = regcm5 && variants+=(lai47 lai47_ndepfix)
  for variant in "${variants[@]}"; do
    for phase in startup month; do
      case_name="${version}_${variant}_${phase}"
      options=(--job-name="$case_name" --output="$case_name/logs/run.%j.out" \
        --error="$case_name/logs/run.%j.err" --export="ALL,VERSION=$version,VARIANT=$variant,PHASE=$phase")
      if [[ "$variant" == *ndepfix ]]; then
        build=$build47
        test "$version" = regcm5 && build=$build5
        options+=(--dependency="afterok:$build")
      fi
      job=$(sbatch --parsable "${options[@]}" run_experiment.slurm)
      jobs+=("$job")
      printf '%s=%s\n' "$case_name" "$job" | tee -a analysis/submitted_jobs.txt
    done
  done
done
dependency=$(IFS=:; printf '%s' "${jobs[*]}")
analysis=$(sbatch --parsable --dependency="afterok:$dependency" analyze_experiments.slurm)
printf 'ANALYSIS=%s\n' "$analysis" | tee -a analysis/submitted_jobs.txt
