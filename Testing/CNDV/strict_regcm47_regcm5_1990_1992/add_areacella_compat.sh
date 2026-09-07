#!/bin/bash
set -euo pipefail

if test "$#" -ne 2; then
  printf 'usage: %s DOMAIN_FILE ORIGINAL_BACKUP\n' "$0" >&2
  exit 2
fi

domain=$1
backup=$2
ncap2=/public/software/apps/nco-4.8.1/intel/bin/ncap2

test -s "$domain"
test -x "$ncap2"
test ! -e "$backup"

mv "$domain" "$backup"
"$ncap2" -O -s \
  'areacella=(60000.0*60000.0)/(xmap*xmap);areacella@long_name="Atmosphere Grid-Cell Area";areacella@standard_name="cell_area";areacella@units="m2";areacella@coordinates="xlat xlon";areacella@grid_mapping="crs"' \
  "$backup" "$domain"

test -s "$domain"
ncdump -h "$domain" | grep 'double areacella(iy, jx)' >/dev/null
printf 'AREACELLA_COMPAT_OK formula=(60000_m/xmap)^2\n'
