"""Independent actual-pack membership and byte-exact geometry critic for R257.

Does not call the migration adapter. Controlled corruptions alter actual
candidate bytes; none are counted as anatomical or physical qualification.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import struct
import sys
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gallery"))
import anatomy_pack

SOURCE_SHA = "d72fbb77b1b0603005131bbd387a36ce1c2c9965dfce13a30150a0f4b22d56be"
MOVES = {
    "FJ3129": ("male-urinary", "male-endocrine", 3996, "left adrenal gland"),
    "FJ3130": ("male-urinary", "male-endocrine", 2294, "right adrenal gland"),
    "hra_0382_VH_F_diaphragmatic_surface_of_liver": ("female-respiratory", "female-digestive", 12448, "VH_F_diaphragmatic_surface_of_liver"),
}
LAYERS = ("male-urinary", "male-endocrine", "female-respiratory", "female-digestive")
CHANGED = {"catalog.json", "male-inventory.json", "female-inventory.json", *(x + ".glb" for x in LAYERS)}
REVISION = "r257-exact-source-classification-v1"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def decode(raw):
    need(struct.unpack_from("<III", raw) == (0x46546C67, 2, len(raw)), "GLB header")
    n, kind = struct.unpack_from("<II", raw, 12)
    need(kind == 0x4E4F534A, "GLB JSON kind")
    d = json.loads(raw[20:20+n])
    m, kind = struct.unpack_from("<II", raw, 20+n)
    need(kind == 0x004E4942 and 28+n+m == len(raw), "GLB binary length")
    return d, raw[28+n:]


def accessor(d, binary, index):
    a = d["accessors"][index]
    need("sparse" not in a and "bufferView" in a, "unsupported accessor")
    view = d["bufferViews"][a["bufferView"]]
    component_size = {5121: 1, 5123: 2, 5125: 4, 5126: 4}[a["componentType"]]
    element_size = component_size * {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    stride = view.get("byteStride", element_size)
    start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    need(view.get("buffer", 0) == 0 and stride >= element_size and start >= 0, "accessor layout")
    need(start + (a["count"] - 1) * stride + element_size <= len(binary), "accessor bounds")
    payload = b"".join(binary[start+i*stride:start+i*stride+element_size] for i in range(a["count"]))
    return {k: v for k, v in a.items() if k not in ("bufferView", "byteOffset")}, payload


def snapshot(raw):
    d, binary = decode(raw)
    need(not any(k in d for k in ("skins", "animations", "extensionsUsed", "images", "textures")), "unexpected body/texture feature")
    need(d.get("scene", 0) == 0 and d["scenes"] == [{"nodes": [0]}], "scene graph")
    need(d["nodes"][0] == {"name": "world", "children": list(range(1, len(d["nodes"])))}, "source world transform changed")
    rows = {}
    total = 0
    for node in d["nodes"][1:]:
        name = node["name"]
        need(name not in rows, "duplicate named source node")
        mesh = d["meshes"][node["mesh"]]
        primitives = []
        triangles = 0
        for p in mesh["primitives"]:
            need(p.get("mode", 4) == 4 and set(p["attributes"]) == {"POSITION"}, "unexpected source primitive")
            pos_meta, pos = accessor(d, binary, p["attributes"]["POSITION"])
            idx_meta, idx = accessor(d, binary, p["indices"])
            need(pos_meta["componentType"] == 5126 and pos_meta["type"] == "VEC3", "source position type")
            need(idx_meta["componentType"] == 5125 and idx_meta["type"] == "SCALAR" and idx_meta["count"] % 3 == 0, "source index type")
            need(all(math.isfinite(v) for t in struct.iter_unpack("<fff", pos) for v in t), "nonfinite source geometry")
            need(all(x[0] < pos_meta["count"] for x in struct.iter_unpack("<I", idx)), "invalid source triangle index")
            triangles += idx_meta["count"] // 3
            primitives.append({"positions": {"metadata": pos_meta, "sha256": sha(pos)},
                               "ordered_indices": {"metadata": idx_meta, "sha256": sha(idx)},
                               "mode": p.get("mode", 4),
                               "material": d.get("materials", [])[p["material"]] if "material" in p else None})
        rows[name] = {"node_transform_and_metadata": {k: v for k, v in node.items() if k != "mesh"},
                      "mesh_metadata": {k: v for k, v in mesh.items() if k != "primitives"},
                      "primitives": primitives, "triangles": triangles}
        total += triangles
    return rows, total, d["asset"]


def verify(before, after):
    need(set(before) == set(after) and len(before) == 80, "asset inventory changed")
    old, new, old_membership, new_membership, stats = {}, {}, {}, {}, {}
    for layer in LAYERS:
        a, old_faces, asset = snapshot(before[layer + ".glb"])
        b, new_faces, next_asset = snapshot(after[layer + ".glb"])
        need(asset == next_asset, "source GLB asset declaration changed")
        stats[layer] = {"nodes": len(b), "display_triangles": new_faces}
        for name, record in a.items():
            need(name not in old, "duplicate original source identity")
            old[name], old_membership[name] = record, layer
        for name, record in b.items():
            need(name not in new, "duplicate candidate source identity")
            new[name], new_membership[name] = record, layer
    need(set(old) == set(new) and len(old) == 144, "source node set changed")
    expected_membership = dict(old_membership)
    for name, (source, target, triangles, identity) in MOVES.items():
        need(old_membership[name] == source and old[name]["triangles"] == triangles, "source identity baseline changed")
        expected_membership[name] = target
    need(new_membership == expected_membership, "exact corrected layer membership mismatch")
    need(old == new, "source coordinates/ordered triangles/transforms/materials changed")
    changed = {name for name in before if before[name] != after[name]}
    need(changed == CHANGED, "unaffected asset bytes or expected correction changed")
    original_catalog = json.loads(before["catalog.json"])
    candidate_catalog = json.loads(after["catalog.json"])
    stripped_catalog = copy.deepcopy(candidate_catalog)
    added = stripped_catalog.pop("display_classification")
    need(added["revision"] == REVISION and added["source_display_pack_sha256"] == SOURCE_SHA, "correction provenance")
    need(len(added["transfers"]) == 3 and "No registration, organ coupling or physical-property acceptance" in added["scope"], "correction scope")
    for sex in ("male", "female"):
        filename = sex + "-inventory.json"
        original_inventory = json.loads(before[filename])
        inventory = json.loads(after[filename])
        need(len(original_inventory) == len(inventory), "inventory element count")
        for a, b in zip(original_inventory, inventory):
            need(a["id"] == b["id"], "source inventory identity/order")
            if a["id"] not in MOVES:
                need(a == b, "unaffected source inventory changed")
                continue
            source, target, triangles, identity = MOVES[a["id"]]
            expected = {**a, "category": target.split("-", 1)[1], "layer": target,
                        "source_display_category": a["category"], "classification_revision": REVISION,
                        "classification_basis": "Exact admitted source identifier and anatomical name; no substring inference"}
            need(identity in a["names"] and a["layer"] == source and a["triangles"] == triangles and b == expected, "exact inventory correction")
    for old_dataset, dataset in zip(original_catalog["datasets"], stripped_catalog["datasets"]):
        for old_layer, layer in zip(old_dataset["layers"], dataset["layers"]):
            layer_id = layer["id"]
            if layer_id not in LAYERS:
                need(old_layer == layer, "unaffected model declaration changed")
                continue
            raw = after[layer_id + ".glb"]
            source_delta = sum(n * (int(target == layer_id) - int(source == layer_id)) for source, target, n, _ in MOVES.values())
            expected = {**old_layer, **stats[layer_id], "bytes": len(raw), "sha256": sha(raw),
                        "source_triangles": old_layer["source_triangles"] + source_delta}
            need(layer == expected, "corrected layer counts/hashes")
            layer.clear()
            layer.update(old_layer)
    need(stripped_catalog == original_catalog, "catalog coverage, attribution or held-scope text changed")
    return {"status": "PASS_EXACT_CLASSIFICATION_TRANSPORT", "source_nodes_preserved": len(old),
            "relocated_source_nodes": 3, "unchanged_other_nodes_in_affected_layers": len(old) - 3,
            "unchanged_assets": 73, "unchanged_models": 49, "models": 53, "datasets": 7,
            "positions_and_ordered_indices": "BYTE_EXACT", "node_transforms": "EXACT_UNCHANGED",
            "materials_and_attribution": "UNCHANGED", "membership_after": {n: new_membership[n] for n in MOVES},
            "layer_counts_after": stats, "anatomical_registration": "NOT_QUALIFIED", "organ_physics": "NOT_IMPLEMENTED"}


def encode_doc(doc, binary):
    text = json.dumps(doc, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    return struct.pack("<III", 0x46546C67, 2, 28+len(text)+len(binary)) + struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(binary), 0x004E4942) + binary


def controlled_corruptions(before, after):
    controls = []
    def reject(name, edit):
        values = dict(after)
        edit(values)
        try:
            verify(before, values)
        except (ValueError, KeyError) as exc:
            controls.append({"id": name, "status": "PASS_REJECTED", "reason": str(exc)})
        else:
            controls.append({"id": name, "status": "FAIL_ACCEPTED"})
    def change_doc(values, file, edit):
        d, b = decode(values[file])
        edit(d)
        values[file] = encode_doc(d, b)
    def move_only_metadata(values):
        for name in LAYERS:
            values[name + ".glb"] = before[name + ".glb"]
    reject("metadata_without_actual_mesh_transfer", move_only_metadata)
    def corrupt_buffer(values, indices=False):
        file = "male-endocrine.glb"
        d, b = decode(values[file]);binary = bytearray(b)
        node = next(n for n in d["nodes"] if n.get("name") == "FJ3129")
        p = d["meshes"][node["mesh"]]["primitives"][0]
        a = d["accessors"][p["indices"] if indices else p["attributes"]["POSITION"]]
        view = d["bufferViews"][a["bufferView"]]
        offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        if indices:
            binary[offset:offset+4], binary[offset+4:offset+8] = binary[offset+4:offset+8], binary[offset:offset+4]
        else:
            struct.pack_into("<f", binary, offset, struct.unpack_from("<f", binary, offset)[0] + .0001)
        values[file] = encode_doc(d, bytes(binary))
    reject("actual_source_vertex_displaced", lambda v: corrupt_buffer(v))
    reject("actual_source_triangle_order_changed", lambda v: corrupt_buffer(v, True))
    reject("actual_node_transform_changed", lambda v: change_doc(v, "male-endocrine.glb", lambda d: next(n for n in d["nodes"] if n.get("name") == "FJ3129").update(translation=[.001, 0, 0])))
    reject("source_root_transform_changed", lambda v: change_doc(v, "female-digestive.glb", lambda d: d["nodes"][0].update(translation=[0, 0, .1])))
    reject("renamed_source_identity", lambda v: change_doc(v, "male-endocrine.glb", lambda d: next(n for n in d["nodes"] if n.get("name") == "FJ3129").update(name="renamed-adrenal")))
    def duplicate(values):
        # Restoring the old layer duplicates the exact actual adrenal nodes.
        values["male-urinary.glb"] = before["male-urinary.glb"]
    reject("source_node_duplicated_across_layers", duplicate)
    reject("unaffected_attribution_modified", lambda v: v.__setitem__("male-attribution.txt", v["male-attribution.txt"] + b"changed"))
    reject("unaffected_model_modified", lambda v: v.__setitem__("male-skeletal.glb", v["male-skeletal.glb"] + b"changed"))
    def claim(values):
        c = json.loads(values["catalog.json"]);c["datasets"][0]["scope"] = "Accepted coupled anatomy"
        values["catalog.json"] = json.dumps(c).encode()
    reject("anatomical_hold_text_removed", claim)
    def wrong_inventory(values):
        inv = json.loads(values["male-inventory.json"])
        next(r for r in inv if r["id"] == "FJ3129")["category"] = "urinary"
        values["male-inventory.json"] = json.dumps(inv).encode()
    reject("inventory_left_in_wrong_category", wrong_inventory)
    need(all(r["status"] == "PASS_REJECTED" for r in controls), "negative control accepted")
    return controls


def main(source, candidate, output):
    original_entries = anatomy_pack.verify(source, SOURCE_SHA)
    candidate_sha = anatomy_pack.digest(candidate)
    candidate_entries = anatomy_pack.verify(candidate, candidate_sha)
    with zipfile.ZipFile(source) as z:
        before = {n: z.read(n) for n in original_entries}
    with zipfile.ZipFile(candidate) as z:
        after = {n: z.read(n) for n in candidate_entries}
    result = verify(before, after)
    result.update(schema="oneirifact.independent-display-classification-critic/v1", source_pack_sha256=SOURCE_SHA,
                  candidate_pack_sha256=candidate_sha, controls=controlled_corruptions(before, after),
                  limits="Membership and source transport only; no new anatomy, coupling or physical qualification")
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "controls": len(result["controls"]), "source_nodes": result["source_nodes_preserved"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.source, args.candidate, args.output)
