"""Independent analytic assembly-plan checks, plus native OBJ/GLB identity checks.

Checks exact source mating axes and placements; does not pretend to certify
mesh contact, friction, load capacity or manufacturing tolerance.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def near(a, b, tolerance=1e-10):
    return abs(a - b) <= tolerance


def close3(a, b, tolerance=1e-10):
    return all(near(x, y, tolerance) for x, y in zip(a, b))


def rotation_z_axis(degrees):
    x, y, z = [math.radians(v) for v in degrees]
    # Independent direct Rz*Ry*Rx third-column calculation.
    return [math.cos(z) * math.sin(y) * math.cos(x) + math.sin(z) * math.sin(x),
            math.sin(z) * math.sin(y) * math.cos(x) - math.cos(z) * math.sin(x),
            math.cos(y) * math.cos(x)]


def verify_source(scene, plan):
    parts = scene["instances"]
    require(len(parts) == plan["instance_count"] <= 32, "instance count")
    require(len({p["id"] for p in parts}) == len(parts), "duplicate instance")
    require(dict(sorted(Counter(p["definition_id"] for p in parts).items())) == plan["bom"], "BOM mismatch")
    require(all(p["composition_mode"] == "scene_assembly" for p in parts), "wrong composition mode")
    require(all(near(p["transform"]["scale"], 1) for p in parts), "unplanned uniform scale")
    ids = {p["id"]: p for p in parts}
    if scene["id"] == "brick_bridge":
        pitch, height = 0.008, 0.0096
        for p in parts:
            x, y, z = p["transform"]["translation"]
            require(near(x / pitch, round(x / pitch)) and near(y / pitch, round(y / pitch)), "stud lattice mismatch")
            require(near((z - height / 2) / height, round((z - height / 2) / height)), "brick course mismatch")
            require(close3(p["transform"]["rotation"], [0, 0, 0]), "unplanned brick rotation")
        for side, sign in [("left", -1), ("right", 1)]:
            for level in range(3):
                require(close3(ids[f"pier_{side}_{level}"]["transform"]["translation"],
                               [sign * 0.024, 0, 0.0048 + level * height]), "pier location")
        require(close3(ids["bridge_deck"]["transform"]["translation"], [0, 0, 0.0336]), "deck location")
        return {"stud_lattice": "PASS", "course_alignment": "PASS", "reusable_piers": 2}
    if scene["id"] == "log_cabin":
        for p in parts:
            tx = p["transform"]
            x, y, z = tx["translation"]
            if p["definition_id"] == "notched_log":
                require(near((z - 0.004) / 0.004, round((z - 0.004) / 0.004)), "half-height course mismatch")
                if p["id"].startswith("side_"):
                    require(near(abs(x), 0.024) and near(y, 0), "side notch alignment")
                    require(close3(tx["rotation"], [0, 0, 90]), "side orientation")
                else:
                    require(near(x, 0) and near(abs(y), 0.024), "back/sill notch alignment")
                    require(close3(tx["rotation"], [0, 0, 0]), "back/sill orientation")
            else:
                sign = -1 if p["id"] == "roof_left" else 1
                require(close3(tx["rotation"], [0, sign * 30, 0]), "roof pitch")
                angle = math.radians(30)
                # Plane evaluated at side wall axis, accounting for panel half-thickness.
                surface = z - (0.024 - abs(x)) * math.tan(angle) - 0.0015 / math.cos(angle)
                require(near(surface, plan["construction_invariants"]["wall_top_m"]), "roof support plane")
        return {"notch_axes": "PASS", "half_height_courses": "PASS", "roof_support_plane": "PASS"}
    require(scene["id"] == "rod_hub_frame", "unknown assembly")
    centers = plan["hub_centers_m"]
    for i, center in enumerate(centers):
        require(close3(ids[f"hub_{i}"]["transform"]["translation"], center), "hub center")
    for edge in plan["edges"]:
        p, q = [centers[i] for i in edge["hubs"]]
        length = math.sqrt(sum((a - b) ** 2 for a, b in zip(p, q)))
        require(near(length, edge["center_distance_m"]), "frame edge length")
        rod = ids[edge["rod"]]
        tx, half = rod["transform"], (length - 2 * edge["endpoint_inset_m"]) / 2
        axis = rotation_z_axis(tx["rotation"])
        ends = [[tx["translation"][k] + sign * half * axis[k] for k in range(3)] for sign in [-1, 1]]
        direction = [(q[k] - p[k]) / length for k in range(3)]
        expected = [[p[k] + edge["endpoint_inset_m"] * direction[k] for k in range(3)],
                    [q[k] - edge["endpoint_inset_m"] * direction[k] for k in range(3)]]
        require(all(close3(a, b) for a, b in zip(ends, expected)), "rod endpoint/socket axis mismatch")
    require(len(plan["socket_axes"]) == 12, "socket count")
    for port in plan["socket_axes"]:
        p, q = centers[port["hub"]], centers[port["toward"]]
        length = math.sqrt(sum((a - b) ** 2 for a, b in zip(p, q)))
        require(close3(port["axis"], [(q[k] - p[k]) / length for k in range(3)]), "socket axis")
        require(port["radius_m"] > plan["families"]["frame_rod"]["radius_m"], "nominal radial clearance")
    return {"equal_strut_lengths": "PASS", "rod_socket_endpoint_alignment": "PASS", "nominal_clearance": "PASS"}


def glb_document(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data)
    require(magic == b"glTF" and version == 2 and length == len(data), "GLB header")
    size, tag = struct.unpack_from("<I4s", data, 12)
    require(tag == b"JSON", "GLB JSON chunk")
    return json.loads(data[20:20 + size].decode().rstrip(" \0"))


def verify_native(scene, folder):
    source = json.loads((folder / "spec.json").read_text())
    require([p["id"] for p in source["instances"]] == [p["id"] for p in scene["instances"]], "native source identities")
    require(all(p.get("definition_hash", "").startswith("sha256:") for p in source["instances"]), "missing native definition pins")
    names = []
    for line in (folder / "object.obj").read_text().splitlines():
        if line.startswith("o "):
            names.append(line[2:].strip())
    expected = {p["id"] for p in scene["instances"]}
    require(set(names) == expected and len(names) == len(expected), "native OBJ identity loss")
    doc = glb_document(folder / "object.glb")
    node_names = [node["name"] for node in doc["nodes"] if "mesh" in node]
    require(set(node_names) == expected and len(node_names) == len(expected), "native GLB identity loss")
    return {"native_definition_pins": "PASS", "obj_named_parts": len(names), "glb_mesh_nodes": len(node_names)}


def main(args):
    rows = []
    for name in ["brick_bridge", "log_cabin", "rod_hub_frame"]:
        folder = args.fixtures / name
        scene = json.loads((folder / "scene.candidate.json").read_text())
        plan = json.loads((folder / "assembly-plan.json").read_text())
        row = {"case": name, "source": verify_source(scene, plan)}
        negatives = []
        for operation in ["move", "duplicate", "scale"]:
            bad = copy.deepcopy(scene)
            if operation == "move":
                bad["instances"][0]["transform"]["translation"][0] += 0.003
            elif operation == "duplicate":
                bad["instances"][1]["id"] = bad["instances"][0]["id"]
            else:
                bad["instances"][0]["transform"]["scale"] = 1.1
            try:
                verify_source(bad, plan)
            except ValueError:
                negatives.append(operation)
            else:
                raise ValueError(name + ": corrupted fixture accepted: " + operation)
        row["rejected_controls"] = negatives
        if args.native:
            row["native"] = verify_native(scene, args.native / name)
        rows.append(row)
    receipt = {"schema": "oneirifact.construction-verification/v1", "results": rows,
        "scope": "Analytic source placements/ports, BOM and negative inputs; optional actual native export identity",
        "excluded_claims": ["mesh collision freedom", "continuous assembly path", "mechanical fit", "friction", "load capacity", "manufacturing tolerance"]}
    if args.output:
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("--native", type=Path)
    parser.add_argument("--output", type=Path)
    main(parser.parse_args())
