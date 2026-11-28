"""Replay a frozen male head-fit correction against paired full-body samples.

This is cross-donor research geometry. Sphere centers are proxies, not clinical
joint centers. A lower sampled protrusion count is not anatomical acceptance.
"""
import copy
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "r241" / "male"))
from register import ATLAS, SKIN, IDS, glb, read, encode, xform, sha, need, oriented

BASE = "15c35738f128cdab948f7f727091f32875288ec3bc6a2b55dfd69d20d5ed9e31"
HEAD = "c5d667690bdf6021a9d9ae5610281b2544cc72d4b813d34a2254da1869a7c834"
RAYS = ([1, .071, .023], [-.13, .039, 1], [.09, 1, .127])


def samples(vertices, faces, count, seed):
    tri = vertices[faces]
    area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    rng = np.random.default_rng(seed)
    take = rng.choice(len(tri), count, p=area / area.sum())
    uv = rng.random((count, 2))
    uv[uv.sum(1) > 1] = 1 - uv[uv.sum(1) > 1]
    return take, uv


def points(vertices, faces, take, uv):
    tri = vertices[faces[take]]
    return tri[:, 0] + uv[:, :1] * (tri[:, 1] - tri[:, 0]) + uv[:, 1:] * (tri[:, 2] - tri[:, 0])


def exterior(mesh, sample):
    votes = np.zeros(len(sample), dtype=int)
    for direction in RAYS:
        _, ray, _ = mesh.ray.intersects_location(sample, np.tile(direction, (len(sample), 1)), multiple_hits=True)
        votes += np.bincount(ray, minlength=len(sample)) % 2
    outside = votes == 0
    distance = trimesh.proximity.closest_point(mesh, sample[outside])[1] * 1000 if outside.any() else np.array([])
    return {
        "samples": len(sample), "outside": int(outside.sum()),
        "disagreement": int(((votes > 0) & (votes < 3)).sum()),
        "outside_over_5mm": int((distance > 5).sum()),
        "outside_over_10mm": int((distance > 10).sum()),
        "max_exterior_mm": float(distance.max(initial=0)),
        "sum_exterior_mm": float(distance.sum()),
    }


def world_frames(doc, binary, parents):
    animation = doc["animations"][0]
    rotations = {}
    for channel in animation["channels"]:
        need(channel["target"]["path"] == "rotation", "unexpected motion channel")
        rotations[channel["target"]["node"]] = read(doc, binary, animation["samplers"][channel["sampler"]]["output"])
    result = []
    for key in range(3):
        frame = []
        for i, node in enumerate(doc["nodes"][:163]):
            matrix = np.eye(4)
            matrix[:3, :3] = Rotation.from_quat(rotations[i][key] if i in rotations else node["rotation"]).as_matrix()
            matrix[:3, 3] = node["translation"]
            frame.append(matrix if parents[i] < 0 else frame[parents[i]] @ matrix)
        result.append(np.array(frame))
    return np.array(result)


def write_positions(doc, binary, accessor, vertices):
    item = doc["accessors"][accessor]
    view = doc["bufferViews"][item["bufferView"]]
    need(item["componentType"] == 5126 and item["type"] == "VEC3" and item["count"] == len(vertices), "position format")
    need("byteStride" not in view and "sparse" not in item, "position storage")
    offset = view.get("byteOffset", 0) + item.get("byteOffset", 0)
    packed = np.asarray(vertices, dtype="<f4")
    binary[offset:offset + packed.nbytes] = packed.tobytes()
    item["min"], item["max"] = packed.min(0).tolist(), packed.max(0).tolist()


def main(atlas_path, skin_path, base_path, head_path, out):
    inputs = {"atlas": (atlas_path, ATLAS), "skin": (skin_path, SKIN), "baseline": (base_path, BASE), "head_patch": (head_path, HEAD)}
    for name, (path, digest) in inputs.items():
        need(sha(path.read_bytes()) == digest, "archive pin: " + name)
    out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(atlas_path) as atlas, zipfile.ZipFile(skin_path) as skin, zipfile.ZipFile(base_path) as base, zipfile.ZipFile(head_path) as head:
        inventory = {r["id"]: r for r in json.loads(atlas.read("inventory.json"))}
        source_raw = atlas.read("layers/skeletal.glb")
        need(sha(source_raw) == json.loads(atlas.read("receipt.json"))["files"]["layers/skeletal.glb"]["sha256"], "source mesh pin")
        scene = trimesh.load(io.BytesIO(source_raw), file_type="glb", force="scene", process=False)
        source = {}
        for role, (ident, label) in IDS.items():
            row = inventory[ident]
            need(label in [x[1].lower() for x in row["concepts"]], "source identity " + role)
            matrix, geometry = scene.graph[ident]
            mesh = scene.geometry[geometry].copy()
            mesh.apply_transform(matrix)
            need(len(mesh.faces) == row["triangles"] and np.max(abs(mesh.bounds - np.asarray(row["bounds_m"]))) < 2e-6, "source geometry " + role)
            source[role] = mesh
        base_receipt = json.loads(base.read("receipt.json"))
        base_raw = base.read("male-athletic-anatomical-candidate.glb")
        need(sha(base_raw) == base_receipt["glb_sha256"], "baseline model pin")
        old_doc, old_bin = glb(base_raw)
        patch = json.loads(head.read("receipt.json"))
        need(patch["source_sha256"] == ATLAS and len(patch["sides"]) == 2, "head patch source")
        rig = json.loads(skin.read("male-athletic-rig.json"))
        cpu = np.load(io.BytesIO(skin.read("male-athletic-cpu-reference.npz")))
        skin_frames, skin_faces = cpu["frames"], cpu["faces"]
        for name in ("LICENSE-source.html", "LICENSE-update.html"):
            (out / name).write_bytes(atlas.read(name))
        for name in ("LICENSE.md", "LICENSE.ASSETS.md"):
            (out / name).write_bytes(skin.read(name))
        (out / "ATTRIBUTION.txt").write_bytes(atlas.read("ATTRIBUTION.txt") + b"\nR242: fixed R241 superior-medial head-patch proxy centers replayed in the same cross-donor registration. Shape retained; anatomical admission held.\n")
    bones = rig["bones"]
    names = [row["id"] for row in bones]
    index = {name: i for i, name in enumerate(names)}
    need(len(names) == 163 and [n["name"] for n in old_doc["nodes"][:163]] == names, "rig identity")
    world = np.array([row["world_bind"] for row in bones])
    inverse = np.array([row["inverse_bind"] for row in bones])
    parents = [-1 if row["parent"] is None else index[row["parent"]] for row in bones]
    def joint(name):
        return world[index[name], :3, 3]
    records = {row["id"]: row for row in base_receipt["bones"]}
    hip, knee, center_changes = {}, {}, []
    for side in ("L", "R"):
        item = next(row for row in patch["sides"] if row["side"] == side)
        method = item["methods"]["medial_contact"]
        need(method["status"] == "FIT_CANDIDATE", "head candidate unavailable")
        hip[side] = np.array(method["center_m"])
        femur, tibia = source["femur." + side].vertices, source["tibia." + side].vertices
        distal = femur[femur[:, 1] <= femur[:, 1].min() + .04]
        distance = cKDTree(tibia).query(distal)[0]
        knee[side] = distal[distance <= np.quantile(distance, .5)].mean(0)
        old_matrix = np.array(records[IDS["femur." + side][0]]["source_to_rig"])
        old_head = xform(joint("upperleg01." + side)[None], np.linalg.inv(old_matrix))[0]
        need(np.linalg.norm(xform(knee[side][None], old_matrix)[0] - joint("lowerleg01." + side)) < 1e-8, "unchanged knee proxy")
        center_changes.append({"side": side, "old_center_m": old_head.tolist(), "new_center_m": hip[side].tolist(),
                               "shift_mm": float(np.linalg.norm(hip[side] - old_head) * 1000),
                               "head_patch_method": method, "head_patch_holdout_sha256": item["heldout_sha256"]})
    source_transverse = hip["L"] - hip["R"]
    target_transverse = joint("upperleg01.L") - joint("upperleg01.R")
    sacrum = source["sacrum"].vertices
    superior = sacrum[sacrum[:, 1] >= np.quantile(sacrum[:, 1], .85)].mean(0)
    source_mid = (hip["L"] + hip["R"]) / 2
    target_mid = (joint("upperleg01.L") + joint("upperleg01.R")) / 2
    pelvis_matrix, pelvis_scale = oriented(hip["R"], hip["L"], joint("upperleg01.R"), joint("upperleg01.L"), superior - source_mid, joint("spine01") - target_mid)
    transforms = {"pelvis": (pelvis_matrix, pelvis_scale)}
    for side in ("L", "R"):
        transforms["thigh." + side] = oriented(hip[side], knee[side], joint("upperleg01." + side), joint("lowerleg01." + side), source_transverse, target_transverse)
        row = records[IDS["tibia." + side][0]]
        transforms["shin." + side] = np.array(row["source_to_rig"]), row["scale"]
    doc, binary = copy.deepcopy(old_doc), bytearray(old_bin)
    groups, output_bones = [], []
    for role, (ident, label) in IDS.items():
        row = records[ident]
        owner = row["owner"]
        region = "pelvis" if role.startswith("hip.") or role == "sacrum" else "thigh." + role[-1] if role.startswith("femur.") else "shin." + role[-1]
        matrix, scale = transforms[region]
        mesh = source[role]
        ni = next(i for i, n in enumerate(doc["nodes"]) if n["name"] == "BP3D_" + ident)
        prim = doc["meshes"][doc["nodes"][ni]["mesh"]]["primitives"][0]
        faces = read(doc, binary, prim["indices"]).reshape(-1, 3)
        need(np.array_equal(faces, mesh.faces), "unchanged triangle correspondence")
        baseline_world = xform(read(old_doc, old_bin, prim["attributes"]["POSITION"]), world[index[owner]])
        need(np.max(np.linalg.norm(baseline_world - xform(mesh.vertices, np.asarray(row["source_to_rig"])), axis=1)) < 2e-6, "independent baseline source mapping")
        mapped = xform(mesh.vertices, matrix)
        singular = np.linalg.svd(matrix[:3, :3], compute_uv=False)
        need(np.linalg.det(matrix[:3, :3]) > 0 and np.max(abs(singular - scale)) < 1e-10, "positive isotropic shape preservation")
        write_positions(doc, binary, prim["attributes"]["POSITION"], xform(mapped, inverse[index[owner]]))
        output_bones.append({"role": role, "id": ident, "label": label, "owner": owner, "triangles": len(faces), "old_scale": row["scale"], "scale": scale, "source_to_rig": matrix.tolist()})
        groups.append({"role": role, "id": ident, "owner": owner, "node": ni, "primitive": prim, "faces": faces, "mapped": mapped})
    packed = encode(doc, binary)
    model_path = out / "male-athletic-refined-candidate.glb"
    model_path.write_bytes(packed)
    doc, binary = glb(packed)
    need(old_doc["nodes"] == doc["nodes"] and old_doc["skins"] == doc["skins"] and old_doc["animations"] == doc["animations"], "unchanged rig and clip structure")
    # Check every original accessor except the nine intentionally edited positions.
    edited = {g["primitive"]["attributes"]["POSITION"] for g in groups}
    for ai in range(len(old_doc["accessors"])):
        if ai not in edited:
            need(np.array_equal(read(old_doc, old_bin, ai), read(doc, binary, ai)), "unchanged non-bone accessor " + str(ai))
    globals_at = world_frames(doc, binary, parents)
    model_views, max_transport = {}, 0.0
    for variant, (d, b) in {"baseline": (old_doc, old_bin), "refined": (doc, binary)}.items():
        for key in range(3):
            view = {}
            for group in groups:
                owner_index = index[group["owner"]]
                v = xform(read(d, b, group["primitive"]["attributes"]["POSITION"]), globals_at[key, owner_index])
                view[group["role"]] = v
                if variant == "refined":
                    expected = xform(group["mapped"], globals_at[key, owner_index] @ inverse[owner_index])
                    max_transport = max(max_transport, float(np.max(np.linalg.norm(v - expected, axis=1))))
            model_views[(variant, key)] = view
    need(max_transport < 2e-6, "serialized bone transport")
    # Fresh paired sample manifest is generated ONCE from the source geometry,
    # then reused without resampling for both candidates and all animation keys.
    paired, manifest, sample_arrays = {}, [], {}
    for group in groups:
        role = group["role"]
        take, uv = samples(source[role].vertices, group["faces"], 512, 24201)
        paired[role] = take, uv
        sample_hash = sha(np.asarray(take, dtype="<i8").tobytes() + np.asarray(uv, dtype="<f8").tobytes())
        manifest.append({"role": role, "samples": len(take), "face_barycentric_sha256": sample_hash})
        sample_arrays[role + "_face"] = take
        sample_arrays[role + "_uv"] = uv
    np.savez_compressed(out / "paired-surface-samples.npz", **sample_arrays)
    rows, legacy = [], []
    for key in range(3):
        skin_mesh = trimesh.Trimesh(vertices=skin_frames[key], faces=skin_faces, process=False)
        need(skin_mesh.is_watertight, "watertight exterior")
        for variant in ("baseline", "refined"):
            for group in groups:
                role, faces = group["role"], group["faces"]
                v = model_views[(variant, key)][role]
                rows.append({"variant": variant, "key": key, "role": role, **exterior(skin_mesh, points(v, faces, *paired[role]))})
                if variant == "baseline":
                    legacy.append({"key": key, "role": role, **exterior(skin_mesh, points(v, faces, *samples(v, faces, 256, 241)))})
    legacy_totals = [sum(r["outside"] for r in legacy if r["key"] == k) for k in range(3)]
    need(legacy_totals == [r["outside"] for r in base_receipt["summary"]], "legacy R241 replay count")
    summaries = []
    for variant in ("baseline", "refined"):
        for key in range(3):
            selected = [r for r in rows if r["variant"] == variant and r["key"] == key]
            summary = {"variant": variant, "key": key}
            for name in ("samples", "outside", "disagreement", "outside_over_5mm", "outside_over_10mm", "sum_exterior_mm"):
                summary[name] = sum(r[name] for r in selected)
            summary["max_exterior_mm"] = max(r["max_exterior_mm"] for r in selected)
            summaries.append(summary)
    # Surface separation is a separate unsigned, one-way geometry diagnostic.
    # Same actual proximal femur triangles are compared before/after registration;
    # it does not infer contact, cartilage thickness or collision-free joints.
    joint_rows = []
    for side in ("L", "R"):
        role = "femur." + side
        mesh = source[role]
        take, uv = paired[role]
        source_points = points(mesh.vertices, mesh.faces, take, uv)
        keep = source_points[:, 1] >= mesh.vertices[:, 1].max() - .065
        need(int(keep.sum()) >= 10, "hip surface sample coverage")
        source_dist = trimesh.proximity.closest_point(source["hip." + side], source_points[keep])[1] * 1000
        joint_rows.append({"variant": "donor_source", "key": None, "side": side, "samples": int(keep.sum()), "mean_surface_distance_mm": float(source_dist.mean()), "max_surface_distance_mm": float(source_dist.max())})
        for variant in ("baseline", "refined"):
            for key in range(3):
                view = model_views[(variant, key)]
                hip_mesh = trimesh.Trimesh(vertices=view["hip." + side], faces=source["hip." + side].faces, process=False)
                p = points(view[role], mesh.faces, take, uv)[keep]
                distance = trimesh.proximity.closest_point(hip_mesh, p)[1] * 1000
                joint_rows.append({"variant": variant, "key": key, "side": side, "samples": len(p), "mean_surface_distance_mm": float(distance.mean()), "max_surface_distance_mm": float(distance.max())})
    image = Image.new("RGB", (1600, 1040), "#14232f")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19)
    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 25)
    draw.text((24, 12), "Male source-patch replay | actual geometry, unchanged exterior and animation", font=title_font, fill="white")
    draw.text((24, 48), "9 male atlas bones; cross-donor candidate. Surface and joint anatomy remain unqualified.", font=font, fill="#c4d3de")
    for col, (variant, axis) in enumerate((("baseline", 0), ("refined", 0), ("baseline", 2), ("refined", 2))):
        for row, key in enumerate((0, 1)):
            cx, foot_y, scale = col * 400 + 200, 490 + row * 460, 205
            def project(v):
                return np.column_stack((cx + v[:, axis] * scale, foot_y - v[:, 1] * scale))
            draw.text((col * 400 + 20, 88 + row * 460), variant.title() + (" / front" if axis == 0 else " / side") + (" / rest" if key == 0 else " / pose"), font=font, fill="white")
            xy = project(skin_frames[key])
            for face in skin_faces:
                draw.polygon([tuple(xy[i]) for i in face], fill="#455e70")
            for group in groups:
                xy = project(model_views[(variant, key)][group["role"]])
                for face in group["faces"]:
                    draw.polygon([tuple(xy[i]) for i in face], fill="#efce95")
    draw.text((24, 1002), "Fixed camera geometry overlay; see the independent Blender witness for consumer rendering.", font=font, fill="#c4d3de")
    image.save(out / "male-refined-registration-comparison.png")
    receipt = {
        "status": "HOLD_CROSS_DONOR_ANATOMICAL_ADMISSION", "execution_sha": os.environ.get("EXECUTION_SHA"),
        "workflow_sha": os.environ.get("WORKFLOW_SHA"),
        "input_sha256": {name: digest for name, (_, digest) in inputs.items()},
        "glb_sha256": sha(packed), "bones": output_bones, "head_center_changes": center_changes,
        "transport_max_m": max_transport, "all_other_accessors_preserved": True,
        "legacy_R241_256_samples_per_bone_replay_outside": legacy_totals,
        "paired_sample_manifest": manifest, "paired_sample_archive_sha256": sha((out / "paired-surface-samples.npz").read_bytes()),
        "paired_surface_results": rows, "summary": summaries, "hip_surface_distance_diagnostic": joint_rows,
        "scope": "Fixed R241 superior-medial head centers, unchanged knee and shin recipe, source-based paired area samples reused across candidates and keys. Aggregate counts weight every bone equally, not by bone area or anatomical volume. Nearest triangle distance only for unanimous exterior points; disagreement reported. Separate unsigned proximal surface distance is not a contact or collision oracle. No containment tuning, muscle/organ/clinical/native qualification, or anatomical acceptance. Reduced atlas and cross-donor shape remain limitations.",
    }
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("R242_MALE", json.dumps({"status": receipt["status"], "execution_sha": receipt["execution_sha"], "glb_sha256": receipt["glb_sha256"], "legacy_outside": legacy_totals, "summary": summaries, "head_center_changes": center_changes}), flush=True)


if __name__ == "__main__":
    main(*(Path(p) for p in sys.argv[1:]))
