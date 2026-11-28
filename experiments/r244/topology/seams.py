"""Exact-index seam diagnosis; preserve every actual source triangle corner.

No tolerance weld, hole filling, decimation, deletion or anatomical reconstruction.
The original source mesh remains immutable; a quotient is a separate diagnostic.
"""
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "r243" / "envelope"))
from envelope import need, sha, sample, topology

PIN = "6a02936df3e0e40616efc62315961372eddc833ded773b7b5be004cb06e4ae65"


def exact_quotient(mesh):
    vertices, inverse, multiplicity = np.unique(mesh.vertices, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    faces = inverse[mesh.faces]
    quotient = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    need(np.array_equal(mesh.vertices[mesh.faces], quotient.vertices[quotient.faces]), "exact original triangle corner order and positions")
    return quotient, inverse, multiplicity


def face_anomalies(mesh):
    faces = mesh.faces
    sorted_faces = np.sort(faces, axis=1)
    _, groups, counts = np.unique(sorted_faces, axis=0, return_inverse=True, return_counts=True)
    groups = groups.reshape(-1)
    start = faces.argmin(axis=1)
    oriented = faces[np.arange(len(faces))[:, None], (start[:, None] + np.arange(3)) % 3]
    _, oriented_counts = np.unique(oriented, axis=0, return_counts=True)
    orientations = np.unique(np.column_stack((groups, oriented)), axis=0)
    orientations_per_group = np.bincount(orientations[:, 0], minlength=len(counts))
    corners = mesh.vertices[faces]
    areas2 = np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    return {
        "index_degenerate_triangles": int(((faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) | (faces[:, 2] == faces[:, 0])).sum()),
        "exact_zero_area_triangles": int((areas2 == 0).sum()),
        "unordered_duplicate_groups": int((counts > 1).sum()),
        "unordered_duplicate_excess_faces": int(np.maximum(counts - 1, 0).sum()),
        "same_winding_duplicate_excess_faces": int(np.maximum(oriented_counts - 1, 0).sum()),
        "opposing_winding_duplicate_groups": int((orientations_per_group > 1).sum()),
    }


def boundaries(mesh):
    counts = np.bincount(mesh.edges_unique_inverse, minlength=len(mesh.edges_unique))
    return mesh.edges_unique[counts == 1]


def boundary_components(mesh):
    edges = boundaries(mesh)
    if not len(edges):
        return []
    vertices, inverse = np.unique(edges, return_inverse=True)
    local = inverse.reshape(-1, 2)
    graph = coo_matrix((np.ones(len(local)), (local[:, 0], local[:, 1])), shape=(len(vertices), len(vertices)))
    count, labels = connected_components(graph, directed=False)
    rows = []
    for group in range(count):
        take = labels[local[:, 0]] == group
        part_edges = edges[take]
        part_vertices = vertices[labels == group]
        points = mesh.vertices[part_vertices]
        _, degree = np.unique(part_edges, return_counts=True)
        length = np.linalg.norm(mesh.vertices[part_edges[:, 1]] - mesh.vertices[part_edges[:, 0]], axis=1)
        rows.append({"component": int(group), "edges": len(part_edges), "vertices": len(part_vertices),
                     "edge_length_sum_m": float(length.sum()), "edge_length_min_m": float(length.min()), "edge_length_max_m": float(length.max()),
                     "bounds_m": np.array([points.min(0), points.max(0)]).tolist(), "centroid_m": points.mean(0).tolist(),
                     "degree_one_vertices": int((degree == 1).sum()), "degree_above_two_vertices": int((degree > 2).sum()),
                     "closed_index_loop": bool(np.all(degree == 2))})
    return sorted(rows, key=lambda r: r["edge_length_sum_m"], reverse=True)


def surface_components(mesh):
    adjacent = mesh.face_adjacency
    graph = coo_matrix((np.ones(len(adjacent)), (adjacent[:, 0], adjacent[:, 1])), shape=(len(mesh.faces), len(mesh.faces)))
    count, labels = connected_components(graph, directed=False)
    rows = []
    for group in range(count):
        indices = np.flatnonzero(labels == group)
        vertices = np.unique(mesh.faces[indices])
        points = mesh.vertices[vertices]
        rows.append({"component": int(group), "triangles": len(indices), "vertices": len(vertices),
                     "surface_area_m2": float(mesh.area_faces[indices].sum()),
                     "bounds_m": np.array([points.min(0), points.max(0)]).tolist()})
    return sorted(rows, key=lambda r: r["triangles"], reverse=True)


def oracle():
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    faces = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])
    split = trimesh.Trimesh(vertices=vertices[faces].reshape(-1, 3), faces=np.arange(12).reshape(-1, 3), process=False)
    fixed, _, _ = exact_quotient(split)
    need(topology(split)["boundary_edges"] == 12 and fixed.is_watertight and abs(fixed.volume - 1 / 6) < 1e-12, "exact split tetrahedron oracle")
    opened = trimesh.Trimesh(vertices=split.vertices, faces=split.faces[:-1], process=False)
    still_open, _, _ = exact_quotient(opened)
    need(not still_open.is_watertight and topology(still_open)["boundary_edges"] == 3, "missing face must remain missing")
    duplicate = trimesh.Trimesh(vertices=split.vertices, faces=np.vstack((split.faces, split.faces[:1])), process=False)
    retained, _, _ = exact_quotient(duplicate)
    need(len(retained.faces) == 5 and face_anomalies(retained)["unordered_duplicate_excess_faces"] == 1 and topology(retained)["nonmanifold_edges"] == 3,
         "duplicate faces must remain and be diagnosed")
    return {"exact_seam_tetrahedron": "PASS", "missing_face_not_repaired": "PASS", "duplicate_face_not_deleted": "PASS"}


def main(archive, out):
    need(sha(archive.read_bytes()) == PIN, "exact R243 input archive")
    out.mkdir(parents=True, exist_ok=False)
    fixtures = oracle()
    with zipfile.ZipFile(archive) as z:
        prior = json.loads(z.read("receipt.json"))
        raw = z.read("source-exterior-candidates.glb")
        need(sha(raw) == prior["files"]["source-exterior-candidates.glb"]["sha256"], "inner source GLB digest")
        candidates = {r["id"]: r for r in prior["candidates"]}
        need(["FMA7163", "skin"] in candidates["FJ2810"]["concepts"], "actual skin source identity")
        scene = trimesh.load(io.BytesIO(raw), file_type="glb", force="scene", process=False)
        matrix, geometry = scene.graph["FJ2810"]
        need(np.array_equal(matrix, np.eye(4)), "source mesh must already be in original frame")
        original = scene.geometry[geometry].copy()
        need(len(original.vertices) == 102467 and len(original.faces) == 203382, "source census")
        for name in ("ATTRIBUTION.txt", "LICENSE-source.html", "LICENSE-update.html"):
            (out / name).write_bytes(z.read(name))
    original_corner_bytes = np.asarray(original.vertices[original.faces], dtype="<f4").tobytes()
    quotient, inverse, multiplicity = exact_quotient(original)
    quotient_corner_bytes = np.asarray(quotient.vertices[quotient.faces], dtype="<f4").tobytes()
    need(original_corner_bytes == quotient_corner_bytes, "bit-exact serialized triangle corners and winding")
    before, after = topology(original), topology(quotient)
    after["watertight_exact_quotient"] = after.pop("watertight_unmodified")
    after["interpretation"] = "Exact-coordinate vertex-index quotient, assessed without further processing. Every original triangle corner position, order and winding retained; no tolerance welding, face deletion or hole repair."
    before_faces, after_faces = face_anomalies(original), face_anomalies(quotient)
    need(len(original.faces) == len(quotient.faces) and before_faces["exact_zero_area_triangles"] == after_faces["exact_zero_area_triangles"], "all source faces retained")
    source_edges = boundaries(original)
    mapped_edges = np.sort(inverse[source_edges], axis=1)
    _, seam_counts = np.unique(mapped_edges, axis=0, return_counts=True)
    seam_evidence = {"source_boundary_edges": len(source_edges),
                     "exact_endpoint_pair_groups": len(seam_counts),
                     "original_boundary_edges_in_exact_pairs": int(seam_counts[seam_counts == 2].sum()),
                     "original_boundary_edges_in_multiplicity_above_two": int(seam_counts[seam_counts > 2].sum()),
                     "original_boundary_edges_with_no_exact_endpoint_mate": int((seam_counts == 1).sum()),
                     "zero_length_quotient_boundary_edges": int((mapped_edges[:, 0] == mapped_edges[:, 1]).sum()),
                     "interpretation": "Exact endpoint-coordinate matches only; unmatched edges are not automatically missing anatomical tissue or confirmed orifices."}
    before_boundaries, after_boundaries = boundary_components(original), boundary_components(quotient)
    before_components, after_components = surface_components(original), surface_components(quotient)
    np.savez_compressed(out / "exact-index-quotient-map.npz", original_vertex_to_unique_vertex=inverse,
                        unique_vertices=quotient.vertices.astype("<f4"), quotient_faces=quotient.faces.astype("<u4"))
    closed = bool(after["watertight_exact_quotient"] and after["winding_consistent"] and after["face_components"] == 1 and after["nonmanifold_edges"] == 0
                  and after["signed_volume_m3"] > 1e-9 and not after_faces["index_degenerate_triangles"] and not after_faces["exact_zero_area_triangles"] and not after_faces["unordered_duplicate_excess_faces"])
    if closed:
        derived = trimesh.Scene()
        candidate = quotient.copy()
        candidate.visual = original.visual.copy()
        derived.add_geometry(candidate, node_name="FJ2810_exact_index_quotient", geom_name="FJ2810_exact_index_quotient")
        encoded = derived.export(file_type="glb")
        reread = trimesh.load(io.BytesIO(encoded), file_type="glb", force="scene", process=False)
        rematrix, rename = reread.graph["FJ2810_exact_index_quotient"]
        remesh = reread.geometry[rename]
        need(np.array_equal(rematrix, np.eye(4)) and np.asarray(remesh.vertices[remesh.faces], dtype="<f4").tobytes() == original_corner_bytes, "export preserves every original corner")
        (out / "FJ2810-exact-index-quotient-candidate.glb").write_bytes(encoded)
    points = sample(original, 140000, 24401)
    image = Image.new("RGB", (1650, 1060), "#14242e")
    draw = ImageDraw.Draw(image)
    fontpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    title = ImageFont.truetype(fontpath, 24)
    font = ImageFont.truetype(fontpath, 18)
    draw.text((24, 14), "Actual source skin FJ2810 | exact-coordinate index seam diagnosis", font=title, fill="white")
    draw.text((24, 48), "All original triangle positions and winding retained. No tolerance welding, hole repair or inferred anatomy.", font=font, fill="#cad7df")
    lo, hi = original.bounds
    for col, (mesh, axis, label) in enumerate(((original, 0, "Original / front"), (quotient, 0, "Exact quotient / front"), (quotient, 2, "Exact quotient / side"))):
        scale = min(790 / (hi[1] - lo[1]), 490 / (hi[axis] - lo[axis]))
        center = (hi[axis] + lo[axis]) / 2
        def project(v):
            return np.column_stack((col * 550 + 275 + (v[:, axis] - center) * scale, 940 - (v[:, 1] - lo[1]) * scale))
        draw.text((col * 550 + 22, 95), label, font=title, fill="white")
        counts = before if col == 0 else after
        draw.text((col * 550 + 22, 127), f"{counts['boundary_edges']} boundary edges / {counts['face_components']} components", font=font, fill="#d0dce3")
        coords = project(points)
        for ix in np.argsort(points[:, 2 if axis == 0 else 0]):
            x, y = coords[ix]
            if col * 550 + 10 < x < (col + 1) * 550 - 10 and 165 < y < 965:
                draw.point((int(x), int(y)), fill="#b7a590")
        for edge in boundaries(mesh):
            line = project(mesh.vertices[edge])
            if np.all((line[:, 0] > col * 550 + 10) & (line[:, 0] < (col + 1) * 550 - 10) & (line[:, 1] > 165) & (line[:, 1] < 965)):
                draw.line([tuple(p) for p in line], fill="#f16f57" if col == 0 else "#ffd263", width=2)
    draw.text((24, 988), "All boundary edges projected, including rear surfaces; highlighted loops are not identified anatomical orifices.", font=font, fill="#cad7df")
    draw.text((24, 1018), "Closed quotient candidate" if closed else "Exact quotient remains open or otherwise fails the closed-surface screen; no closed model emitted.", font=font, fill="#ffd263")
    image.save(out / "source-skin-exact-seam-diagnostic.png")
    report = {"status": "EXACT_INDEX_QUOTIENT_CLOSED_CANDIDATE" if closed else "EXACT_INDEX_QUOTIENT_NOT_CLOSED_QUALIFIED",
              "anatomical_acceptance": "HOLD", "execution_sha": os.environ.get("SOURCE_HEAD_SHA"), "workflow_sha": os.environ.get("GITHUB_SHA"),
              "input_artifact": 15263871225, "input_sha256": PIN, "input_model_sha256": sha(raw), "source_id": "FJ2810", "source_concept": ["FMA7163", "skin"],
              "oracle": fixtures, "exact_coordinate_groups": len(quotient.vertices), "redundant_vertex_indices": len(original.vertices) - len(quotient.vertices),
              "duplicate_coordinate_groups": int((multiplicity > 1).sum()), "largest_coordinate_multiplicity": int(multiplicity.max()),
              "all_original_triangle_corners_bit_exact": True, "source_triangle_corner_sha256": sha(original_corner_bytes), "quotient_triangle_corner_sha256": sha(quotient_corner_bytes),
              "before": before, "after": after, "before_face_anomalies": before_faces, "after_face_anomalies": after_faces,
              "exact_boundary_matches": seam_evidence, "before_boundary_components": before_boundaries, "after_boundary_components": after_boundaries,
              "before_surface_components": before_components, "after_surface_components": after_components,
              "closed_candidate_emitted": closed,
              "limits": ["Same source collection; one biological donor not established.", "Only exact-coordinate index equivalence; no geometric distance tolerance or face repair.", "Original triangle order, corner positions and winding retained exactly; degenerate or duplicate source faces are diagnosed, not deleted.", "The exact preservation guarantee covers triangle corners and winding, not unchanged vertex normals after index equivalence.", "Open boundary loops are unclassified source topology; neither anatomical orifices nor missing tissue are inferred from loops.", "No containment, self-intersection, skin thickness, physiological motion or native acceptance claim."]}
    report["files"] = {p.name: {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size} for p in out.iterdir() if p.is_file()}
    (out / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print("R244_SKIN_TOPOLOGY", json.dumps({k: report[k] for k in ("status", "execution_sha", "oracle", "redundant_vertex_indices", "all_original_triangle_corners_bit_exact", "before", "after", "before_face_anomalies", "after_face_anomalies", "exact_boundary_matches", "closed_candidate_emitted")}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
