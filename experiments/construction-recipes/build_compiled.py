"""Replay source-compiled construction artifacts; no replacement geometry engine.

Only standard-library Python is required here. OpenSCAD evaluates the preserved
programs emitted by Oneirifact's existing compiler. Blender displays the resulting
part meshes and applies the preserved scene transforms.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import zlib


ROOT = Path(__file__).resolve().parent
CASES = ("brick_bridge", "log_cabin", "rod_hub_frame")
FRAGILITY_GRID_METRES = 1e-8


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return sha256(path.read_bytes())


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local_path(root, relative):
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, "invalid locked path")
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root.resolve()), "locked path escapes package")
    return resolved


def verify_lock(root=ROOT):
    lock = json.loads((root / "compiled-lock.json").read_text())
    require(lock["schema"] == "oneirifact.construction-compiled-lock/v1", "lock schema")
    require(len(lock["parts"]) == 9, "expected nine compiled definitions")
    for relative, expected in lock["files"].items():
        path = local_path(root, relative)
        require(path.is_file() and digest(path) == expected, "locked file hash mismatch: " + relative)
    identifiers = set()
    for part in lock["parts"]:
        case, identity = part["case"], part["definition_id"]
        require(case in CASES and re.fullmatch(r"[a-z][a-z0-9_]*", identity), "invalid part identity")
        require((case, identity) not in identifiers, "duplicate compiled part")
        identifiers.add((case, identity))
        directory = local_path(root, part["directory"])
        manifest = json.loads((directory / "adapter-manifest.json").read_text())
        graph_bytes = (directory / "source.graph.json").read_bytes()
        program = directory / "source-first.scad"
        require("sha256:" + sha256(graph_bytes) == manifest["source_sha256"] == part["source_sha256"],
                "compiler source binding mismatch: " + identity)
        require("sha256:" + digest(program) == manifest["openscad_program_sha256"] == part["openscad_program_sha256"],
                "compiled program binding mismatch: " + identity)
        require(manifest["source_revision"] == part["source_revision"], "source revision binding mismatch")
        require("source revision: " + part["source_revision"] in program.read_text(), "SCAD revision header mismatch")
        component = json.loads((root / "fixtures" / case / "components" / (identity + ".json")).read_text())
        require(json.loads(graph_bytes) == component["graph"], "compiled graph differs from component source")
    return lock


def verify_fixtures(root=ROOT):
    generator = load_module(root / "generate.py", "construction_source_generator")
    verifier = load_module(root / "verify.py", "construction_source_verifier")
    with tempfile.TemporaryDirectory(prefix="construction-source-") as temp:
        regenerated = Path(temp) / "fixtures"
        generator.generate(regenerated)
        for path in sorted(regenerated.rglob("*.json")):
            relative = path.relative_to(regenerated)
            require(json.loads(path.read_text()) == json.loads((root / "fixtures" / relative).read_text()),
                    "regenerated fixture differs: " + str(relative))
    results = []
    for case in CASES:
        folder = root / "fixtures" / case
        candidate = json.loads((folder / "scene.candidate.json").read_text())
        scene = json.loads((folder / "spec.json").read_text())
        plan = json.loads((folder / "assembly-plan.json").read_text())
        result = verifier.verify_source(scene, plan)
        unpinned = json.loads(json.dumps(scene))
        pins = {}
        for instance in unpinned["instances"]:
            pin = instance.pop("definition_hash", None)
            require(isinstance(pin, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", pin), "missing native definition pin")
            definition = instance["definition_id"]
            require(definition not in pins or pins[definition] == pin, "inconsistent definition pins")
            pins[definition] = pin
        require(unpinned == candidate, "native-pinned scene changed source layout")
        results.append({"case": case, "checks": result, "definition_pins": pins,
                        "pin_origin": "preserved native component hash; not recomputed from pretty JSON"})
    return results


def read_binary_stl(path):
    data = path.read_bytes()
    require(len(data) >= 84, "short binary STL")
    count = struct.unpack_from("<I", data, 80)[0]
    require(0 < count <= 500000 and len(data) == 84 + 50 * count, "invalid binary STL length/count")
    triangles = []
    for offset in range(84, len(data), 50):
        record = struct.unpack_from("<12fH", data, offset)
        triangles.append(tuple(tuple(record[3 + 3 * i:6 + 3 * i]) for i in range(3)))
    return triangles


def audit_triangles(triangles):
    """Independent edge-incidence/winding check on exported STL coordinates.

    Binary STL already quantizes positions to float32. Use those exact decoded
    values for topology, with no additional tolerance-based vertex welding.
    Also report faces that a separate 10-nanometre grid would collapse; this
    measures numerical fragility without changing mesh identity to hide it.
    """
    require(triangles, "empty mesh")
    counts, directions = Counter(), Counter()
    volumes, vertices, edge_lengths = [], [], []
    coarse_collapsed = 0
    for triangle in triangles:
        require(len(triangle) == 3, "non-triangle face")
        require(all(len(v) == 3 and all(math.isfinite(x) and abs(x) < 10 for x in v) for v in triangle),
                "nonfinite or out-of-envelope mesh position")
        q = triangle
        ab = [q[1][k] - q[0][k] for k in range(3)]
        ac = [q[2][k] - q[0][k] for k in range(3)]
        cross = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
        require(any(cross), "triangle has zero area in decoded STL")
        coarse = [tuple(round(x / FRAGILITY_GRID_METRES) for x in v) for v in triangle]
        cab = [coarse[1][k] - coarse[0][k] for k in range(3)]
        cac = [coarse[2][k] - coarse[0][k] for k in range(3)]
        coarse_cross = (cab[1] * cac[2] - cab[2] * cac[1], cab[2] * cac[0] - cab[0] * cac[2], cab[0] * cac[1] - cab[1] * cac[0])
        coarse_collapsed += not any(coarse_cross)
        for a, b in ((q[0], q[1]), (q[1], q[2]), (q[2], q[0])):
            key, sign = ((a, b), 1) if a < b else ((b, a), -1)
            counts[key] += 1
            directions[key] += sign
            edge_lengths.append(math.dist(a, b))
        a, b, c = triangle
        volumes.append((a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2])
                        + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6)
        vertices.extend(triangle)
    boundary = sum(n == 1 for n in counts.values())
    overused = sum(n > 2 for n in counts.values())
    winding = sum(counts[key] == 2 and value != 0 for key, value in directions.items())
    require(boundary == overused == winding == 0,
            f"STL edge closure failed: boundary={boundary} overused={overused} winding={winding}")
    volume = math.fsum(volumes)
    require(math.isfinite(volume) and volume > 0, "nonpositive signed volume")
    return {"triangles": len(triangles), "unique_stl_edges": len(counts), "boundary_edges": boundary,
            "overused_edges": overused, "inconsistent_winding_edges": winding, "signed_volume_m3": volume,
            "bounds_m": [[min(v[k] for v in vertices) for k in range(3)], [max(v[k] for v in vertices) for k in range(3)]],
            "coordinate_identity": "exact decoded binary-STL float32 values; no added welding",
            "minimum_edge_m": min(edge_lengths), "fragility_grid_m": FRAGILITY_GRID_METRES,
            "faces_collapsed_by_fragility_grid": coarse_collapsed,
            "edge_closure": "PASS", "self_intersection": "NOT_TESTED",
            "dimensional_fidelity": "NOT_QUALIFIED", "physical_fit": "NOT_QUALIFIED"}


def execute(command, log, timeout):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    log.write_text(result.stdout)
    require(result.returncode == 0, "external command failed; see " + str(log))


def verify_render(scene_path, output):
    """Read exported artifacts independently of Blender's success exit code."""
    scene = json.loads(scene_path.read_text())
    expected = {instance["id"]: instance for instance in scene["instances"]}
    data = (output / "assembly.glb").read_bytes()
    require(len(data) >= 20 and struct.unpack_from("<4sII", data) == (b"glTF", 2, len(data)), "GLB header")
    size, kind = struct.unpack_from("<I4s", data, 12)
    require(kind == b"JSON" and 20 + size <= len(data), "GLB JSON chunk")
    doc = json.loads(data[20:20 + size].decode().rstrip(" \0"))
    nodes = [node for node in doc["nodes"] if "mesh" in node]
    names = [node["name"] for node in nodes]
    require(len(names) == len(expected) and set(names) == set(expected), "exported GLB instance identity mismatch")
    for node in nodes:
        source = expected[node["name"]]
        extras = node.get("extras", {})
        require(extras.get("oneirifact_instance_id") == source["id"] and
                extras.get("oneirifact_definition_id") == source["definition_id"] and
                extras.get("oneirifact_definition_hash") == source["definition_hash"] and
                extras.get("oneirifact_source_scene_sha256") == digest(scene_path), "GLB source binding metadata mismatch")
    receipt = json.loads((output / "render-receipt.json").read_text())
    require({"assembled.png", "exploded.png", "assembly.glb", "assembly.blend"}.issubset(receipt["files"]),
            "render receipt missing deliverables")
    for name, expected_hash in receipt["files"].items():
        require(Path(name).name == name and digest(output / name) == expected_hash, "render receipt digest mismatch")
    for name in ("assembled.png", "exploded.png"):
        png = (output / name).read_bytes()
        require(len(png) >= 33 and png[:8] == b"\x89PNG\r\n\x1a\n", "PNG signature")
        require(struct.unpack_from(">I4s", png, 8) == (13, b"IHDR"), "PNG IHDR chunk")
        require(struct.unpack_from(">II", png, 16) == (1000, 800), "PNG dimensions")
        require(zlib.crc32(png[12:29]) & 0xffffffff == struct.unpack_from(">I", png, 29)[0], "PNG IHDR checksum")
    return {"case": scene["id"], "named_glb_nodes": len(nodes), "source_binding_extras": "PASS",
            "render_receipt_digests": "PASS", "png_ihdr_dimensions": "PASS", "blender_version": receipt["blender"]}


def main(args):
    lock = verify_lock()
    sources = verify_fixtures()
    if args.verify_only:
        print(json.dumps({"source_lock": "PASS", "regenerated_fixtures": "PASS", "cases": sources}, indent=2))
        return
    args.output.mkdir(parents=True, exist_ok=False)
    cases = CASES if args.case == "all" else (args.case,)
    version = subprocess.run([args.openscad, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, check=True).stdout.strip()
    parts, renders = [], []
    for case in cases:
        target = args.output / case
        meshes = target / "parts"
        meshes.mkdir(parents=True)
        for part in (x for x in lock["parts"] if x["case"] == case):
            identity = part["definition_id"]
            program = local_path(ROOT, part["directory"]) / "source-first.scad"
            mesh = meshes / (identity + ".stl")
            execute([args.openscad, "--export-format", "binstl", "-o", str(mesh), str(program)],
                    target / (identity + ".openscad.log"), timeout=180)
            audit = audit_triangles(read_binary_stl(mesh))
            row = {**part, "stl_sha256": digest(mesh), "openscad_version": version, "mesh_audit": audit}
            (target / (identity + ".mesh-audit.json")).write_text(json.dumps(row, indent=2) + "\n")
            parts.append(row)
            print("COMPILED_PART " + json.dumps({"case": case, "definition_id": identity, **audit}), flush=True)
        if not args.no_render:
            execute([args.blender, "-b", "-t", "2", "--factory-startup", "--python", str(ROOT / "render_native.py"), "--",
                     "--scene", str(ROOT / "fixtures" / case / "spec.json"), "--parts-directory", str(meshes),
                     "--output", str(target / "render"), "--samples", str(args.samples)], target / "blender.log", timeout=300)
            readback = verify_render(ROOT / "fixtures" / case / "spec.json", target / "render")
            (target / "render-readback.json").write_text(json.dumps(readback, indent=2) + "\n")
            renders.append(readback)
    receipt = {"schema": "oneirifact.construction-compiled-replay/v1", "compiler_provenance": lock["compiler_provenance"],
               "lock_sha256": digest(ROOT / "compiled-lock.json"), "source_lock": "PASS", "regenerated_source": "PASS",
               "cases": [x for x in sources if x["case"] in cases], "parts": parts,
               "render_readback": renders,
               "rendering": "NOT_RUN" if args.no_render else "ACTUAL_COMPILED_PART_MESHES",
               "native_voxel_parity": "NOT_CLAIMED", "assembly_mesh_collision": "NOT_QUALIFIED",
               "mechanical_fit": "NOT_QUALIFIED", "manufacturing": "NOT_QUALIFIED"}
    (args.output / "replay-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("all", *CASES), default="all")
    parser.add_argument("--output", type=Path, default=Path("construction-output"))
    parser.add_argument("--openscad", default="openscad")
    parser.add_argument("--blender", default="blender")
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    main(parser.parse_args())
