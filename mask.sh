#!/bin/bash
set -o errexit
set -o pipefail
set -o nounset

IN_FA=$1
OUT_FILE=$2
OUT_FA=$3

MYTMP=$(mktemp -d)

# the outfiles have multiple headers, fix
HEADER_1="SW.*perc.*query.*position in query"
HEADER_2="score.*div.* del.*ins.*sequence.*begin.*end.*repeat"
HEADER_3="There were no repetitive sequences"
grep -Ev "${HEADER_1}" "${OUT_FILE}" | grep -Ev "${HEADER_2}" | grep -Ev "^$" | grep -Ev "${HEADER_3}" | awk '{ $6 = $6 - 1; $7 = $7 - 1; print $0 }' >"${MYTMP}/mask_noHeaders.out"

PSEUDO_HEADER="SW  perc perc"
echo "   $PSEUDO_HEADER" > "${MYTMP}/mask.out"
echo "   $PSEUDO_HEADER" > "${MYTMP}/mask.out"
echo "   $PSEUDO_HEADER" > "${MYTMP}/mask.out"
cat "${MYTMP}/mask_noHeaders.out" >> "${MYTMP}/mask.out"

# mask
echo "${MYTMP}/mask.out"
faToTwoBit "${IN_FA}" "${MYTMP}/in.2bit"
twoBitMask -type=.out "${MYTMP}/in.2bit" "${MYTMP}/mask.out" "${MYTMP}/mask.2bit"
twoBitToFa "${MYTMP}/mask.2bit" "$OUT_FA"

# cleanup
rm -fr "${MYTMP}"
