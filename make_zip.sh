#!/usr/bin/env bash
# Build a QGIS-ready plugin ZIP from the current HEAD.
# Usage: ./make_zip.sh
# Output: dist/processing_richdem-<version>.zip
set -e

VERSION=$(grep '^version=' metadata.txt | cut -d= -f2)
PLUGIN=processing_richdem
OUTDIR=dist
OUTFILE="${OUTDIR}/${PLUGIN}-${VERSION}.zip"

mkdir -p "${OUTDIR}"
git archive --prefix="${PLUGIN}/" HEAD --output="${OUTFILE}"
echo "Created ${OUTFILE}"
