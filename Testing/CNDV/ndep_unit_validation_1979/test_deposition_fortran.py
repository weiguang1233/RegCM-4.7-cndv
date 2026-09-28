#!/usr/bin/env python3
"""Compile the actual CNNDeposition routine against a minimal state container."""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

STUBS = """
module mod_intkinds
 integer, parameter :: ik4=kind(1)
end module
module mod_realkinds
 integer, parameter :: rk8=kind(1.d0)
end module
module mod_dynparam
 real(8) :: dayspy
end module
module mod_clm_varcon
 real(8), parameter :: secspday=86400.d0
end module
module mod_clm_varctl
 logical :: ndep_nochem
end module
module mod_clm_atmlnd
 type a2l_type
   real(8), pointer :: forc_ndep(:)
 end type
 type(a2l_type) :: clm_a2l
end module
module mod_clm_type
 type cps_type
   real(8), pointer :: ndep(:)
 end type
 type cnf_type
   real(8), pointer :: ndep_to_sminn(:)
 end type
 type column_type
   integer, pointer :: gridcell(:)
   type(cps_type) :: cps
   type(cnf_type) :: cnf
 end type
 type land_type
   type(column_type) :: c
 end type
 type grid_type
   type(land_type) :: l
 end type
 type clm_type
   type(grid_type) :: g
 end type
 type(clm_type) :: clm3
end module
"""

DRIVER = """
program test
 use mod_clm_type
 use mod_clm_atmlnd
 use mod_clm_varctl
 use mod_dynparam
 use deposition_under_test
 implicit none
 integer :: i
 real(8) :: calendars(3)=[365.d0,365.2422d0,360.d0]
 allocate(clm3%g%l%c%cps%ndep(3),clm3%g%l%c%cnf%ndep_to_sminn(3))
 allocate(clm3%g%l%c%gridcell(3),clm_a2l%forc_ndep(3))
 clm3%g%l%c%cps%ndep=[0.d0,0.16808491552337634d0,1.d0]
 clm3%g%l%c%gridcell=[3,1,2]
 clm_a2l%forc_ndep=[1.d-9,2.d-9,3.d-9]
 do i=1,3
   dayspy=calendars(i)
   ndep_nochem=.true.
   call CNNDeposition(1,3)
   write(*,'(a,f10.4,3es25.16)') 'ANNUAL ',dayspy, &
     clm3%g%l%c%cnf%ndep_to_sminn*86400.d0*dayspy
   ndep_nochem=.false.
   call CNNDeposition(1,3)
   if (any(clm3%g%l%c%cnf%ndep_to_sminn /= [3.d-9,1.d-9,2.d-9])) stop 2
 end do
 print *, 'CHEMISTRY_BRANCH_UNCHANGED'
end program
"""


def exercise(source, fixed):
    content = source.read_text()
    if fixed:
        old = 'ndep_to_sminn(c) = ndep(c)'
        if content.count(old) != 1:
            raise ValueError('unexpected deposition assignment')
        content = content.replace(old, old + ' / (secspday * dayspy)')
    match = re.search(r'  subroutine CNNDeposition\(.*?  end subroutine CNNDeposition', content, re.S)
    if match is None:
        raise ValueError('CNNDeposition not found')
    unit = STUBS + '\nmodule deposition_under_test\n'
    unit += 'use mod_intkinds\nuse mod_realkinds\nuse mod_dynparam\n'
    unit += 'use mod_clm_varcon\nuse mod_clm_varctl\ncontains\n'
    unit += match.group() + '\nend module\n' + DRIVER
    with tempfile.TemporaryDirectory(prefix='cndv_ndep_test_') as name:
        root = Path(name)
        path = root / 'actual_deposition.F90'
        path.write_text(unit)
        subprocess.run(['gfortran', '-fcheck=all', '-Wall', '-o', str(root/'test'), str(path)], cwd=root, check=True, capture_output=True)
        output = subprocess.check_output([str(root/'test')], text=True)
    tests = []
    for line in output.splitlines():
        if not line.startswith('ANNUAL'):
            continue
        vals = line.split()
        days = float(vals[1])
        actual = list(map(float, vals[2:]))
        expected = [0., 0.16808491552337634, 1.]
        factor = 1. if fixed else days * 86400.
        for v, e in zip(actual, expected):
            if abs(v - e*factor) > max(1.e-13,abs(e*factor)*1.e-12):
                raise AssertionError((days, fixed, actual))
        tests.append({'days_per_year': days, 'integrated_annual_input': actual, 'input_multiplier': factor})
    assert len(tests) == 3 and 'CHEMISTRY_BRANCH_UNCHANGED' in output
    return tests


def main():
    p=argparse.ArgumentParser()
    p.add_argument('regcm47',type=Path)
    p.add_argument('regcm5',type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    result={}
    for version,path in [('RegCM4.7',args.regcm47),('RegCM5',args.regcm5)]:
        result[version]={'baseline':exercise(path,False),'fixed':exercise(path,True),
            'source_file':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'zero_input_checked':True,'chemistry_column_mapping_unchanged':True}
    result['compiler']=subprocess.check_output(['gfortran','--version'],text=True).splitlines()[0]
    result['pass']=True
    out=json.dumps(result,indent=2)+'\n'
    if args.output:
        args.output.write_text(out)
    print(out,end='')

if __name__=='__main__':
    main()
