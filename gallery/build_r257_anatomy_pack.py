"""Create an exact classification-only derivative of the released display pack.

This modifies three named source memberships, not geometry, registration,
source attribution, morphology, mass, or organ dynamics.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path
import anatomy_pack as pack
from anatomy_classification import OVERRIDES, REVISION, inventory_correction, records, record_digest, relocate_layers

BASE_TAG = "anatomy-display-r233-v3"
BASE_SHA = "d72fbb77b1b0603005131bbd387a36ce1c2c9965dfce13a30150a0f4b22d56be"
TAG = "anatomy-display-r257-v4"
CHANGED = {"catalog.json", "male-inventory.json", "female-inventory.json",
           "male-urinary.glb", "male-endocrine.glb", "female-respiratory.glb", "female-digestive.glb"}


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()


def build(source, out, stage):
    entries = pack.verify(source, BASE_SHA)
    pack.require(len(entries) == 80, "source corpus size")
    out.mkdir(parents=True, exist_ok=False)
    stage.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(source) as z:
        files = {name: z.read(name) for name in entries}
    before = dict(files)
    catalog = json.loads(files["catalog.json"])
    pack.require(len(catalog["datasets"]) == 7 and sum(len(d["layers"]) for d in catalog["datasets"]) == 53, "source display coverage")
    transfers = []
    node_proofs = []
    for sex in ("male", "female"):
        dataset = next(d for d in catalog["datasets"] if d["id"] == sex)
        invname = sex + "-inventory.json"
        inventory = json.loads(files[invname])
        by_id = {r["id"]: r for r in inventory}
        touched = {v[k] for v in OVERRIDES[sex].values() for k in ("from", "to")}
        raw = {category: files[sex + "-" + category + ".glb"] for category in touched}
        moved = relocate_layers(raw, sex)
        original_records = {}
        for category, value in raw.items():
            for name, row in records(value)[1].items():
                pack.require(name not in original_records, "duplicate original source identity")
                original_records[name] = row
        after_records = {}
        for category, value in moved.items():
            for name, row in records(value)[1].items():
                pack.require(name not in after_records, "duplicate candidate source identity")
                after_records[name] = row
                node_proofs.append({"id": name, "sex": sex, "layer_after": sex + "-" + category,
                                   "source_accessor_transform_material_sha256": record_digest(original_records[name]),
                                   "candidate_accessor_transform_material_sha256": record_digest(row)})
            files[sex + "-" + category + ".glb"] = value
        pack.require(set(original_records) == set(after_records), "source node set changed")
        pack.require(all(record_digest(original_records[n]) == record_digest(after_records[n]) for n in original_records), "source geometry/transform/material changed")
        for name, item in OVERRIDES[sex].items():
            original = by_id[name]
            new = inventory_correction(sex, original)
            transfer = {"id": name, "sex": sex, "identity": item["identity"],
                        "from_layer": original["layer"], "to_layer": new["layer"],
                        "original_source_triangles": original["triangles"],
                        "geometry_transform_materials_changed": False}
            transfers.append(transfer)
        files[invname] = json_bytes([inventory_correction(sex, row) for row in inventory])
        for layer in dataset["layers"]:
            category = layer["id"].removeprefix(sex + "-")
            if category not in touched:
                continue
            raw = files[layer["file"].removeprefix("data/")]
            rs = records(raw)[1]
            delta = sum(by_id[name]["triangles"] * (int(item["to"] == category) - int(item["from"] == category))
                        for name, item in OVERRIDES[sex].items())
            layer.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), nodes=len(rs),
                         source_triangles=layer["source_triangles"] + delta,
                         display_triangles=sum(p["accessors"]["indices"]["accessor"]["count"] // 3 for r in rs.values() for p in r["primitives"]))
    catalog["display_classification"] = {
        "revision": REVISION,
        "source_display_pack_sha256": BASE_SHA,
        "transfers": transfers,
        "scope": "Exact source-ID display grouping only. Source surfaces, transforms, material appearance and reference limitations are unchanged. No registration, organ coupling or physical-property acceptance."
    }
    files["catalog.json"] = json_bytes(catalog)
    changed = {name for name in files if files[name] != before[name]}
    pack.require(changed == CHANGED, "unexpected changed display assets")
    for name, value in files.items():
        (stage / name).write_bytes(value)
    archive = out / (TAG + ".zip")
    sha = pack.pack(stage, archive)
    qualified = pack.verify(archive, sha)
    lock = {"schema": "oneirifact.browser-display-release/v1", "repository": "SemperSupra/oneirifact",
            "tag": TAG, "asset": TAG + ".zip", "sha256": sha, "assets": len(qualified),
            "models": 53, "datasets": 7, "unpacked_bytes": sum(r["bytes"] for r in qualified.values())}
    (out / "release-lock.json").write_bytes(json_bytes(lock))
    report = {"schema": "oneirifact.display-classification-correction/v1", "source_head": os.environ.get("SOURCE_HEAD_SHA"),
              "run_id": os.environ.get("GITHUB_RUN_ID"), "source_tag": BASE_TAG, "source_pack_sha256": BASE_SHA,
              "candidate_pack_sha256": sha, "status": "PASS_EXACT_SOURCE_MEMBERSHIP_AND_TRANSPORT",
              "changed_assets": sorted(changed), "unchanged_assets": len(files) - len(changed),
              "unchanged_model_files": 49, "source_nodes_preserved_in_affected_layers": len(node_proofs),
              "transfers": transfers, "node_proofs": node_proofs,
              "source_to_exterior_registration": "NOT_QUALIFIED", "real_organ_morphology_and_physics": "NOT_IMPLEMENTED",
              "limits": ["Display grouping correction only", "Original display materials retained, including their historical names/colors",
                         "Existing source attribution and all reference/coupling holds retained", "No anatomy completeness or clinical claim"]}
    (out / "classification-report.json").write_bytes(json_bytes(report))
    print(json.dumps({"status": report["status"], "sha256": sha, "bytes": archive.stat().st_size,
                      "changed_assets": sorted(changed), "preserved_nodes": len(node_proofs)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args()
    build(args.source, args.out, args.stage)
