#!/usr/bin/env python3
"""Analyze controlled one-day and one-month cold-start NDEP experiments."""
import argparse
import csv
import json
import math
import tempfile
import hashlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import analyze_precise_onset as onset

CASES = ['regcm47_baseline','regcm47_ndepfix','regcm5_baseline','regcm5_ndepfix','regcm5_lai47','regcm5_lai47_ndepfix']
SECONDS_PER_YEAR=86400.*365.2422


def restart_mineral_n(path):
    fields=('sminn','cols1d_wtxy','cols1d_ityplun')
    with tempfile.TemporaryDirectory(prefix='ndep_restart_') as name:
        data=onset.read_subset(path,fields,Path(name))
    variables=data['variables']
    values=onset.finite(variables['sminn']['data'])
    weights=onset.finite(variables['cols1d_wtxy']['data'])
    landunit=np.asarray(variables['cols1d_ityplun']['data'])
    selected=np.isin(landunit,[1,8]) & np.isfinite(weights) & (weights>0.)
    assert np.all(np.isfinite(values[selected])),('nonfinite soil mineral N',path)
    count=int(data['dimensions']['gridcell'])
    return {
        'soil_column_contribution_gN_m2':float(np.sum(values[selected]*weights[selected])/count),
        'soil_column_min_gN_m2':float(np.min(values[selected])),
        'soil_column_max_gN_m2':float(np.max(values[selected])),
        'source_file':path.name,
        'selection':'soil/crop landunit (1/8), positive column weight; gridcell-normalized contribution',
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    root=args.root
    analysis=root/'analysis'
    analysis.mkdir(exist_ok=True)
    surface=Path('/public/home/elpt_2024_000795/workdir_for_RCM/cndv_maxrun_regcm47_regcm5_1979_2016/common_input/cndvab_CLM45_surface.nc')
    with tempfile.TemporaryDirectory(prefix='ndep_surface_') as name:
        surface_data=onset.read_subset(surface,('NDEP',),Path(name))
    dep=surface_data['variables']['NDEP']
    assert dep['units']=='g(N)/m2/yr',dep['units']
    assert surface_data['dimensions']['gridcell']==onset.GRID_COUNT
    expected_ndep=float(np.mean(dep['data']))
    result={'generated_utc':datetime.now(timezone.utc).isoformat(),'calendar_days_per_year':365.2422,'phases':{},
        'surface_input':{'file':str(surface),'units':dep['units'],'gridcells':onset.GRID_COUNT,
          'ndep_min':float(np.min(dep['data'])),'ndep_mean':expected_ndep,'ndep_max':float(np.max(dep['data'])),
          'sha256':hashlib.sha256(surface.read_bytes()).hexdigest()}}
    rows_by_phase={}
    history_units={}
    checks={}
    for phase,count,hours in [('startup',24,1),('month',31,24)]:
        rows_by_phase[phase]={}
        result['phases'][phase]={}
        for case in CASES:
            rows,units=onset.load_phase(root,case,phase)
            history_units[f'{case}_{phase}']=units
            assert len(rows)==count,(case,phase,len(rows))
            stamps=[datetime.fromisoformat(r['datetime']) for r in rows]
            expected_stamps=[datetime(1979,1,1)+timedelta(hours=hours*(i+1)) for i in range(count)]
            assert stamps==expected_stamps,(case,phase,'timestamps')
            fixed='ndepfix' in case
            expected_rate=expected_ndep/(SECONDS_PER_YEAR if fixed else 1.)
            np.testing.assert_allclose([r['NDEP_TO_SMINN'] for r in rows],expected_rate,rtol=2.e-6,atol=1.e-14)
            closure=max(abs(r['NPP_BALANCE_ERROR']) for r in rows)
            assert closure<1.e-10,(case,phase,'NPP closure',closure)
            last=rows[-1]
            result['phases'][phase][case]={
                'records':len(rows),'final_datetime':last['datetime'],
                'ndep_rate_gN_m2_s':float(np.mean([r['NDEP_TO_SMINN'] for r in rows])),
                'cumulative_ndep_gN_m2':float(sum(r['NDEP_TO_SMINN']*hours*3600. for r in rows)),
                'final_sminn_history':last['SMINN'],
                'min_FPG':min(r['FPG'] for r in rows),
                'max_abs_DOWNREG':max(abs(r['DOWNREG']) for r in rows),
                'max_abs_NPP_closure':closure,
                **{key:last[key] for key in ('CUM_GPP','CUM_NPP','TOTVEGC','TOTVEGN','LEAFC','TLAI','BTRAN','SOILWATER_10CM')},
            }
            final_date='1979010200' if phase=='startup' else '1979020100'
            restart=root/f'{case}_{phase}'/'output'/f'cndvab.clm.regcm.r.{final_date}.nc'
            result['phases'][phase][case]['restart_mineral_n']=restart_mineral_n(restart)
            rows_by_phase[phase][case]=rows
        onset.write_wide(analysis/f'{phase}_regional_timeseries.csv',rows_by_phase[phase])
        comparisons=[]
        for a,b in [('regcm47_baseline','regcm47_ndepfix'),('regcm5_baseline','regcm5_ndepfix'),('regcm5_lai47','regcm5_lai47_ndepfix'),('regcm47_ndepfix','regcm5_ndepfix'),('regcm5_ndepfix','regcm5_lai47_ndepfix')]:
            for row in onset.compare_rows(rows_by_phase[phase][a],rows_by_phase[phase][b]):
                comparisons.append({'reference':a,'candidate':b,
                    'datetime':row['datetime'],'metric':row['metric'],
                    'reference_value':row['regcm47'],'candidate_value':row['regcm5'],
                    'candidate_minus_reference':row['regcm5_minus_regcm47'],
                    'candidate_over_reference_pct':row['regcm5_over_regcm47_pct'],
                    'absolute_relative_difference':row['absolute_relative_difference']})
        onset.write_rows(analysis/f'{phase}_comparison_long.csv',comparisons)
    checks['record_counts_and_timestamps']=True
    checks['ndep_rate_matches_surface_and_calendar']=True
    checks['npp_closure']=True
    result['checks']=checks
    result['pass']=True
    (analysis/'history_units.json').write_text(json.dumps(history_units,indent=2)+'\n')
    (analysis/'ndep_validation_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    subprocess.run([sys.executable, str(Path(__file__).with_name('verify_output_independent.py')), str(root)],check=True)
    print('NDEP_EXPERIMENT_ANALYSIS_PASS')

if __name__=='__main__':
    main()
