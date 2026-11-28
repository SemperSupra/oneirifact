"""Inspect actual BodyParts3D exterior candidates without constructing a surface.

Same source collection and coordinate frame do not establish one biological
donor. Names nominate meshes; geometry and topology determine the bounded screen.
"""
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "r222"))
from baseline import sha

ATLAS = "18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9"
PATTERN = re.compile(r"\b(?:skin|integument(?:ary)?|epidermis|dermis|body surface|body envelope|external surface)\b", re.I)
RAYS = ([1, .071, .023], [-.13, .039, 1], [.09, 1, .127])


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sample(mesh, count, seed):
    tri = mesh.vertices[mesh.faces]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    need(np.isfinite(area).all() and area.sum() > 0, "nonfinite or empty surface area")
    rng = np.random.default_rng(seed)
    ids = rng.choice(len(tri), count, p=area / area.sum())
    uv = rng.random((count, 2))
    uv[uv.sum(1) > 1] = 1 - uv[uv.sum(1) > 1]
    t = tri[ids]
    return t[:, 0] + uv[:, :1] * (t[:, 1] - t[:, 0]) + uv[:, 1:] * (t[:, 2] - t[:, 0])


def topology(mesh):
    edge_counts = np.bincount(mesh.edges_unique_inverse, minlength=len(mesh.edges_unique))
    boundary = mesh.edges_unique[edge_counts == 1]
    adjacent = mesh.face_adjacency
    graph = coo_matrix((np.ones(len(adjacent)), (adjacent[:, 0], adjacent[:, 1])), shape=(len(mesh.faces), len(mesh.faces)))
    face_components = connected_components(graph, directed=False, return_labels=False)
    boundary_components = 0
    if len(boundary):
        vertices, indices = np.unique(boundary, return_inverse=True)
        edges = indices.reshape(-1, 2)
        graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(vertices), len(vertices)))
        boundary_components = connected_components(graph, directed=False, return_labels=False)
    return {
        "vertices": len(mesh.vertices), "triangles": len(mesh.faces),
        "bounds_m": mesh.bounds.tolist(), "boundary_edges": int((edge_counts == 1).sum()),
        "nonmanifold_edges": int((edge_counts > 2).sum()),
        "face_components": int(face_components),
        "boundary_graph_components": int(boundary_components),
        "watertight_unmodified": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "signed_volume_m3": float(mesh.volume) if mesh.is_watertight else None,
        "interpretation": "Unmodified index topology; boundary components are not identified anatomical orifices. No welding, hole closing, remeshing or reconstruction.",
    }


def main(atlas_path, out):
    need(sha(atlas_path.read_bytes()) == ATLAS, "exact admitted atlas archive")
    out.mkdir(parents=True, exist_ok=False)
    tetrahedron = trimesh.Trimesh(vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
                                 faces=[[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], process=False)
    oracle = topology(tetrahedron)
    opened = trimesh.Trimesh(vertices=tetrahedron.vertices, faces=tetrahedron.faces[:-1], process=False)
    negative = topology(opened)
    need(oracle["watertight_unmodified"] and oracle["boundary_edges"] == 0 and oracle["face_components"] == 1 and abs(oracle["signed_volume_m3"] - 1 / 6) < 1e-12,
         "analytic closed tetrahedron oracle")
    need(not negative["watertight_unmodified"] and negative["boundary_edges"] == 3 and negative["boundary_graph_components"] == 1,
         "deliberately opened tetrahedron must abstain")
    z = zipfile.ZipFile(atlas_path)
    receipt = json.loads(z.read("receipt.json"))
    inventory_raw = z.read("inventory.json")
    need(sha(inventory_raw) == receipt["files"]["inventory.json"]["sha256"], "inventory digest")
    inventory = json.loads(inventory_raw)
    need(len(inventory) == 2234 and len({r["id"] for r in inventory}) == 2234, "complete source inventory")
    atlas_bounds = np.array([np.min([r["bounds_m"][0] for r in inventory], axis=0), np.max([r["bounds_m"][1] for r in inventory], axis=0)])
    skeletal_rows = [r for r in inventory if r["category"] == "skeletal"]
    skeletal_bounds = np.array([np.min([r["bounds_m"][0] for r in skeletal_rows], axis=0), np.max([r["bounds_m"][1] for r in skeletal_rows], axis=0)])
    layers = {}

    def mesh_for(row):
        category = row["category"]
        if category not in layers:
            path = "layers/" + category + ".glb"
            raw = z.read(path)
            need(sha(raw) == receipt["files"][path]["sha256"], "source layer digest " + category)
            layers[category] = trimesh.load(io.BytesIO(raw), file_type="glb", force="scene", process=False)
        scene = layers[category]
        transform, geometry = scene.graph[row["id"]]
        mesh = scene.geometry[geometry].copy()
        mesh.apply_transform(transform)
        need(len(mesh.vertices) == row["vertices"] and len(mesh.faces) == row["triangles"], "source topology " + row["id"])
        need(np.isfinite(mesh.vertices).all() and np.max(abs(mesh.bounds - np.array(row["bounds_m"]))) < 2e-6, "source frame " + row["id"])
        return mesh

    nominated = []
    for row in inventory:
        names = [str(c[1]) for c in row["concepts"]]
        hits = [n for n in names if PATTERN.search(n) or n.lower().strip() in ("body", "human body", "adult human body")]
        if hits or row["category"] == "skin":
            nominated.append((row, hits))
    skin_scene = trimesh.Scene()
    candidates, meshes = [], {}
    for row, hits in nominated:
        mesh = mesh_for(row)
        ident = row["id"]
        meshes[ident] = mesh
        info = topology(mesh)
        overlap = np.maximum(0, np.minimum(mesh.bounds[1], skeletal_bounds[1]) - np.maximum(mesh.bounds[0], skeletal_bounds[0]))
        coverage = overlap / (skeletal_bounds[1] - skeletal_bounds[0])
        full_extent = bool(np.all(coverage >= .98))
        closed = bool(info["watertight_unmodified"] and info["winding_consistent"] and info["face_components"] == 1 and info["nonmanifold_edges"] == 0 and info["signed_volume_m3"] > 1e-9)
        info.update({"id": ident, "concepts": row["concepts"], "heuristic_source_category": row["category"],
                     "label_matches": hits, "original_obj_sha256": row["source_sha256"],
                     "source_vertex_face_sha256": sha(np.asarray(mesh.vertices, dtype="<f8").tobytes() + np.asarray(mesh.faces, dtype="<i8").tobytes()),
                     "skeletal_bbox_axis_coverage": coverage.tolist(), "full_extent_screen": full_extent,
                     "closed_surface_screen": closed,
                     "containment_status": "PENDING" if closed and full_extent else "ABSTAIN_NOT_SINGLE_CLOSED_FULL_EXTENT_SURFACE"})
        candidates.append(info)
        display = mesh.copy()
        display.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name="Actual source exterior", baseColorFactor=[.65, .57, .50, 1], roughnessFactor=.85, doubleSided=True))
        skin_scene.add_geometry(display, node_name=ident, geom_name=ident)
    # Source skeletal geometry is used only as reference context and independent
    # fixed surface samples. The label category remains heuristic, not complete.
    skeleton_samples = []
    bone_sample_manifest = []
    for row in skeletal_rows:
        mesh = mesh_for(row)
        pts = sample(mesh, 32, 24301)
        skeleton_samples.append(pts)
        bone_sample_manifest.append({"id": row["id"], "concepts": row["concepts"], "samples": len(pts), "points_sha256": sha(pts.astype("<f8").tobytes())})
    skeleton_points = np.concatenate(skeleton_samples)
    np.savez_compressed(out / "source-skeletal-samples.npz", points=skeleton_points)
    for info in candidates:
        if info["containment_status"] != "PENDING":
            continue
        mesh = meshes[info["id"]]
        votes = np.zeros(len(skeleton_points), dtype=int)
        for direction in RAYS:
            _, rays, _ = mesh.ray.intersects_location(skeleton_points, np.tile(direction, (len(skeleton_points), 1)), multiple_hits=True)
            votes += np.bincount(rays, minlength=len(skeleton_points)) % 2
        info["containment_status"] = "GEOMETRIC_SCREEN_ONLY"
        info["skeletal_sample_parity"] = {"samples": len(votes), "inside_all_three": int((votes == 3).sum()), "outside_all_three": int((votes == 0).sum()), "ray_disagreement": int(((votes > 0) & (votes < 3)).sum())}
        # Equal per-element samples; neither whole-body area nor volume fraction.
    if candidates:
        raw = skin_scene.export(file_type="glb")
        (out / "source-exterior-candidates.glb").write_bytes(raw)
        reread = trimesh.load(io.BytesIO(raw), file_type="glb", force="scene", process=False)
        need(len(reread.geometry) == len(candidates), "candidate export mesh count")
        for info in candidates:
            transform, geom = reread.graph[info["id"]]
            m = reread.geometry[geom]
            actual = m.vertices @ transform[:3, :3].T + transform[:3, 3]
            expected = meshes[info["id"]]
            need(np.array_equal(m.faces, expected.faces) and np.max(np.linalg.norm(actual - expected.vertices, axis=1)) < 2e-6, "unchanged exterior export " + info["id"])
    combined = topology(trimesh.util.concatenate(list(meshes.values()))) if meshes else None
    # Diagnostic projections from actual surface samples; no synthesized body.
    skin_points = np.concatenate([sample(m, min(60000, max(500, len(m.faces) * 2)), 24302) for m in meshes.values()]) if meshes else np.empty((0, 3))
    lo, hi = atlas_bounds
    image = Image.new("RGB", (1650, 1040), "#13232e")
    draw = ImageDraw.Draw(image)
    fontpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    title = ImageFont.truetype(fontpath, 25)
    font = ImageFont.truetype(fontpath, 18)
    draw.text((24, 16), "BodyParts3D same-source exterior inspection | actual geometry", font=title, fill="white")
    draw.text((24, 53), "Source collection / source frame; one biological donor is not established. No inferred or reconstructed envelope.", font=font, fill="#c9d5de")
    height = hi[1] - lo[1]
    for col, (axis, label) in enumerate(((0, "Source skeletal context"), (0, "Exterior candidates / front"), (2, "Exterior candidates / side"))):
        scale = min(800 / height, 500 / max(hi[axis] - lo[axis], .01))
        center = (hi[axis] + lo[axis]) / 2
        draw.text((col * 550 + 24, 100), label, font=font, fill="white")
        def paint(points, color):
            if not len(points):
                return
            coords = np.column_stack((col * 550 + 275 + (points[:, axis] - center) * scale, 955 - (points[:, 1] - lo[1]) * scale))
            depth = points[:, 2 if axis == 0 else 0]
            for idx in np.argsort(depth):
                x, y = coords[idx]
                if col * 550 + 10 < x < (col + 1) * 550 - 10 and 140 < y < 970:
                    draw.point((int(x), int(y)), fill=color)
        paint(skeleton_points, "#e5d6ac" if col == 0 else "#4b718b")
        if col:
            paint(skin_points, "#cfae91")
            if not len(skin_points):
                draw.text((col * 550 + 80, 470), "NO SOURCE SURFACE MATCH", font=font, fill="#ffb978")
    closed_full = [r["id"] for r in candidates if r["closed_surface_screen"] and r["full_extent_screen"]]
    draw.text((24, 1000), f"Named geometry candidates: {len(candidates)} | closed full-extent screen: {len(closed_full)} | anatomy/native acceptance: HELD", font=font, fill="#c9d5de")
    image.save(out / "source-exterior-inspection.png")
    for name in ("LICENSE-source.html", "LICENSE-update.html"):
        (out / name).write_bytes(z.read(name))
    (out / "ATTRIBUTION.txt").write_bytes(z.read("ATTRIBUTION.txt") + b"\nR243: selected actual named exterior source meshes, unchanged geometry and source frame; presentation material and geometric diagnostic only. Same-source collection, one biological donor unestablished.\n")
    (out / "candidate-matches.json").write_text(json.dumps(candidates, indent=2) + "\n")
    report = {"status": "SOURCE_EXTERIOR_CANDIDATE_GEOMETRY" if closed_full else "NO_QUALIFIED_CLOSED_FULL_EXTENT_ENVELOPE_IN_SCREEN", "anatomical_acceptance": "HOLD", "execution_sha": os.environ.get("SOURCE_HEAD_SHA"), "workflow_sha": os.environ.get("GITHUB_SHA"),
              "input_artifact_id": 15238389268, "input_sha256": ATLAS, "inventory_sha256": sha(inventory_raw), "inventory_meshes": len(inventory),
              "topology_oracle": {"closed_tetrahedron": "PASS", "opened_tetrahedron": "PASS", "known_volume_m3": 1 / 6},
              "selection": "Actual source skin category or skin/integument/epidermis/dermis/body-surface/body-envelope/external-surface label, or exact body/human body/adult human body label; heuristic names only nominate inspection.",
              "atlas_bounds_m": atlas_bounds.tolist(), "skeletal_reference_bounds_m": skeletal_bounds.tolist(), "skeletal_reference_meshes": len(skeletal_rows),
              "candidates": candidates, "concatenated_unmodified_topology": combined, "closed_full_extent_ids": closed_full, "skeletal_sample_manifest": bone_sample_manifest,
              "limits": ["BodyParts3D is a same-source idealized collection; one biological donor is not established.", "No full-body surface inferred from names, bounding boxes or point cloud.", "No holes closed, vertices welded, normals reversed, skin reconstructed, geometry fit or cross-donor grafting.", "Containment abstains unless one unmodified watertight consistently wound positive-volume full-extent component passes the screen.", "Three-ray sampled containment does not prove collision freedom, anatomically correct orifices, tissue thickness or absence of self-intersection.", "Source classes and named coverage remain heuristic and incomplete; no native regeneration, rig or anatomical acceptance."]}
    report["files"] = {p.name: {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size} for p in out.iterdir() if p.is_file()}
    (out / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print("R243_ENVELOPE", json.dumps({k: report[k] for k in ("status", "execution_sha", "inventory_meshes", "skeletal_reference_meshes", "candidates", "closed_full_extent_ids")}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
