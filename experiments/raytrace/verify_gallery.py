#!/usr/bin/env python3
"""Independent consumer of public original Blender/Cycles images and receipts.

The generator and the independent validator intentionally execute in separate
Python processes. Equality of JSON/image hashes is not geometry/CSG parity
against the protected Oneirifact engine.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

PROFILES = ("pavilion-day", "pavilion-night", "pavilion-tall", "pavilion-plan")
W, H = 720, 480


def digest(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def qualify(out_dir: Path, specs: Path, generator: Path) -> dict:
    from PIL import Image, ImageChops, ImageStat

    expected = {p + suffix for p in PROFILES for suffix in (".png", ".json")}
    if set(p.name for p in out_dir.iterdir()) != expected:
        raise ValueError("missing/extra image or receipt in study output")
    spec = json.loads(specs.read_text(encoding="utf-8"))
    spec_sha = digest(specs)
    src_sha = digest(generator)
    receipts, images = {}, {}
    for i, profile in enumerate(PROFILES):
        receipt_path = out_dir / (profile + ".json")
        image_path = out_dir / (profile + ".png")
        for p in (receipt_path, image_path):
            if not p.is_file() or p.is_symlink():
                raise ValueError("non-regular generated evidence")
        r = json.loads(receipt_path.read_text(encoding="utf-8"))
        if r.get("schema") != "oneirifact.public-cycles-render-receipt/v0.1":
            raise ValueError("unknown render receipt schema")
        if r.get("source_kind") != "ORIGINAL_PUBLIC_PARAMETRIC_SCENE_NOT_PRIVATE_ONEIRIFACT_ENGINE":
            raise ValueError("false source fidelity claim")
        if r.get("status") != "ACTUAL_BLENDER_CYCLES_CPU_RENDER" or r.get("engine") != "CYCLES" or r.get("device") != "CPU":
            raise ValueError("native Cycles execution evidence missing")
        if not str(r.get("blender_version")).startswith("5.2.4"):
            raise ValueError("unqualified engine version")
        if r.get("spec_sha256") != spec_sha or r.get("generator_sha256") != src_sha:
            raise ValueError("source/procedure hash mismatch")
        if r.get("profile") != spec["profiles"][i]:
            raise ValueError("render variant does not match source specification")
        if r.get("resolution") != [W, H] or r.get("samples") != spec["profiles"][i]["samples"]:
            raise ValueError("wrong size or sample settings")
        if r.get("image_sha256") != digest(image_path) or r.get("image_bytes") != image_path.stat().st_size:
            raise ValueError("image receipt/hash mismatch")
        objects = r.get("object_ids")
        if not isinstance(objects, list) or len(objects) != r.get("object_count") or len(objects) < 100:
            raise ValueError("procedural object count failed")
        if len(set(objects)) != len(objects) or "suspended prismatic mineral" not in objects:
            raise ValueError("missing stable named geometry")
        if r.get("object_names_sha256") != "sha256:" + hashlib.sha256(("\n".join(objects) + "\n").encode()).hexdigest():
            raise ValueError("procedural occurrence identity digest mismatch")
        if not any(x.startswith("arched rib 07 segment") for x in objects):
            raise ValueError("parametric arch occurrence missing")
        with Image.open(image_path) as im:
            im.load()
            if im.format != "PNG" or im.size != (W, H):
                raise ValueError("unsupported output image")
            rgb = im.convert("RGB")
            colors = len(rgb.getcolors(maxcolors=1_000_000) or [])
            if colors < 1000:
                raise ValueError("image lacks meaningful tone variation")
            images[profile] = rgb.copy()
        receipts[profile] = r

    base = receipts["pavilion-day"]
    for alt in PROFILES[1:]:
        if base["object_ids"] != receipts[alt]["object_ids"]:
            raise ValueError("source object naming changed across scene controls")
    if base["profile"]["height_m"] != receipts["pavilion-night"]["profile"]["height_m"]:
        raise ValueError("lighting comparison changed geometry dimensions")
    if base["camera_position"] != receipts["pavilion-tall"]["camera_position"]:
        raise ValueError("geometry comparison changed camera")
    if base["camera_position"] == receipts["pavilion-plan"]["camera_position"]:
        raise ValueError("overhead comparison camera did not change")

    comparisons = {}
    for alt in PROFILES[1:]:
        difference = ImageChops.difference(images["pavilion-day"], images[alt])
        changed = sum(1 for rgb in difference.getdata() if rgb != (0, 0, 0))
        means = [round(x, 3) for x in ImageStat.Stat(difference).mean]
        if changed < 4000 or max(means) <= 0.65:
            raise ValueError("native raytracing controls did not change rendered pixels")
        comparisons[alt] = {"changed_pixels": changed, "pixel_count": W * H, "mean_absolute_rgb": means}
    return {
        "schema": "oneirifact.public-gallery-qualification/v0.1",
        "status": "INDEPENDENT_REAL_CYCLES_IMAGES_PASS",
        "scope": "original first-party procedural visual study; NOT private Oneirifact engine/CSG",
        "native_engine": "Blender 5.2.4 LTS CPU Cycles",
        "source_sha256": src_sha,
        "spec_sha256": spec_sha,
        "object_count": base["object_count"],
        "images_sha256": {k: receipts[k]["image_sha256"] for k in PROFILES},
        "comparisons": comparisons,
    }


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: verify_gallery.py OUTPUT_DIR SPECS.json PAVILION.py")
    result = qualify(*[Path(x) for x in sys.argv[1:]])
    output = Path(sys.argv[1]) / "qualification.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PUBLIC_R191_REAL_CYCLES_GALLERY_PASS", json.dumps(result, sort_keys=True))
