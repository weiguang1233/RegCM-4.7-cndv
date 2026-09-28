#!/usr/bin/env python3
"""Plot archived controlled NDEP experiments using the source-backed CSVs."""
import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

CASES={
 'regcm47_baseline':('RegCM4.7 baseline','#1565c0','-'),
 'regcm47_ndepfix':('RegCM4.7 NDEP fixed','#1565c0','--'),
 'regcm5_baseline':('RegCM5 baseline','#c62828','-'),
 'regcm5_ndepfix':('RegCM5 NDEP fixed','#c62828','--'),
 'regcm5_lai47':('RegCM5 legacy LAI','#388e3c','-'),
 'regcm5_lai47_ndepfix':('RegCM5 legacy LAI + NDEP fixed','#388e3c','--'),
}

def main():
 p=argparse.ArgumentParser()
 p.add_argument('results',type=Path)
 args=p.parse_args()
 for phase in ['startup','month']:
  groups=defaultdict(list)
  with (args.results/f'{phase}_regional_timeseries.csv').open() as f:
   for r in csv.DictReader(f): groups[r['version']].append(r)
  units=json.loads((args.results/'history_units.json').read_text())
  sminn_unit=units[f'regcm47_baseline_{phase}']['SMINN']
  assert all(u['SMINN']==sminn_unit for u in units.values())
  metrics=[('SMINN',f'History mineral N ({sminn_unit}; symlog)'),('FPG','N demand satisfaction (FPG)'),
   ('CUM_NPP','Cumulative NPP (gC m$^{-2}$)'),('TOTVEGC','Vegetation C (gC m$^{-2}$)'),
   ('TOTVEGN','Vegetation N (gN m$^{-2}$)'),('TLAI','Leaf area index (m$^2$ m$^{-2}$)')]
  fig,axes=plt.subplots(2,3,figsize=(16,9),layout='constrained')
  for ax,(metric,label) in zip(axes.flat,metrics):
   for case,rows in groups.items():
    name,color,style=CASES[case]
    x=[datetime.fromisoformat(r['datetime']) for r in rows]
    marker='o' if case.startswith('regcm47') else '^' if 'lai47' in case else 's'
    ax.plot(x,[float(r[metric]) for r in rows],label=name,color=color,linestyle=style,linewidth=1.8,
     marker=marker,markevery=6,markersize=3,markerfacecolor='none')
   ax.set_ylabel(label)
   if metric=='SMINN': ax.set_yscale('symlog',linthresh=1.e-4)
   ax.grid(True,alpha=.25)
   ticks=[x[0],*x[6:-1:6],x[-1]]
   ax.set_xticks(ticks)
   ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d\n%H:%M' if phase=='startup' else '%m-%d'))
   ax.tick_params(axis='x',labelrotation=0)
  handles,labels=axes.flat[0].get_legend_handles_labels()
  fig.legend(handles,labels,loc='outside lower center',ncol=3,fontsize=10)
  fig.suptitle(f'N deposition unit control: 1979 {phase}; identical cold-start inputs',fontsize=16)
  fig.savefig(args.results/f'{phase}_ndep_control.png',dpi=180)
  plt.close(fig)

if __name__=='__main__': main()
