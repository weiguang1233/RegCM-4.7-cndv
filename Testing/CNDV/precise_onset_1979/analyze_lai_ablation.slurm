#!/bin/bash
#SBATCH -J cndv_lai_ana
#SBATCH -p cpu_single
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH -t 01:00:00

set -euo pipefail
export LANG=C
export LC_ALL=C
module purge
module load mathlib/netcdf/intel/4.4.1
module load mathlib/hdf5/intel/1.8.20
module load mathlib/zlib/intel/1.2.11
cd /public/home/elpt_2024_000795/workdir_for_RCM/cndv_precise_onset_1979
/public/home/elpt_2024_000795/anaconda3/bin/python3 analyze_lai_ablation.py
