#!/usr/bin/env python3
"""Independent raw-NetCDF checks; deliberately do not import the onset helper."""
import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from scipy.io import netcdf_file


def open_classic(path, temporary):
    try:
        return netcdf_file(path, 'r', mmap=False)
    except TypeError:
        converted = temporary / path.name
        subprocess.run(['nccopy', '-k', '64-bit-offset', str(path), str(converted)], check=True)
        return netcdf_file(converted, 'r', mmap=False)


def valid(array):
    a = np.asarray(array, dtype=np.float64)
    return np.isfinite(a) & (np.abs(a) < 1.e19)


def grid_mean(array):
    a = np.asarray(array, dtype=np.float64).reshape(-1)
    selected = a[valid(a)]
    assert len(selected) > 0
    return math.fsum(map(float, selected)) / len(selected)


def natural_mean(dataset, variable, index, grid_count):
    var = dataset.variables[variable]
    sample = np.take(var.data, index, axis=var.dimensions.index('time'))
    weights = np.asarray(dataset.variables['pfts1d_wtgcell'].data, dtype=np.float64)
    types = np.asarray(dataset.variables['pfts1d_itypveg'].data)
    selected = (types >= 1) & (types <= 14) & valid(sample) & valid(weights)
    products = np.asarray(sample, dtype=np.float64)[selected] * weights[selected]
    return math.fsum(map(float, products)) / grid_count


def close(actual, expected):
    assert math.isfinite(actual) and math.isfinite(expected)
    assert math.isclose(actual, expected, rel_tol=2.e-11, abs_tol=1.e-12), (actual, expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root
    summary = json.loads((root / 'analysis/ndep_validation_summary.json').read_text())
    grid_count = summary['surface_input']['gridcells']
    checks = {}
    with tempfile.TemporaryDirectory(prefix='independent_ndep_') as name:
        temporary = Path(name)
        with open_classic(Path(summary['surface_input']['file']), temporary) as nc:
            surface_mean = grid_mean(nc.variables['NDEP'].data)
        close(surface_mean, summary['surface_input']['ndep_mean'])
        for phase, cases in summary['phases'].items():
            duration = 3600. if phase == 'startup' else 86400.
            for case, expected in cases.items():
                output = root / f'{case}_{phase}' / 'output'
                rates, fpg, npp = [], [], []
                for path in sorted(output.glob('*.clm.regcm.h0.*.nc')):
                    with open_classic(path, temporary) as nc:
                        for i in range(len(nc.variables['time'].data)):
                            for metric, target in [('NDEP_TO_SMINN', rates), ('FPG', fpg)]:
                                var = nc.variables[metric]
                                target.append(grid_mean(np.take(var.data, i, axis=var.dimensions.index('time'))))
                for path in sorted(output.glob('*.clm.regcm.h1.*.nc')):
                    with open_classic(path, temporary) as nc:
                        for i in range(len(nc.variables['time'].data)):
                            npp.append(natural_mean(nc, 'NPP', i, grid_count))
                state_files = sorted(output.glob('*.clm.regcm.h2.*.nc'))
                with open_classic(state_files[-1], temporary) as nc:
                    final_index = len(nc.variables['time'].data) - 1
                    states = {metric: natural_mean(nc, metric, final_index, grid_count)
                              for metric in ('TOTVEGC', 'TOTVEGN', 'LEAFC', 'TLAI')}
                assert len(rates) == len(npp) == expected['records']
                annual_seconds = 86400. * summary['calendar_days_per_year']
                expected_rate = surface_mean / annual_seconds if 'ndepfix' in case else surface_mean
                for rate in rates:
                    assert math.isclose(rate, expected_rate, rel_tol=2.e-6, abs_tol=1.e-14)
                cumulative_ndep = math.fsum(rates) * duration
                cumulative_npp = math.fsum(npp) * duration
                close(cumulative_ndep, expected['cumulative_ndep_gN_m2'])
                close(cumulative_npp, expected['CUM_NPP'])
                close(min(fpg), expected['min_FPG'])
                for metric, value in states.items():
                    close(value, expected[metric])
                restart = output / expected['restart_mineral_n']['source_file']
                with open_classic(restart, temporary) as nc:
                    n = np.asarray(nc.variables['sminn'].data, dtype=np.float64)
                    w = np.asarray(nc.variables['cols1d_wtxy'].data, dtype=np.float64)
                    t = np.asarray(nc.variables['cols1d_ityplun'].data)
                    selected = ((t == 1) | (t == 8)) & valid(n) & valid(w) & (w > 0.)
                    mineral_n = math.fsum(map(float, n[selected] * w[selected])) / grid_count
                close(mineral_n, expected['restart_mineral_n']['soil_column_contribution_gN_m2'])
                checks[f'{case}_{phase}'] = {'records': len(rates), 'cumulative_ndep_gN_m2': cumulative_ndep,
                    'cumulative_npp_gC_m2': cumulative_npp, 'final_states': states,
                    'restart_mineral_n_gN_m2': mineral_n, 'pass': True}
    result = {'method': 'Independent raw NetCDF reads, math.fsum, natural PFT 1-14 and soil/crop column weighting',
              'scope': 'All 12 runs: surface input, NDEP, FPG minimum, cumulative NPP, final C/N/LAI, restart mineral N',
              'pass': True, 'checks': checks}
    (root / 'analysis/independent_output_checks.json').write_text(json.dumps(result, indent=2) + '\n')
    print('INDEPENDENT_NDEP_OUTPUT_CHECKS_PASS')


if __name__ == '__main__':
    main()
