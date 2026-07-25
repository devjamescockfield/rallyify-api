#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${PMTILES_WORK_DIR:-${ROOT_DIR}/maps/work}"
OUTPUT_DIR="${PMTILES_OUTPUT_DIR:-${ROOT_DIR}/maps/public/packages}"
PLANETILER_VERSION="0.10.2"
PLANETILER_SHA256="f310bd0413e2e4512b27f4046d418664e8e1d3bf31603c2a70e23de06c167e4d"
OSM_VERSION="2026-07-01"
OSM_SHA256="1631f148d15f64667a48da52bcc5c9985df594af0ffd625395b00b0158daa50d"
BOUNDS="-6.22,57.20,-2.65,58.87"
JVM_HEAP="${JVM_HEAP:-8g}"

PLANETILER_JAR="${WORK_DIR}/planetiler-v${PLANETILER_VERSION}.jar"
OSM_PBF="${WORK_DIR}/scotland-260701.osm.pbf"
OUTPUT="${OUTPUT_DIR}/uk-scotland-northern-highlands-${OSM_VERSION}.pmtiles"
JAVA_BIN="${JAVA_BIN:-java}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "${WORK_DIR}/sources" "${WORK_DIR}/tmp" "${OUTPUT_DIR}"

download() {
  local url="$1"
  local destination="$2"
  if [[ ! -f "${destination}" ]]; then
    curl --fail --location --retry 3 --show-error \
      --output "${destination}" "${url}"
  fi
}

verify_sha256() {
  local expected="$1"
  local file="$2"
  local actual
  actual="$(shasum -a 256 "${file}" | awk '{print $1}')"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "SHA-256 mismatch for ${file}" >&2
    echo "expected: ${expected}" >&2
    echo "actual:   ${actual}" >&2
    exit 1
  fi
}

download \
  "https://github.com/onthegomap/planetiler/releases/download/v${PLANETILER_VERSION}/planetiler.jar" \
  "${PLANETILER_JAR}"
download \
  "https://download.geofabrik.de/europe/united-kingdom/scotland-260701.osm.pbf" \
  "${OSM_PBF}"

verify_sha256 "${PLANETILER_SHA256}" "${PLANETILER_JAR}"
verify_sha256 "${OSM_SHA256}" "${OSM_PBF}"

java_major="$("${JAVA_BIN}" -version 2>&1 | awk -F '[\".]' '/version/ {print $2; exit}')"
if [[ -z "${java_major}" || "${java_major}" -lt 21 ]]; then
  echo "Planetiler ${PLANETILER_VERSION} requires Java 21 or newer." >&2
  echo "Set JAVA_BIN to a Java 21+ executable." >&2
  exit 1
fi

"${JAVA_BIN}" "-Xmx${JVM_HEAP}" -jar "${PLANETILER_JAR}" \
  --osm-path="${OSM_PBF}" \
  --output="${OUTPUT}" \
  --bounds="${BOUNDS}" \
  --minzoom=0 \
  --maxzoom=14 \
  --download \
  --download-dir="${WORK_DIR}/sources" \
  --tmpdir="${WORK_DIR}/tmp" \
  --force

echo
echo "Generated ${OUTPUT}"
echo "sizeBytes=$(stat -f '%z' "${OUTPUT}" 2>/dev/null || stat -c '%s' "${OUTPUT}")"
shasum -a 256 "${OUTPUT}"
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/inspect_pmtiles.py" "${OUTPUT}"
