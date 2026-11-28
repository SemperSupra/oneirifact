"""Exact source-ID display grouping; never an anatomical registration or warp.

The admitted R222 GLBs have one identity world root, flat named mesh children,
uncompressed indexed triangles, and no skins, animation, textures or extensions.
This bounded adapter copies accessor bytes, node transforms and materials. It
rejects other layouts instead of guessing how to transform their geometry.
"""
from __future__ import annotations
import copy
import hashlib
import json
import struct

REVISION = "r257-exact-source-classification-v1"
OVERRIDES = {
    "male": {
        "FJ3129": {"from": "urinary", "to": "endocrine", "identity": "left adrenal gland"},
        "FJ3130": {"from": "urinary", "to": "endocrine", "identity": "right adrenal gland"},
    },
    "female": {
        "hra_0382_VH_F_diaphragmatic_surface_of_liver": {
            "from": "respiratory", "to": "digestive", "identity": "VH_F_diaphragmatic_surface_of_liver"
        }
    },
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def corrected_category(sex, identifier, original):
    item = OVERRIDES.get(sex, {}).get(identifier)
    if item is None:
        return original
    require(original == item["from"], "exact source category changed: " + identifier)
    return item["to"]


def inventory_correction(sex, row):
    """Preserve the old grouping as provenance on only the three corrected rows."""
    item = OVERRIDES.get(sex, {}).get(row["id"])
    if item is None:
        return copy.deepcopy(row)
    require(item["identity"] in row["names"], "exact source identity changed")
    category = corrected_category(sex, row["id"], row["category"])
    require(row["layer"] == sex + "-" + item["from"], "source inventory layer")
    result = copy.deepcopy(row)
    result.update(category=category, layer=sex + "-" + category,
                  source_display_category=row["category"],
                  classification_revision=REVISION,
                  classification_basis="Exact admitted source identifier and anatomical name; no substring inference")
    return result


def parse_glb(raw):
    require(len(raw) >= 28 and raw[:4] == b"glTF", "GLB header")
    magic, version, size = struct.unpack_from("<III", raw)
    require(version == 2 and size == len(raw), "GLB version/length")
    n, kind = struct.unpack_from("<II", raw, 12)
    require(kind == 0x4E4F534A and n % 4 == 0 and 20 + n + 8 <= len(raw), "GLB JSON chunk")
    doc = json.loads(raw[20:20+n])
    m, kind = struct.unpack_from("<II", raw, 20+n)
    require(kind == 0x004E4942 and 28+n+m == len(raw), "GLB binary chunk")
    blob = raw[28+n:]
    allowed = {"asset", "scene", "scenes", "nodes", "meshes", "accessors", "materials", "buffers", "bufferViews"}
    require(set(doc) <= allowed and doc["asset"]["version"] == "2.0", "unsupported GLB feature")
    require(doc.get("scene", 0) == 0 and doc["scenes"] == [{"nodes": [0]}], "unsupported scene graph")
    require(doc["nodes"][0] == {"name": "world", "children": list(range(1, len(doc["nodes"])))}, "nonidentity or nonflat source root")
    require(len(doc["buffers"]) == 1 and set(doc["buffers"][0]) == {"byteLength"}, "external buffer")
    require(0 <= len(blob) - doc["buffers"][0]["byteLength"] <= 3, "binary padding")
    require(all(set(m) <= {"name", "pbrMetallicRoughness", "doubleSided"} and
                set(m.get("pbrMetallicRoughness", {})) <= {"baseColorFactor", "roughnessFactor", "metallicFactor"}
                for m in doc.get("materials", [])), "unsupported material")
    return doc, blob


def records(raw):
    doc, blob = parse_glb(raw)
    result = {}
    used_meshes = set()
    for node in doc["nodes"][1:]:
        require(set(node) <= {"name", "mesh", "matrix", "translation", "rotation", "scale", "extras"}, "nonflat source node")
        name = node["name"]
        require(name not in result and node["mesh"] not in used_meshes, "duplicate source node/mesh")
        used_meshes.add(node["mesh"])
        mesh = doc["meshes"][node["mesh"]]
        require(set(mesh) <= {"name", "extras", "primitives"}, "unsupported mesh")
        primitives = []
        for p in mesh["primitives"]:
            require(set(p) <= {"attributes", "indices", "mode", "material"} and p.get("mode", 4) == 4, "nontriangle primitive")
            require("POSITION" in p["attributes"] and "indices" in p, "unindexed surface")
            accessors = {}
            for semantic, index in {"indices": p["indices"], **p["attributes"]}.items():
                a = copy.deepcopy(doc["accessors"][index])
                require(set(a) <= {"bufferView", "byteOffset", "componentType", "count", "max", "min", "type", "normalized"}, "unsupported accessor")
                view = copy.deepcopy(doc["bufferViews"][a.pop("bufferView")])
                require(set(view) <= {"buffer", "byteOffset", "byteLength", "byteStride", "target"} and view.pop("buffer") == 0, "unsupported buffer view")
                start = view.pop("byteOffset", 0)
                length = view["byteLength"]
                require(start >= 0 and length > 0 and start + length <= doc["buffers"][0]["byteLength"], "buffer bounds")
                accessors[semantic] = {"accessor": a, "view": view, "bytes": blob[start:start+length]}
            primitives.append({"mode": p.get("mode", 4), "accessors": accessors,
                               "material": copy.deepcopy(doc["materials"][p["material"]]) if "material" in p else None})
        result[name] = {"node": {k: copy.deepcopy(v) for k, v in node.items() if k != "mesh"},
                        "mesh": {k: copy.deepcopy(v) for k, v in mesh.items() if k != "primitives"},
                        "primitives": primitives}
    require(used_meshes == set(range(len(doc["meshes"]))), "unreferenced source meshes")
    return copy.deepcopy(doc["asset"]), result


def record_digest(record):
    def serial(value):
        if isinstance(value, bytes):
            return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
        if isinstance(value, list):
            return [serial(x) for x in value]
        if isinstance(value, dict):
            return {k: serial(v) for k, v in value.items()}
        return value
    return hashlib.sha256(json.dumps(serial(record), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def encode(asset, source_records):
    doc = {"asset": copy.deepcopy(asset), "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": "world", "children": []}], "meshes": [], "accessors": [],
           "bufferViews": [], "materials": [], "buffers": []}
    blob = bytearray()
    for name, record in source_records.items():
        node = copy.deepcopy(record["node"])
        require(node["name"] == name, "node identity mismatch")
        node["mesh"] = len(doc["meshes"])
        doc["nodes"][0]["children"].append(len(doc["nodes"]))
        doc["nodes"].append(node)
        mesh = copy.deepcopy(record["mesh"])
        mesh["primitives"] = []
        for primitive in record["primitives"]:
            p = {"mode": primitive["mode"], "attributes": {}}
            for semantic, item in primitive["accessors"].items():
                blob.extend(b"\0" * (-len(blob) % 4))
                view = {**copy.deepcopy(item["view"]), "buffer": 0, "byteOffset": len(blob)}
                a = {**copy.deepcopy(item["accessor"]), "bufferView": len(doc["bufferViews"])}
                doc["bufferViews"].append(view)
                index = len(doc["accessors"])
                doc["accessors"].append(a)
                blob.extend(item["bytes"])
                if semantic == "indices":
                    p["indices"] = index
                else:
                    p["attributes"][semantic] = index
            material = primitive["material"]
            if material is not None:
                if material not in doc["materials"]:
                    doc["materials"].append(copy.deepcopy(material))
                p["material"] = doc["materials"].index(material)
            mesh["primitives"].append(p)
        doc["meshes"].append(mesh)
    doc["buffers"] = [{"byteLength": len(blob)}]
    blob.extend(b"\0" * (-len(blob) % 4))
    raw = json.dumps(doc, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    raw += b" " * (-len(raw) % 4)
    return struct.pack("<III", 0x46546C67, 2, 28+len(raw)+len(blob)) + struct.pack("<II", len(raw), 0x4E4F534A) + raw + struct.pack("<II", len(blob), 0x004E4942) + blob


def relocate_layers(raw_layers, sex):
    """Return changed copies of four bounded layer layouts; keep other bytes."""
    result = dict(raw_layers)
    touched = {v[k] for v in OVERRIDES.get(sex, {}).values() for k in ("from", "to")}
    assets, meshes = {}, {}
    for category in touched:
        require(category in raw_layers, "missing required source/destination layer")
        assets[category], meshes[category] = records(raw_layers[category])
    for name, item in OVERRIDES.get(sex, {}).items():
        old, new = item["from"], item["to"]
        require(name in meshes[old] and name not in meshes[new], "source membership changed: " + name)
        meshes[new][name] = meshes[old].pop(name)
    for category in touched:
        result[category] = encode(assets[category], meshes[category])
        _, replay = records(result[category])
        require(list(replay) == list(meshes[category]), "node order/identity transport")
        require(all(record_digest(replay[n]) == record_digest(r) for n, r in meshes[category].items()), "source accessor/transform/material transport")
    return result
