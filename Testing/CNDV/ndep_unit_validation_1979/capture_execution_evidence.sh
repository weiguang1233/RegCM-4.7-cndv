#!/bin/bash
# Read experiment artifacts and preserve a compact execution receipt.
set -euo pipefail
export LANG=C LC_ALL=C
root=/public/home/elpt_2024_000795/workdir_for_RCM/cndv_ndep_unit_validation_1979
cd "$root"
mkdir -p analysis/namelists
cp -p ./*.in analysis/namelists/
job_ids=$(awk -F= '{print $2}' analysis/submitted_jobs.txt | paste -sd,)
sacct -n -X -P -j "$job_ids" --format=JobID,JobName%40,Partition,State,ExitCode,Elapsed,AllocCPUS,NNodes \
  > analysis/job_status.psv
sha256sum ./*.in ./*.patch ./*.slurm ./*.py ./*.sh > analysis/final_definition_sha256.txt
sha256sum analysis/*timeseries.csv analysis/*comparison_long.csv analysis/ndep_validation_summary.json \
  analysis/history_units.json analysis/independent_output_checks.json > analysis/final_result_sha256.txt
sha256sum bin/* \
  /public/home/elpt_2024_000795/packages/RegCM/RegCM-4.7-cndv/install/bin/regcmMPICN_CNDV_CLM45_histfix \
  /public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv/install/bin/regcmMPICN_CNDV_CLM45 \
  /public/home/elpt_2024_000795/packages/RegCM/RegCM5-cndv-experiments/legacy-lai47/bin/regcmMPICN_CNDV_CLM45_lai47 \
  > analysis/all_executable_sha256.txt
{
  for version in regcm47 regcm5; do
    model=RegCM-4.7-cndv
    test "$version" = regcm5 && model=RegCM5-cndv
    baseline=/public/home/elpt_2024_000795/packages/RegCM/$model/source
    for kind in baseline candidate; do
      source_path=$baseline
      test "$kind" = candidate && source_path="$root/build/$version"
      (
        cd "$source_path"
        find . -type f \( -name '*.F90' -o -name '*.f90' -o -name '*.c' -o -name '*.h' -o -name '*.inc' \) \
          -print0 | sort -z | xargs -0 sha256sum
      ) > "$root/analysis/${version}_${kind}_source_sha256.txt"
    done
    diff -u "$root/analysis/${version}_baseline_source_sha256.txt" \
      "$root/analysis/${version}_candidate_source_sha256.txt" \
      > "$root/analysis/${version}_source_change.diff" || test "$?" -eq 1
    printf '\nVERSION=%s\n' "$version"
    sha256sum "$baseline/Main/clmlib/clm4.5/mod_clm_cnndynamics.F90"
    grep -n 'ndep_to_sminn(c) =' "$baseline/Main/clmlib/clm4.5/mod_clm_cnndynamics.F90"
    sha256sum "$root/build/$version/Main/clmlib/clm4.5/mod_clm_cnndynamics.F90"
    grep -n 'ndep_to_sminn(c) =' "$root/build/$version/Main/clmlib/clm4.5/mod_clm_cnndynamics.F90"
  done
} > analysis/baseline_and_candidate_source_receipt.txt
{
  for case_name in regcm47_baseline regcm47_ndepfix regcm5_baseline regcm5_ndepfix regcm5_lai47 regcm5_lai47_ndepfix; do
    for phase in startup month; do
      log=$(find "$root/${case_name}_${phase}/logs" -maxdepth 1 -type f -name 'run.*.out' | sort | tail -n 1)
      printf '\nCASE=%s_%s LOG=%s\n' "$case_name" "$phase" "$log"
      grep -aE 'CASE=|simulation successfully reached end|NDEP_VALIDATION_RUN_OK|^[a-f0-9]{64}  ' "$log"
    done
  done
  for job in $(awk -F= '/^BUILD_/ {print $2}' analysis/submitted_jobs.txt); do
    grep -a 'NDEP_EXPERIMENT_BUILD_OK' "logs/build.$job.out"
  done
} > analysis/run_completion_receipt.txt
printf 'NDEP_EXECUTION_EVIDENCE_CAPTURED\n'
