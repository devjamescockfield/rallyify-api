#!/usr/bin/env python3
import argparse
import gzip
import json
from pathlib import Path
import struct


HEADER_SIZE = 127
COMPRESSION_NAMES = {1: "none", 2: "gzip", 3: "brotli", 4: "zstd"}
TILE_TYPE_NAMES = {1: "mvt", 2: "png", 3: "jpeg", 4: "webp", 5: "avif"}


def read_archive(path: Path) -> dict:
    with path.open("rb") as archive:
        header = archive.read(HEADER_SIZE)
        if len(header) != HEADER_SIZE or header[:7] != b"PMTiles":
            raise ValueError("Not a PMTiles v3 archive.")
        version = header[7]
        if version != 3:
            raise ValueError(f"Unsupported PMTiles version: {version}")

        metadata_offset = struct.unpack_from("<Q", header, 24)[0]
        metadata_length = struct.unpack_from("<Q", header, 32)[0]
        archive.seek(metadata_offset)
        metadata_bytes = archive.read(metadata_length)

    compression = header[97]
    if compression == 2:
        metadata_bytes = gzip.decompress(metadata_bytes)
    elif compression != 1:
        raise ValueError(
            "Metadata compression requires an external decoder: "
            f"{COMPRESSION_NAMES.get(compression, compression)}"
        )

    return {
        "pmtilesVersion": version,
        "sizeBytes": path.stat().st_size,
        "clustered": bool(header[96]),
        "internalCompression": COMPRESSION_NAMES.get(compression, compression),
        "tileCompression": COMPRESSION_NAMES.get(header[98], header[98]),
        "tileType": TILE_TYPE_NAMES.get(header[99], header[99]),
        "minZoom": header[100],
        "maxZoom": header[101],
        "bounds": [
            struct.unpack_from("<i", header, 102)[0] / 10_000_000,
            struct.unpack_from("<i", header, 106)[0] / 10_000_000,
            struct.unpack_from("<i", header, 110)[0] / 10_000_000,
            struct.unpack_from("<i", header, 114)[0] / 10_000_000,
        ],
        "metadata": json.loads(metadata_bytes),
    }


def main():
    parser = argparse.ArgumentParser(description="Inspect a PMTiles v3 archive.")
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(read_archive(args.archive), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
