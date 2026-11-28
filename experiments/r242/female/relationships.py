"""Source-preserving diagnosis of female sacral and tibiofibular residuals.

This observes the existing candidates. No geometry is optimized or moved. Pair
distances are geometric witnesses, not physiological contact/clearance claims.
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
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "r240" / "registration"))
from ct_skin import glb, read, xform, sha, need
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "r241" / "female"))
from critic import surface_sample, sample, classify

PINS = {
    "base": "38c9d834128f18932870a799399496b1b86341a920374971af7585e676ec81c7",
    "roll": "45b6e0650ceee40acf62ee67d227aaf6b9542a3b5af6b1dceb344f02b25e5886",
    "skin": "f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f",
    "ct": "f9e0e39a5591705aa73509e4239a4a9652d57fe3bdbb010b120b5366443ede8a",
}


def around(a, b, angle):
    axis = b - a
    axis /= np.linalg.norm(axis)
    r = Rotation.from_rotvec(axis * np.radians(angle)).as_matrix()
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = a - r @ a
    return m


def stats(values):
    values = np.asarray(values)
    need(len(values) > 0 and np.isfinite(values).all(), "invalid metric values")
    return {"min": float(values.min()), "median": float(np.median(values)),
            "p95": float(np.quantile(values, .95)), "max": float(values.max())}


def plane_segments(v, f, height):
    triangles = v[f]
    offset = triangles[:, :, 1] - height
    mask = (offset.min(1) < 0) & (offset.max(1) > 0)
    triangles, offset = triangles[mask], offset[mask]
    points = [[] for _ in range(len(triangles))]
    for a, b in ((0, 1), (1, 2), (2, 0)):
        crossed = np.flatnonzero(offset[:, a] * offset[:, b] < 0)
        t = offset[crossed, a] / (offset[crossed, a] - offset[crossed, b])
        hit = triangles[crossed, a] + t[:, None] * (triangles[crossed, b] - triangles[crossed, a])
        for i, p in zip(crossed, hit):
            points[i].append(p[[0, 2]])
    return np.array([p for p in points if len(p) == 2]).reshape(-1, 2, 2)


def main(base, roll, skin, ct, out):
    paths = dict(zip(PINS, (base, roll, skin, ct)))
    need({k: sha(v.read_bytes()) for k, v in paths.items()} == PINS, "archive SHA pin")
    out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(base) as z, zipfile.ZipFile(roll) as rz, \
            zipfile.ZipFile(skin) as sz, zipfile.ZipFile(ct) as cz:
        br = json.loads(z.read("receipt.json"))
        rr = json.loads(rz.read("receipt.json"))
        cr = json.loads(cz.read("receipt.json"))
        raw = z.read("female-athletic-ct-candidate.glb")
        rraw = rz.read("female-athletic-ct-roll-candidate.glb")
        craw = cz.read("female-ct-leg-animation.glb")
        need(sha(raw) == br["glb_sha256"] and sha(rraw) == rr["candidate_glb_sha256"]
             and sha(craw) == cr["models"]["animated"], "inner GLB SHA pin")
        d, b = glb(raw)
        rd, rb = glb(rraw)
        cpu = np.load(io.BytesIO(sz.read("female-athletic-cpu-reference.npz")))
        frames, skinfaces = cpu["frames"], cpu["faces"]
        source = trimesh.load(io.BytesIO(craw), file_type="glb", force="scene", process=False)
        for n in ("LICENSE.md", "LICENSE.ASSETS.md", "ATTRIBUTION.txt"):
            (out / n).write_bytes(z.read(n))
    names = [n["name"] for n in d["nodes"][:163]]
    ix = {n: i for i, n in enumerate(names)}
    parent = {}
    for i, n in enumerate(d["nodes"]):
        for j in n.get("children", []):
            need(j not in parent, "multiple parents")
            parent[j] = i
    animation = d["animations"][0]
    tracks = {c["target"]["node"]: read(d, b, animation["samplers"][c["sampler"]]["output"])
              for c in animation["channels"]}
    worlds = []
    for key in range(3):
        w = []
        for i, n in enumerate(d["nodes"][:163]):
            m = np.eye(4)
            m[:3, :3] = Rotation.from_quat(tracks[i][key] if i in tracks else n["rotation"]).as_matrix()
            m[:3, 3] = n["translation"]
            w.append(w[parent[i]] @ m if i in parent else m)
        worlds.append(np.array(w))
    world = worlds[0]
    def joint(name):
        return world[ix[name], :3, 3]
    axes = {"root": (joint("upperleg01.R"), joint("upperleg01.L"))}
    for s in ("L", "R"):
        axes["upperleg01." + s] = (joint("upperleg01." + s), joint("lowerleg01." + s))
        axes["lowerleg01." + s] = (joint("lowerleg01." + s), joint("foot." + s))
    rolls = {g["owner"]: around(*axes[g["owner"]], g["selected_angle_deg"]) for g in rr["groups"]}
    records = {r["source"]: r for r in br["bones"]}
    bones = {}
    for ni, n in enumerate(d["nodes"]):
        if not n.get("name", "").startswith("CT_"):
            continue
        name = n["name"][3:]
        rec = records[name]
        owner = rec["owner"]
        need(names[parent[ni]] == owner, "attachment identity")
        sm, geom = source.graph[name]
        src = source.geometry[geom]
        sv = xform(src.vertices, sm)
        p = d["meshes"][n["mesh"]]["primitives"][0]
        rp = rd["meshes"][rd["nodes"][ni]["mesh"]]["primitives"][0]
        f = read(d, b, p["indices"]).reshape(-1, 3)
        need(np.array_equal(f, src.faces) and np.array_equal(f, read(rd, rb, rp["indices"]).reshape(-1, 3)), "source topology")
        v = xform(read(d, b, p["attributes"]["POSITION"]), world[ix[owner]])
        rv = xform(read(rd, rb, rp["attributes"]["POSITION"]), world[ix[owner]])
        m = np.array(rec["source_to_rig"])
        rm = rolls[owner] @ m
        err = max(np.linalg.norm(xform(sv, m) - v, axis=1).max(),
                  np.linalg.norm(xform(sv, rm) - rv, axis=1).max())
        need(err < 2e-6, "serialized source registration disagrees")
        bones[name] = {"source": sv, "baseline": v, "roll": rv, "faces": f,
                       "owner": owner, "baseline_map": m, "roll_map": rm,
                       "scale": rec["scale"], "replay_error_m": float(err)}
    need(len(bones) == 9, "nine anatomical components")
    def by_suffix(suffix):
        matches = [(n, v) for n, v in bones.items() if n.endswith("_" + suffix)]
        need(len(matches) == 1, "source suffix identity")
        return matches[0]
    # Test point-pair relationships from the actual donor, before looking at skin.
    # Nearest source vertices approximate surface distances; they are not contact
    # surfaces, do not detect intersection and cannot establish joint clearance.
    pairs = []
    specifications = []
    for side in ("LEFT", "RIGHT"):
        for region in ("proximal", "distal"):
            specifications.append(("FIBULA_" + side, "TIBIA_" + side, region, True))
        specifications.append(("SACRUM", "HIP_" + side, "whole", True))
        specifications.append(("FEMUR_" + side, "TIBIA_" + side, "distal", False))
    for first, second, region, shared in specifications:
        an, a = by_suffix(first)
        bn, bb = by_suffix(second)
        va, vb = a["source"], bb["source"]
        mask = np.ones(len(va), dtype=bool)
        if region == "proximal":
            mask = va[:, 1] >= va[:, 1].max() - .065
        elif region == "distal":
            mask = va[:, 1] <= va[:, 1].min() + .065
        ids = np.flatnonzero(mask)
        ids = ids[np.linspace(0, len(ids) - 1, min(384, len(ids)), dtype=int)]
        dd, near = cKDTree(vb).query(va[ids], k=1)
        # Retain nearest quartile as a reproducible opposing-region proxy.
        keep = dd <= np.quantile(dd, .25)
        ids, near, dd = ids[keep], near[keep], dd[keep]
        row = {"first": an, "second": bn, "region": region, "pairs": len(ids),
               "shared_owner": shared, "source_nearest_vertex_pair_mm": stats(dd * 1000)}
        for version in ("baseline", "roll"):
            ma, mb = a[version + "_map"], bb[version + "_map"]
            delta = np.linalg.norm(a[version][ids] - bb[version][near], axis=1)
            # Undo the second bone's transform for a donor-unit relationship test.
            back_a = xform(a[version][ids], np.linalg.inv(mb))
            back_b = xform(bb[version][near], np.linalg.inv(mb))
            back_dist = np.linalg.norm(back_a - back_b, axis=1)
            row[version] = {"registered_pair_mm": stats(delta * 1000),
                            "second_bone_source_frame_pair_mm": stats(back_dist * 1000),
                            "max_source_pair_change_mm": float(abs(back_dist - dd).max() * 1000),
                            "transform_max_difference": float(abs(ma - mb).max())}
            if shared:
                need(np.max(abs(ma - mb)) < 1e-12, "paired bones transformed separately")
                need(np.max(abs(back_dist - dd)) < 3e-6, "source pair relationship changed")
        pairs.append(row)
    skins = [trimesh.Trimesh(vertices=v, faces=skinfaces, process=False) for v in frames]
    need(all(s.is_watertight for s in skins), "watertight skin required")
    rows, visual = [], {}
    sample_arrays = {}
    for name, bone in bones.items():
        ids, u = surface_sample(bone["baseline"], bone["faces"])
        sourcepoints = sample(bone["source"], bone["faces"], ids, u)
        axial = (sourcepoints[:, 1] - bone["source"][:, 1].min()) / np.ptp(bone["source"][:, 1])
        axial_bin = np.minimum(3, (axial * 4).astype(int))
        for version in ("baseline", "roll"):
            fixed = sample(bone[version], bone["faces"], ids, u)
            for key in range(3):
                t = worlds[key][ix[bone["owner"]]] @ np.linalg.inv(world[ix[bone["owner"]]])
                pts = xform(fixed, t)
                measure, votes = classify(skins[key], pts)
                bins = [{"source_height_fraction": [j / 4, (j + 1) / 4],
                         "samples": int((axial_bin == j).sum()),
                         "outside": int(((axial_bin == j) & (votes == 0)).sum())} for j in range(4)]
                rows.append({"bone": name, "variant": version, "key": key, **measure,
                             "axial_regions": bins})
                if key == 0:
                    visual[name, version] = (pts, votes)
                    sample_arrays[name + "_" + version + "_points"] = pts
                    sample_arrays[name + "_" + version + "_votes"] = votes
    summary = []
    for key in range(3):
        summary.append({"key": key, **{version: {
            field: sum(r[field] for r in rows if r["key"] == key and r["variant"] == version)
            for field in ("samples", "outside", "disagreement", "outside_over_5mm", "outside_over_10mm", "outside_distance_sum_mm")}
            for version in ("baseline", "roll")}})
    # Reproduce the exact R241 corresponding area sample evaluation. This is a
    # diagnostic repeat, not a fresh independent holdout or new donor validation.
    need([r["baseline"]["outside"] for r in summary] == [367, 360, 367], "R241 baseline sample parity")
    need([r["roll"]["outside"] for r in summary] == [231, 231, 231], "R241 roll sample parity")
    fontpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = ImageFont.truetype(fontpath, 21)
    small = ImageFont.truetype(fontpath, 17)
    image = Image.new("RGB", (1500, 930), "#14212b")
    draw = ImageDraw.Draw(image)
    draw.text((24, 16), "Female CT / exterior residuals — actual registered geometry, unchanged candidate", font=font, fill="white")
    draw.text((24, 49), "Red: unanimous outside samples. Gold: inside. Fixed R241 surface samples; anatomy remains held.", font=small, fill="#becbd3")
    for col, version in enumerate(("baseline", "roll")):
        for view, axis in enumerate((0, 2)):
            left = col * 750 + view * 375
            scale, cx, cy = 610, left + 187, 815
            def project(points):
                return np.column_stack((cx + points[:, axis] * scale, cy - points[:, 1] * scale))
            xy = project(frames[0])
            draw.text((left + 18, 92), ("Initial fit" if version == "baseline" else "Roll candidate") + (" / front" if view == 0 else " / side"), font=small, fill="white")
            for tri in skinfaces:
                if frames[0][tri, 1].max() < 1.12:
                    draw.polygon([tuple(xy[i]) for i in tri], fill="#385263")
            for name, bone in bones.items():
                points, votes = visual[name, version]
                selected = "SACRUM" in name or "FIBULA" in name
                for (x, y), vote in zip(project(points), votes):
                    if not (left < x < left + 375 and 125 < y < 840):
                        continue
                    color = "#ff6f59" if vote == 0 else "#ffdb92" if selected else "#85939d"
                    r = 2 if selected else 1
                    draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
    draw.text((24, 875), "The shared sacrum/hip and tibia/fibula transforms preserve donor pair geometry; skin mismatch does not justify moving one bone alone.", font=small, fill="#d5e2ea")
    image.save(out / "female-residual-source-relations.png")
    section_image = Image.new("RGB", (1500, 720), "#14212b")
    draw = ImageDraw.Draw(section_image)
    draw.text((24, 16), "Horizontal sections at worst sampled protrusion — roll candidate", font=font, fill="white")
    draw.text((24, 49), "Blue: skin contour. Gold: CT bone contours. Red: worst exterior sample; exact nearest skin triangle distance.", font=small, fill="#becbd3")
    sections = []
    for col, suffix in enumerate(("SACRUM", "FIBULA_LEFT", "FIBULA_RIGHT")):
        name, bone = by_suffix(suffix)
        pts, votes = visual[name, "roll"]
        outside = pts[votes == 0]
        need(len(outside) > 0, "expected residual absent")
        nearest, dist, _ = trimesh.proximity.closest_point(skins[0], outside)
        index = int(np.argmax(dist))
        point, closest = outside[index], nearest[index]
        level = float(point[1])
        skin_lines = plane_segments(frames[0], skinfaces, level)
        wanted = [(n, bb) for n, bb in bones.items()
                  if bb["owner"] == bone["owner"]]
        bone_lines = [(n, plane_segments(bb["roll"], bb["faces"], level)) for n, bb in wanted]
        if suffix == "SACRUM":
            center = np.array([0., point[2]])
            span = .50
        else:
            center = bone["roll"][np.abs(bone["roll"][:, 1] - level) < .015][:, [0, 2]].mean(0)
            span = .22
        scale = 430 / span
        origin = np.array([col * 500 + 250, 360])
        def project2(points):
            return origin + (points - center) * np.array([scale, -scale])
        draw.text((col * 500 + 24, 105), suffix.replace("_", " "), font=font, fill="white")
        draw.text((col * 500 + 24, 138), f"Height {level:.3f} m / depth {dist[index] * 1000:.2f} mm", font=small, fill="#c9d5dd")
        for lines, color in [(skin_lines, "#74c6ef")] + [(lines, "#ffdb92") for _, lines in bone_lines]:
            for line in lines:
                xy = project2(line)
                if np.all((xy[:, 0] > col * 500 + 18) & (xy[:, 0] < (col + 1) * 500 - 18) & (xy[:, 1] > 178) & (xy[:, 1] < 590)):
                    draw.line([tuple(p) for p in xy], fill=color, width=2)
        p = project2(point[[0, 2]])
        draw.ellipse((p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5), fill="#ff6f59")
        draw.text((col * 500 + 24, 610), f"View: +Y toward floor; X horizontal, Z vertical", font=small, fill="#becbd3")
        sections.append({"bone": name, "height_m": level, "worst_sample_m": point.tolist(),
                         "nearest_skin_point_m": closest.tolist(), "distance_mm": float(dist[index] * 1000),
                         "skin_segments": len(skin_lines), "bone_segments": {n: len(lines) for n, lines in bone_lines},
                         "plot_span_m": span})
    draw.text((24, 675), "Sections are diagnostic slices, not clinical images. Nearest 3D skin point may be outside the slice plane.", font=small, fill="#d5e2ea")
    section_image.save(out / "female-skin-cross-sections.png")
    np.savez_compressed(out / "corresponding-surface-samples.npz", **sample_arrays)
    receipt = {
        "status": "HOLD_CROSS_DONOR_ANATOMICAL_ADMISSION", "geometry_changed": False,
        "source_sha256": PINS, "execution": {k: os.environ.get(k) for k in
            ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "SOURCE_HEAD_SHA", "RUNNER_OS", "RUNNER_ARCH")},
        "component_replay_errors_m": {n: b["replay_error_m"] for n, b in bones.items()},
        "pair_relationships": pairs, "surface_summary": summary, "surface_rows": rows,
        "sections": sections,
        "conclusions": ["Existing pelvis and paired tibia/fibula transforms retain source pair geometry within serialization tolerance.",
                        "A fibula-only or sacrum-only containment adjustment would change these verified donor relations and needs independent anatomical justification.",
                        "Cross-donor shape/pivot/pose compatibility remains unresolved; separate femur/shank mappings are measured in the shank donor frame.",
                        "Nearest vertex distances approximate surface separation and cannot establish actual cartilage, intended contact or intersection freedom."],
        "evaluation_scope": "Exact R241 area-weighted corresponding sample replay at three animation keys. Same donors and sample set, no new independence claim. No optimization or acceptance from containment.",
    }
    receipt["files"] = {p.name: {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
                        for p in out.iterdir() if p.is_file()}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("R242_FEMALE_RELATIONSHIPS", json.dumps({"status": receipt["status"], "summary": summary,
          "pairs": pairs, "sections": sections}), flush=True)


if __name__ == "__main__":
    main(*(Path(p) for p in sys.argv[1:]))
