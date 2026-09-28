#!/usr/bin/env python3
"""Check downloaded records and derive clearly named experimental contrasts."""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def read_rows(path):
    with path.open() as file:
        return list(csv.DictReader(file))


def ratio(a, b):
    return None if abs(a) < 1.e-20 else 100. * b / a


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('results', type=Path)
    parser.add_argument('--prior-startup', type=Path)
    args = parser.parse_args()
    results = args.results
    summary = json.loads((results / 'ndep_validation_summary.json').read_text())
    independent = json.loads((results / 'independent_output_checks.json').read_text())
    assert summary['pass'] and independent['pass']
    assert len(independent['checks']) == 12
    units = json.loads((results / 'history_units.json').read_text())
    assert len(units) == 12
    jobs = []
    with (results / 'job_status.psv').open() as file:
        for row in csv.reader(file, delimiter='|'):
            if not row or not row[0]:
                continue
            assert row[3:5] == ['COMPLETED', '0:0'], row
            jobs.append(row)
    assert len(jobs) == 15
    for row in jobs:
        if row[2] == 'cpu_parallel':
            assert row[6:8] == ['128', '2'], row
    report = {'pass': True, 'completed_jobs': len(jobs), 'phases': {}, 'baseline_reproduction': {}}
    phases = {}
    for phase, count in [('startup', 24), ('month', 31)]:
        rows = read_rows(results / f'{phase}_regional_timeseries.csv')
        assert len(rows) == 6 * count
        groups = defaultdict(list)
        for row in rows:
            groups[row['version']].append(row)
        assert set(groups) == set(summary['phases'][phase])
        assert all(len(rows) == count and len({r['datetime'] for r in rows}) == count for rows in groups.values())
        phases[phase] = groups
        cases = summary['phases'][phase]
        contrasts = []
        for reference, candidate in [('regcm47_baseline', 'regcm47_ndepfix'),
                                     ('regcm5_baseline', 'regcm5_ndepfix'),
                                     ('regcm5_lai47', 'regcm5_lai47_ndepfix'),
                                     ('regcm47_ndepfix', 'regcm5_ndepfix'),
                                     ('regcm47_ndepfix', 'regcm5_lai47_ndepfix'),
                                     ('regcm5_ndepfix', 'regcm5_lai47_ndepfix')]:
            ratios = {key: ratio(cases[reference][key], cases[candidate][key])
                      for key in ('CUM_GPP', 'CUM_NPP', 'TOTVEGC', 'TOTVEGN', 'LEAFC', 'TLAI', 'BTRAN')}
            contrasts.append({'reference': reference, 'candidate': candidate,
                              'candidate_over_reference_pct': ratios})
        report['phases'][phase] = {'row_count': len(rows), 'contrasts': contrasts}
    first_hour = {}
    for case in ('regcm47_ndepfix', 'regcm5_ndepfix', 'regcm5_lai47_ndepfix'):
        first = phases['startup'][case][0]
        first_hour[case] = {'datetime': first['datetime'],
                           **{key: float(first[key]) for key in ('LEAFC', 'TOTVEGC', 'TOTVEGN', 'TLAI', 'FPG', 'SMINN')}}
    report['corrected_first_hour'] = first_hour
    if args.prior_startup:
        prior = {(r['version'], r['datetime']): r for r in read_rows(args.prior_startup)}
        for old, new in [('RegCM4.7', 'regcm47_baseline'), ('RegCM5', 'regcm5_baseline')]:
            max_abs, max_relative, comparisons = 0., 0., 0
            for row in phases['startup'][new]:
                previous = prior[(old, row['datetime'])]
                for metric in (set(row) & set(previous)) - {'datetime', 'version'}:
                    a, b = float(previous[metric]), float(row[metric])
                    if not math.isfinite(a) or not math.isfinite(b):
                        continue
                    assert math.isclose(a, b, rel_tol=1.e-8, abs_tol=1.e-10), (old, metric, row['datetime'], a, b)
                    max_abs = max(max_abs, abs(a-b))
                    if abs(a) > 1.e-10:
                        max_relative = max(max_relative, abs(a-b)/abs(a))
                    comparisons += 1
            report['baseline_reproduction'][old] = {'checked_values': comparisons,
                'max_absolute_difference': max_abs, 'max_relative_difference_nonzero': max_relative, 'pass': True}
    (results / 'archive_audit_summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
