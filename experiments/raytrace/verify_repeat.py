#!/usr/bin/env python3
"""Independent real CPU Cycles same-source replay image oracle.

Compares two actual native renders from the same public runner. Whole PNG files
may differ due to time metadata; pixel equality, source/controls and executable
version are independently checked instead.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

NAME = "pavilion-day"
EXPECTED_OBJECTS = 136


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def compare(first: Path, second: Path) -> dict:
    from PIL import Image, ImageChops, ImageStat

    receipts, pixels, full_hashes = [], [], []
    for folder in (first, second):
        image = folder / (NAME + ".png")
        receipt = folder / (NAME + ".json")
        if not image.is_file() or not receipt.is_file() or image.is_symlink() or receipt.is_symlink():
            raise ValueError("nonregular/missing native Cycles evidence")
        r = json.loads(receipt.read_text(encoding="utf-8"))
        if r.get("schema") != "oneirifact.public-cycles-render-receipt/v0.1":
            raise ValueError("wrong execution receipt")
        if r.get("status") != "ACTUAL_BLENDER_CYCLES_CPU_RENDER" or r.get("engine") != "CYCLES":
            raise ValueError("native renderer did not execute")
        if not str(r.get("blender_version", "")).startswith("5.2.4") or r.get("device") != "CPU":
            raise ValueError("renderer version/CPU mismatch")
        if r.get("image_sha256") != digest(image):
            raise ValueError("unbound pixel file checksum")
        if r.get("object_count") != EXPECTED_OBJECTS or r.get("profile", {}).get("id") != NAME:
            raise ValueError("unexpected procedural object identity")
        if r.get("resolution") != [720, 480] or r.get("seed") != 191 or r.get("samples") != 32:
            raise ValueError("unqualified render controls")
        with Image.open(image) as im:
            im.load()
            if im.format != "PNG" or im.size != (720, 480):
                raise ValueError("not expected native PNG")
            pixels.append(im.convert("RGB").copy())
        receipts.append(r)
        full_hashes.append(digest(image))
    for key in ("spec_sha256", "generator_sha256", "profile", "object_ids", "object_names_sha256",
                "camera_position", "resolution", "samples", "seed", "engine", "blender_version"):
        if receipts[0][key] != receipts[1][key]:
            raise ValueError("source-exact repeat identity mismatch: " + key)
    delta = ImageChops.difference(pixels[0], pixels[1])
    count = sum(1 for val in delta.getdata() if val != (0, 0, 0))
    max_channel = max(x[1] for x in delta.getextrema())
    if count or max_channel:
        raise ValueError("same-run determinism not bitwise exact after pixel decode")
    result = {
        "schema": "oneirifact.public-native-cycles-repeat/v0.1",
        "status": "EXACT_DECODED_RGB_REPEAT_PASS",
        "scope": "original public pavilion; same free-tier CPU runner not cross-host/actual private Oneirifact",
        "image_sha256": full_hashes,
        "same_complete_png_bytes": full_hashes[0] == full_hashes[1],
        "pixel_diff_count": count,
        "pixel_diff_max_channel": max_channel,
        "source_sha256": receipts[0]["generator_sha256"],
        "spec_sha256": receipts[0]["spec_sha256"],
        "object_count": receipts[0]["object_count"],
        "dimensions": [720, 480],
        "samples": 32,
        "seed": 191,
    }
    return result


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: verify_repeat.py FIRST_DIR SECOND_DIR OUTPUT_RECEIPT.json")
    answer = compare(Path(sys.argv[1]), Path(sys.argv[2]))
    out = Path(sys.argv[3])
    if out.exists() or out.is_symlink():
        raise ValueError("refuse receipt overwrite")
    out.write_text(json.dumps(answer, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("PUBLIC_R193_REAL_CYCLES_REPEAT_PASS", json.dumps(answer, sort_keys=True))
