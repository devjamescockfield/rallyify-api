# Northern Highlands PMTiles Proof Of Concept

## Package

- ID: `uk-scotland-northern-highlands`
- Version: `2026-07-01`
- File: `uk-scotland-northern-highlands-2026-07-01.pmtiles`
- Bounds: `[-6.22, 57.20, -2.65, 58.87]` in WGS84 longitude/latitude order
- Zoom range: 0-14
- Tile schema: OpenMapTiles 3.16.0
- Rallyify style compatibility: `rallyify-offline-v1`

The rectangle covers Inverness, Applecross, the northern coast through
Durness, Thurso and John o' Groats, plus roughly 20-30 km of overlap beyond
the principal NC500 extent. The canonical polygon is
`maps/bounds/uk-scotland-northern-highlands.geojson`.

## Source And Licensing

The build uses Geofabrik's dated
`scotland-260701.osm.pbf` OpenStreetMap extract:

```text
https://download.geofabrik.de/europe/united-kingdom/scotland-260701.osm.pbf
SHA-256 1631f148d15f64667a48da52bcc5c9985df594af0ffd625395b00b0158daa50d
```

OpenStreetMap data is available under the Open Database License 1.0. The
Planetiler OpenMapTiles profile produces OpenMapTiles-compatible vector
tiles. Any map displaying this package must visibly show:

```text
© OpenMapTiles © OpenStreetMap contributors
```

Source and licence links are also published in
`/offline-maps/attribution.json`. This workflow does not download, scrape or
republish MapTiler Cloud tiles.

## Generation

Planetiler 0.10.2 and Java 21+ are required. Planetiler itself downloads its
official Natural Earth, water polygon and lake-centreline inputs. Allocate
about 2 GB of temporary disk space and at least 8 GB of JVM heap for this
Scotland build.

```bash
JAVA_BIN=/path/to/java21 JVM_HEAP=8g \
  ./scripts/build_nc500_pmtiles.sh
```

The equivalent Planetiler command is:

```bash
java -Xmx8g -jar maps/work/planetiler-v0.10.2.jar \
  --osm-path=maps/work/scotland-260701.osm.pbf \
  --output=maps/public/packages/uk-scotland-northern-highlands-2026-07-01.pmtiles \
  --bounds=-6.22,57.20,-2.65,58.87 \
  --minzoom=0 \
  --maxzoom=14 \
  --download \
  --download-dir=maps/work/sources \
  --tmpdir=maps/work/tmp \
  --force
```

Inspect the archive and calculate deployment values:

```bash
python scripts/inspect_pmtiles.py \
  maps/public/packages/uk-scotland-northern-highlands-2026-07-01.pmtiles
shasum -a 256 \
  maps/public/packages/uk-scotland-northern-highlands-2026-07-01.pmtiles
```

The proof-of-concept artifact is 51,806,701 bytes with SHA-256:

```text
c3be42243cfeb283523b2ea1a0ce2767875509f129333a7d713b9529a955bcf0
```

The source replication timestamp embedded in the archive is
`2026-07-01T20:22:00Z`. The tracked `.sha256` sidecar can be served or checked
independently of the manifest.

Generated PBF inputs, tools and `.pmtiles` binaries are intentionally ignored
by Git. The versioned manifest, boundary and reproducible generation scripts
remain tracked.

The local build host had approximately 1.7 TiB free before generation. The
build workspace peaked around 2 GB, while only the 52 MB archive, checksum,
manifest, attribution and boundary need to remain on the staging host. Before
building or copying on the VM, check its target filesystem:

```bash
df -h .
du -sh maps/public maps/work 2>/dev/null || true
```

## Deployment

Copy or upload the versioned archive without changing its filename:

```bash
install -d maps/public/packages
cp /build/output/uk-scotland-northern-highlands-2026-07-01.pmtiles \
  maps/public/packages/
shasum -a 256 maps/public/packages/*.pmtiles
(cd maps/public/packages && \
  shasum --check uk-scotland-northern-highlands-2026-07-01.pmtiles.sha256)
docker compose up -d caddy
```

Caddy mounts `./maps/public` read-only at `/srv/offline-maps`. Django is not
involved in archive or manifest responses.

Published URLs for the example staging hostname:

```text
https://api-dev.example.com/offline-maps/manifest.json
https://api-dev.example.com/offline-maps/packages/uk-scotland-northern-highlands-2026-07-01.pmtiles
https://api-dev.example.com/offline-maps/bounds/uk-scotland-northern-highlands.geojson
```

Replace `api-dev.example.com` in the Caddyfile and manifest when deploying on
another hostname. Keep the package URL versioned and immutable. Publish a new
filename and manifest version for every rebuild; never replace bytes beneath
an existing immutable URL.

## HTTP Verification

Check metadata and a one-byte range:

```bash
BASE_URL=https://api-dev.example.com/offline-maps
curl --fail --silent --show-error --head \
  "$BASE_URL/packages/uk-scotland-northern-highlands-2026-07-01.pmtiles"
curl --fail --silent --show-error --dump-header - \
  --range 0-0 --output /dev/null \
  "$BASE_URL/packages/uk-scotland-northern-highlands-2026-07-01.pmtiles"
```

The range request must return `206 Partial Content`, `Accept-Ranges: bytes`,
`Content-Range: bytes 0-0/51806701`, and `Content-Length: 1`. A normal HEAD
must include the full `Content-Length`, `ETag`, `Last-Modified`,
`application/vnd.pmtiles`, and immutable cache policy.

Test an interrupted/resumed download:

```bash
curl --fail --location --range 0-1048575 \
  --output /tmp/nc500.pmtiles.part \
  "$BASE_URL/packages/uk-scotland-northern-highlands-2026-07-01.pmtiles"
curl --fail --location --continue-at - \
  --output /tmp/nc500.pmtiles.part \
  "$BASE_URL/packages/uk-scotland-northern-highlands-2026-07-01.pmtiles"
shasum -a 256 /tmp/nc500.pmtiles.part
```

The final checksum must match the manifest.

## Manifest Update And Rollback

For an update:

1. Select a new dated Geofabrik extract and new package version.
2. Update the pinned source URL and SHA-256 in the build script.
3. Build a new filename; do not overwrite the old archive.
4. Inspect the PMTiles header and calculate its SHA-256 and byte size.
5. Add the new metadata to `maps/public/manifest.json`.
6. Copy the archive to the server and verify range responses before exposing
   the new manifest entry.

For rollback, restore the previous manifest while leaving both immutable
versioned archives in place. Remove old archives only after all supported app
versions have stopped referencing them.
