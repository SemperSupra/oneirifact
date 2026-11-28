"""Pinned Diffeomorphic captured-motion baseline on exact morphology-first rigs.

Run with Blender --background --python witness.py -- CASE_OUT SELECTED_DIR ADDON_DIR CAPTURE_ID.
This deliberately uses the donor's CAnimation API with explicit mappings and
reference matrices. No automatic rig/T-pose guesses or motion cleanup run.
"""
import copy
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "r245" / "consumer"))
from bvh_oracle import parse as parse_bvh, fk, controls
from gltf import parse, read, add, encode, sha, worlds

args = sys.argv[sys.argv.index("--") + 1:]
OUT, SELECTED, ADDON = map(Path, args[:3])
CAPTURE = args[3]
QUICK = "--quick" in args
DONOR_COMMIT = "8501d53f66fffa8d2574a01532c30e195c8d2998"
CAPTURE_SHA = {"07_01": "f8d82ea6ed1aab0cb7d9ee680f476b65471e2322e1da84add8a8527a2cb0b9a2", "13_01": "f9e1fa1da61569a14ca8ecd7bd7782e02a55e6189351148e958c9b75ab89889f"}
SOURCE = parse_bvh(SELECTED / (CAPTURE + ".bvh"))
assert SOURCE["sha256"] == CAPTURE_SHA[CAPTURE]
ORACLES = controls()
CASE = json.loads((OUT / "case.json").read_text())
DOC, BIN = parse((OUT / "bound-source.glb").read_bytes())
SOURCE_WORLD, PARENTS = worlds(DOC)
NAMES = [node["name"] for node in DOC["nodes"][:163]]
INDEX = {name: i for i, name in enumerate(NAMES)}
C = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
CI = C.inverted()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def log(tag, value):
    print("R247_" + tag, json.dumps(value, allow_nan=False), flush=True)


def update():
    bpy.context.view_layer.update()


def cv(point):
    return [float(point[0]), float(point[2]), float(-point[1])]


def bv(point):
    return Vector((point[0], -point[2], point[1]))


def qxy(q):
    return [float(q.x), float(q.y), float(q.z), float(q.w)]


def angle(a, b):
    qa, qb = a.to_quaternion(), b.to_quaternion()
    return float(2 * math.acos(min(1.0, abs(sum(x * y for x, y in zip(qa, qb))))))


def evaluated(obj):
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    data = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", data)
    data = data.reshape(-1, 3)
    mat = np.array(ev.matrix_world)
    result = data @ mat[:3, :3].T + mat[:3, 3]
    ev.to_mesh_clear()
    return result


def nearest(a, b, count=2048):
    def one(a, b):
        tree = KDTree(len(b))
        for i, point in enumerate(b):
            tree.insert(Vector(point), i)
        tree.balance()
        indices = np.linspace(0, len(a) - 1, min(count, len(a)), dtype=int)
        return max(tree.find(Vector(a[i]))[2] for i in indices)
    return max(one(a, b), one(b, a))


def curves(action):
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    return [fc for layer in action.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 120
scene.render.fps_base = 120 * SOURCE["frame_time_s"]
bpy.ops.import_scene.gltf(filepath=str(OUT / "bound-source.glb"))
rig = next(obj for obj in scene.objects if obj.type == "ARMATURE")
rig.name = "Target exact 163 bone " + CASE["id"]
skin = next(obj for obj in scene.objects if obj.type == "MESH" and any(m.type == "ARMATURE" for m in obj.modifiers))
skin.name = "Target original full-weight exterior"
assert len(rig.data.bones) == 163 and set(rig.data.bones.keys()) == set(NAMES)
assert len(skin.data.vertices) == 13380 and len(skin.data.polygons) == 26756
for pb in rig.pose.bones:
    pb.rotation_mode = "QUATERNION"
    assert not any(pb.lock_rotation) and not pb.constraints, "Unexpected locked or constrained source target"
    if pb.custom_shape:
        pb.custom_shape.hide_render = True
        pb.custom_shape.hide_set(True)
REST = {name: rig.matrix_world @ rig.data.bones[name].matrix_local for name in NAMES}
REST_INV = {name: mat.inverted() for name, mat in REST.items()}
RIG_INV = rig.matrix_world.inverted()


def world(name):
    return rig.matrix_world @ rig.pose.bones[name].matrix


def position(name):
    return world(name).translation.copy()


def pose(name, mat):
    rig.pose.bones[name].matrix = RIG_INV @ mat
    update()


attrs = DOC["meshes"][0]["primitives"][0]["attributes"]
source_vertices = read(DOC, BIN, attrs["POSITION"])
source_indices = np.concatenate([read(DOC, BIN, attrs["JOINTS_" + str(i)]) for i in range(3)], axis=1)
source_weights = np.concatenate([read(DOC, BIN, attrs["WEIGHTS_" + str(i)]) for i in range(3)], axis=1)
inverse_bind = read(DOC, BIN, DOC["skins"][0]["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
import_error = nearest(evaluated(skin), source_vertices[:, [0, 2, 1]] * np.array([1, -1, 1]), 13380)
assert import_error < 5e-6

# Uniform coordinate conversion only. The selected BVH does not name a physical
# unit. Match its left anatomical thigh span to this already morphed target.
source_names = [node["name"] for node in SOURCE["nodes"]]
source_index = {name: i for i, name in enumerate(source_names)}
native_thigh = float(np.linalg.norm(SOURCE["nodes"][source_index["LeftLeg"]]["offset"]))
target_thigh = (REST["lowerleg01.L"].translation - REST["upperleg01.L"].translation).length
SCALE = target_thigh / native_thigh
sys.path.insert(0, str(ADDON.parent))
import retarget_bvh
retarget_bvh.register()
from retarget_bvh.bsettings import BD, mcpRna
from retarget_bvh.load import BvhLoader
from retarget_bvh.retarget import CAnimation
from retarget_bvh.source import CRigInfo
from retarget_bvh.utils import setInterpolation
BD.prefs = SimpleNamespace(useLimits=False, useUnlock=False, ignoreLeafBones=False, verbose=False, useBlenderBvh=False, useNativeFbx=False)
loader = BvhLoader()
for key, value in {"scale": SCALE, "orientation": "Manual", "axis_forward": "-Z", "axis_up": "Y", "ssFactor": 1, "useDefaultSS": False, "useAllFrames": True, "startFrame": 0, "endFrame": 999999}.items():
    setattr(loader, key, value)
src = loader.loadPluginBvhFile(bpy.context, str(SELECTED / (CAPTURE + ".bvh")))
src.name = "CMU selected " + CAPTURE + " uniformly scaled source"
bpy.ops.object.mode_set(mode="OBJECT")
setInterpolation(src)
assert all(name in src.pose.bones for name in source_names)
src_rest = {name: src.data.bones[name].matrix_local.copy() for name in source_names}

# Explicit map. Intermediate .02 limb bones, fingers and facial bones are not
# solved independently. They retain their exact parent-relative bind transforms.
mapping = {"root": "Hips", "spine05": "LowerBack", "spine03": "Spine", "spine01": "Spine1", "neck01": "Neck", "neck03": "Neck1", "head": "Head"}
for side, word in (("L", "Left"), ("R", "Right")):
    for target, source in (("clavicle", "Shoulder"), ("upperarm01", "Arm"), ("lowerarm01", "ForeArm"), ("wrist", "Hand"), ("upperleg01", "UpLeg"), ("lowerleg01", "Leg"), ("foot", "Foot")):
        mapping[target + "." + side] = word + source
mapping = {name: mapping[name] for name in NAMES if name in mapping}
assert len(mapping) == 21 and all(name in src.pose.bones for name in mapping.values())
for pb in rig.pose.bones:
    mcpRna(pb).Bone = mapping.get(pb.name, "")
    parent = pb.parent
    while parent and parent.name not in mapping:
        parent = parent.parent
    mcpRna(pb).Parent = parent.name if parent else ""
info = CRigInfo(scene, "R247 explicitly mapped source to exact 163-bone rig")
info.bones = list(mapping.items())

# The publisher's first frame is the empirical reference pose, not capture.
# Build a separate target T-pose in pose space, leaving source bind and geometry
# untouched: anatomical limb vectors become horizontal arms / vertical legs.
scene.frame_set(1)
for side, sign in (("L", 1), ("R", -1)):
    for part, endpoint, direction in (("upperleg01", "lowerleg01", (0, 0, -1)), ("lowerleg01", "foot", (0, 0, -1)), ("upperarm01", "lowerarm01", (sign, 0, 0)), ("lowerarm01", "wrist", (sign, 0, 0))):
        name, child = part + "." + side, endpoint + "." + side
        anchor = position(name)
        delta = (position(child) - anchor).rotation_difference(Vector(direction)).to_matrix().to_4x4()
        pose(name, Matrix.Translation(anchor) @ delta @ Matrix.Translation(-anchor) @ world(name))
    foot = "foot." + side
    flat = REST[foot].copy()
    flat.translation = position(foot)
    pose(foot, flat)
target_tpose = {name: {"basis_rotation_xyzw": qxy(rig.pose.bones[name].matrix_basis.to_quaternion()), "world_head_m": cv(position(name))} for name in NAMES}
for name in mapping:
    pb = rig.pose.bones[name]
    pb.keyframe_insert("rotation_quaternion", frame=1, group=name)
    if name == "root":
        pb.keyframe_insert("location", frame=1, group=name)
anim = CAnimation(src, rig, info, bpy.context)
for banim in anim.boneAnims.values():
    banim.getTPoseMatrix()
assert len(anim.boneAnims) == len(mapping)
alignment = {name: np.array(banim.aMatrix).tolist() for name, banim in anim.boneAnims.items()}
save("reference-and-map.json", {"schema": "oneirifact.captured-motion-reference/v1", "source_reference": "Publisher-added empirical first frame; not measured capture", "source_reference_bvh_row": 0, "target_reference": "Explicit anatomical-vector T-pose in pose space; source bind geometry untouched", "target_reference_pose": target_tpose, "mapped_target_source": mapping, "reference_rotation_alignment": alignment, "donor_api": "Pinned CAnimation/CBoneAnim direct API; getTPoseMatrix then retarget", "unused_source_joints": [name for name in source_names if name not in mapping.values()], "unmapped_target_bones": [name for name in NAMES if name not in mapping], "uniform_scale_m_per_source_unit": SCALE, "source_length_units": "UNESTABLISHED_NATIVE_UNIT", "source_thigh_native_units": native_thigh, "target_thigh_m": target_thigh, "cleanup": {key: False for key in ("auto_rig_mapping", "auto_tpose", "auto_scale", "center_animation", "normalize_source", "bend_positive", "simplify", "time_scale", "loop_conversion", "contact_correction")}})

frames = list(range(2, SOURCE["frame_count"] + 1))
if QUICK:
    frames = frames[:min(61, len(frames))]
log("RETARGET_START", {"capture": CAPTURE, "case": CASE["id"], "captured_frames": len(frames), "mapping_pairs": len(mapping), "blender": bpy.app.version_string, "scale": SCALE})
anim.retarget(frames, bpy.context, 0, len(frames))
setInterpolation(rig)
rig.animation_data.action.name = "CMU " + CAPTURE + " donor baseline " + CASE["id"]
rig.animation_data.action.use_fake_user = True

intermediates = [name for name in NAMES if name.startswith(("upperleg02.", "lowerleg02.", "upperarm02.", "lowerarm02."))]
reference_relative = {name: REST[rig.data.bones[name].parent.name].inverted() @ REST[name] for name in intermediates}
markers = {side: {region: Vector(CASE["morphology"]["ankles_m"][side]) + Vector(CASE["morphology"]["feet"][side][region + "_from_ankle_m"]) for region in ("heel", "forefoot", "toe")} for side in ("L", "R")}
source_max_error = 0.0
source_max_rotation = 0.0
length_error = 0.0
intermediate_error = 0.0
rows, W_all, times, checks = [], [], [], []
reference_samples = {}
sample_frames = {frames[0], frames[len(frames) // 2], frames[-1]}


def target_worlds():
    return np.array([np.array(CI @ world(name) @ REST_INV[name] @ C) @ SOURCE_WORLD[i] for i, name in enumerate(NAMES)])


def cpu_skin(W):
    skinning = W @ inverse_bind
    points = np.column_stack((source_vertices, np.ones(len(source_vertices))))
    result = np.zeros((len(points), 4))
    for slot in range(source_weights.shape[1]):
        result += np.einsum("nij,nj->ni", skinning[source_indices[:, slot]], points) * source_weights[:, slot, None]
    return result[:, :3][:, [0, 2, 1]] * np.array([1, -1, 1])


for frame in frames:
    scene.frame_set(frame)
    update()
    expected = fk(SOURCE, frame - 1, SCALE)
    source_points, source_rotations = {}, {}
    for i, name in enumerate(source_names):
        actual = src.pose.bones[name].matrix
        source_points[name] = cv(actual.translation)
        source_max_error = max(source_max_error, float(np.linalg.norm(np.array(source_points[name]) - expected[i, :3, 3])))
        observed_rot = CI @ actual @ src_rest[name].inverted() @ C
        # Normalize the float32 native quaternion before angle comparison.
        observed = np.array(observed_rot.to_quaternion().normalized().to_matrix())
        source_max_rotation = max(source_max_rotation, float(np.max(abs(observed - expected[i, :3, :3]))))
    target = {}
    for side, word in (("L", "Left"), ("R", "Right")):
        joints = {part: cv(position(name + "." + side)) for part, name in (("hip", "upperleg01"), ("knee", "lowerleg01"), ("ankle", "foot"), ("shoulder", "upperarm01"), ("elbow", "lowerarm01"), ("wrist", "wrist"))}
        foot_delta = world("foot." + side) @ REST_INV["foot." + side]
        target[side] = {**joints, **{region: cv(foot_delta @ bv(point)) for region, point in markers[side].items()}}
        for a, b in (("upperleg01", "lowerleg01"), ("lowerleg01", "foot"), ("upperarm01", "lowerarm01"), ("lowerarm01", "wrist")):
            length_error = max(length_error, abs((position(a + "." + side) - position(b + "." + side)).length - (REST[a + "." + side].translation - REST[b + "." + side].translation).length))
    for name in intermediates:
        relative = world(rig.data.bones[name].parent.name).inverted() @ world(name)
        intermediate_error = max(intermediate_error, float(np.max(abs(np.array(relative.to_3x3()) - np.array(reference_relative[name].to_3x3())))))
    ti = (frame - 2) * SOURCE["frame_time_s"]
    rows.append({"time_s": ti, "bvh_row": frame - 1, "source_joint_heads_m": source_points, "target": target, "target_root_m": cv(position("root"))})
    W = target_worlds()
    W_all.append(W)
    times.append(ti)
    if frame in sample_frames:
        actual_skin = evaluated(skin)
        error = nearest(actual_skin, cpu_skin(W))
        checks.append({"stage": "native_vs_independent_full_weight_lbs", "time_s": ti, "max_error_m": error})
        reference_samples[ti] = actual_skin
    if (frame - frames[0]) % 500 == 0:
        log("OBSERVATION_PROGRESS", {"frame": frame, "source_fk_error_m": source_max_error})
assert source_max_error < 5e-5 and source_max_rotation < 2e-5, "Native donor import diverged from independent BVH oracle"
assert length_error < 2e-5 and intermediate_error < 2e-5, "Retarget distorted an anatomical limb or an intermediate bind transform"
assert max(check["max_error_m"] for check in checks) < 5e-5
save("capture-observations.json", {"schema": "oneirifact.captured-motion-observations/v1", "capture": CAPTURE, "case_id": CASE["id"], "frame_time_s": SOURCE["frame_time_s"], "sample_scope": "All selected capture frames, excluding publisher reference row", "coordinates": "metres after declared uniform normalization; +Y up, +Z forward", "source_ground_truth_contact": "UNAVAILABLE", "target_markers": "Fixed original skin-derived foot reference points transported by actual foot bone; not mocap contact labels", "rows": rows})

# Bake to the original hierarchy; every source attribute and every skin influence
# remains byte-identical. Observed native transforms are the animation authority.
d, b = copy.deepcopy(DOC), bytearray(BIN)
sample_input = add(d, b, np.array(times, dtype="<f4").reshape(-1, 1), kind="SCALAR", bounds=True)
animation = {"name": "CMU_" + CAPTURE + "_donor_baseline", "samplers": [], "channels": []}
W_all = np.array(W_all)
for i in range(163):
    local = np.array([np.linalg.inv(W[PARENTS[i]]) @ W[i] if i in PARENTS and PARENTS[i] < 163 else W[i] for W in W_all])
    rotations = np.array([qxy(Matrix(mat.tolist()).to_quaternion()) for mat in local])
    for j in range(1, len(rotations)):
        if rotations[j - 1] @ rotations[j] < 0:
            rotations[j] *= -1
    for path, values, kind in (("translation", local[:, :3, 3], "VEC3"), ("rotation", rotations, "VEC4")):
        output = add(d, b, values.astype("<f4"), kind=kind)
        animation["channels"].append({"sampler": len(animation["samplers"]), "target": {"node": i, "path": path}})
        animation["samplers"].append({"input": sample_input, "output": output, "interpolation": "LINEAR"})
d["animations"] = [animation]
d["asset"]["generator"] = "Oneirifact R247 pinned Diffeomorphic captured-motion baseline on exact full-weight source"
packed = encode(d, b)
(OUT / "captured-motion-baseline.glb").write_bytes(packed)
dd, bb = parse(packed)
packed_attrs = dd["meshes"][0]["primitives"][0]["attributes"]
assert all(np.array_equal(read(dd, bb, packed_attrs[key]), read(DOC, BIN, attrs[key])) for key in attrs)
assert np.array_equal(read(dd, bb, dd["meshes"][0]["primitives"][0]["indices"]), read(DOC, BIN, DOC["meshes"][0]["primitives"][0]["indices"]))
assert dd["skins"] == DOC["skins"] and len(dd["skins"][0]["joints"]) == 163
export = {"sha256": sha(packed), "bytes": len(packed), "source_attributes_and_indices_bit_identical": True, "skin_and_inverse_bind_accessors_unchanged": True, "bones": 163, "captured_frames": len(times), "duration_s": times[-1], "native_frame_formula": "2 + time_s / exact_BVH_frame_time", "reference_frame_exported_as_capture": False}
log("NATIVE_COMPLETE", {"source_position_error_m": source_max_error, "source_rotation_element_error": source_max_rotation, "limb_length_error_m": length_error, "intermediate_rotation_element_error": intermediate_error, "export_bytes": len(packed)})
save("native-preflight.json", {"status": "LOCAL_DIAGNOSTIC_ONLY" if QUICK else "NATIVE_CAPTURE_COMPUTED", "blender_version": bpy.app.version_string, "source_position_error_m": source_max_error, "source_rotation_element_error": source_max_rotation, "limb_length_error_m": length_error, "intermediate_rotation_element_error": intermediate_error, "export": export, "checks": checks})
if QUICK:
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "local-donor-probe.blend"), compress=True)
    sys.exit(0)

# Native scene: the rendered orange stick skeleton is generated from the actual
# source armature, with full rigid bone weights. Only its display offset changes.
def material(name, color):
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    value.diffuse_color = (*color, 1)
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = .6
    return value


skin.data.materials.clear()
skin.data.materials.append(material("Target original exterior teal", (.16, .48, .55)))
for poly in skin.data.polygons:
    poly.use_smooth = True
verts, faces, groups = [], [], {}
for bone in src.data.bones:
    if bone.length < 1e-5:
        continue
    start = len(verts)
    radius = .008
    for y in (0, bone.length):
        for i in range(6):
            point = bone.matrix_local @ Vector((radius * math.cos(math.tau * i / 6), y, radius * math.sin(math.tau * i / 6)))
            verts.append(tuple(point))
    for i in range(6):
        a, b, c, e = start + i, start + (i + 1) % 6, start + (i + 1) % 6 + 6, start + i + 6
        faces.extend(((a, b, c), (a, c, e)))
    groups[bone.name] = list(range(start, start + 12))
mesh = bpy.data.meshes.new("Actual BVH rest skeleton sticks")
mesh.from_pydata(verts, [], faces)
mesh.update()
sticks = bpy.data.objects.new("Original capture source skeleton DISPLAY OFFSET ONLY", mesh)
scene.collection.objects.link(sticks)
sticks.data.materials.append(material("Measured source skeleton orange", (.95, .38, .09)))
for name, ids in groups.items():
    group = sticks.vertex_groups.new(name=name)
    group.add(ids, 1., "REPLACE")
modifier = sticks.modifiers.new("Actual original BVH armature", "ARMATURE")
modifier.object = src
display_offset = Vector((-1.15, 0, 0))
src.location += display_offset
sticks.location += display_offset

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 12
scene.cycles.use_denoising = bpy.app.version >= (5, 2, 0)
scene.cycles.max_bounces = 2
scene.render.resolution_x = 640
scene.render.resolution_y = 480
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.world = bpy.data.worlds.new("Neutral capture review world")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (.055, .075, .105, 1)
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .55
scene.view_settings.view_transform = "AgX"


def look(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()


bpy.ops.object.camera_add()
camera = bpy.context.object
camera.name = "Captured source and morphed target comparison"
camera.data.type = "ORTHO"
camera.data.ortho_scale = 3.4 if CASE["morphology"]["stature_m"] < 1.7 else 3.8
scene.camera = camera
lights = []
for offset, power, size in (((3, -4, 5), 650, 4), ((-3, -1, 3), 400, 3), ((1, 4, 3), 600, 3)):
    bpy.ops.object.light_add(type="AREA")
    obj = bpy.context.object
    obj.data.energy, obj.data.shape, obj.data.size = power, "DISK", size
    lights.append((obj, Vector(offset)))
render_dir = OUT / "render-frames"
render_dir.mkdir(exist_ok=True)
video_fps = 12 if CAPTURE == "07_01" else 6
render_times = np.arange(math.floor(times[-1] * video_fps) + 1) / video_fps
render_manifest = []
for i, ti in enumerate(render_times):
    native_frame = 2 + float(ti) / SOURCE["frame_time_s"]
    scene.frame_set(math.floor(native_frame), subframe=native_frame % 1)
    update()
    center = position("root") + display_offset / 2 + Vector((0, 0, .12))
    camera.location = center + Vector((1.2, -6, 1.2))
    look(camera, center)
    for obj, offset in lights:
        obj.location = center + offset
        look(obj, center)
    path = render_dir / (str(i).zfill(4) + ".png")
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    render_manifest.append({"file": str(path.relative_to(OUT)), "time_s": float(ti), "native_frame": native_frame, "sha256": sha(path.read_bytes())})
save("render-manifest.json", {"schema": "oneirifact.captured-motion-render/v1", "fps": video_fps, "frames": render_manifest, "duration_s": len(render_manifest) / video_fps, "source_display_offset_blender_m": list(display_offset), "render_scope": "Actual native source armature and retargeted exact exterior at indicated capture time; fixed camera follows translation only", "ground_plane": "NONE; foot-ground calibration is not inferred", "capture_interval_endpoint_not_retimed": True})

scene.frame_start, scene.frame_end = 2, frames[-1]
scene.frame_set(2)
native_path = OUT / "captured-motion-baseline.blend"
rig_name, skin_name = rig.name, skin.name
bpy.ops.wm.save_as_mainfile(filepath=str(native_path), compress=True)
bpy.ops.wm.open_mainfile(filepath=str(native_path))
scene = bpy.context.scene
rig, skin = bpy.data.objects[rig_name], bpy.data.objects[skin_name]
for ti, expected in reference_samples.items():
    native_frame = 2 + ti / SOURCE["frame_time_s"]
    scene.frame_set(math.floor(native_frame), subframe=native_frame % 1)
    update()
    checks.append({"stage": "saved_blend_reopened", "time_s": ti, "max_error_m": nearest(evaluated(skin), expected)})

# Independent standard importer. Its action starts at frame 1 and uses scene FPS.
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 120
# Standard glTF seconds use fractional keys at an ordinary 120 fps. The native
# capture .blend above retains exact BVH fps_base. Avoid the importer's differing
# fps_base convention instead of changing the captured time values.
scene.render.fps_base = 1
bpy.ops.import_scene.gltf(filepath=str(OUT / "captured-motion-baseline.glb"))
rig = next(obj for obj in scene.objects if obj.type == "ARMATURE")
skin = next(obj for obj in scene.objects if obj.type == "MESH" and any(m.type == "ARMATURE" for m in obj.modifiers))
assert len(rig.data.bones) == 163
ad = rig.animation_data
if ad and not ad.action:
    candidates = []
    for track in ad.nla_tracks:
        track.mute = True
        for strip in track.strips:
            if strip.action:
                candidates.append((strip.action, getattr(strip, "action_slot", None)))
    assert len(candidates) == 1
    action, slot = candidates[0]
    ad.action = action
    if slot is not None:
        ad.action_slot = slot
assert ad and ad.action
first_frame = float(ad.action.frame_range[0])
for ti, expected in reference_samples.items():
    frame = first_frame + ti * scene.render.fps / scene.render.fps_base
    scene.frame_set(math.floor(frame), subframe=frame % 1)
    update()
    checks.append({"stage": "exported_glb_reimported", "time_s": ti, "max_error_m": nearest(evaluated(skin), expected)})
worst = max(check["max_error_m"] for check in checks)
assert worst < 5e-5, "Native/save/reimport transport exceeded 50 micrometres"
receipt = {"schema": "oneirifact.captured-motion-baseline-receipt/v1", "status": "PASS_NATIVE_DONOR_TRANSPORT", "retarget_acceptance": "HOLD_CONTACT_AND_MORPHOLOGY_REVIEW", "realism": "NOT_QUALIFIED", "case": CASE, "capture": CAPTURE, "capture_sha256": SOURCE["sha256"], "captured_rows": [1, SOURCE["frame_count"] - 1], "publisher_reference_row": 0, "source_head_commit": os.environ.get("SOURCE_HEAD_SHA"), "run_id": os.environ.get("GITHUB_RUN_ID"), "blender_version": bpy.app.version_string, "retargeter": {"repository": "https://github.com/Diffeomorphic/retarget_bvh", "tag": "version_5_2_0", "commit": DONOR_COMMIT, "license": "GPL-2.0-or-later", "integration": "Explicit direct CAnimation/CBoneAnim API; not automatic MakeHuman mapping"}, "source_normalization": {"scale_m_per_native_unit": SCALE, "method": "Uniform left anatomical thigh length ratio only", "time_scale": 1, "native_frame_time_s": SOURCE["frame_time_s"], "root_centering": False}, "source_fk_oracle": {"all_capture_frames": True, "max_joint_head_error_m": source_max_error, "max_rotation_element_error": source_max_rotation, "analytic_controls": ORACLES}, "target_rig": {"max_anatomical_limb_length_error_m": length_error, "max_intermediate_relative_rotation_element_error": intermediate_error, "bind_edit": False}, "export": export, "checks": checks, "worst_transport_error_m": worst, "transport_tolerance_m": 5e-5, "body_and_footwear": "Exact source exterior, no shoe model in this donor baseline; preparation case IDs are inherited identifiers", "render": {"fps": video_fps, "frames": len(render_manifest), "source_display_offset_m": [-1.15, 0, 0]}, "limitations": ["CMU captures have no supplied ground/contact labels in selected BVH; derived stance episodes are provisional", "Uniform stature pair only; not diverse regional morphology or footwear qualification", "No contact correction, seat fitting, physical balance, forces, joint limits or self-intersection acceptance", "No captured finger grip or physiological/soft-tissue behavior established", "Publisher empirical T-pose is a reference, not measured capture", "The selected capture is not forced into a loop or retimed", "Source and converted data may not be directly resold; preserve CMU and conversion notices"], "files": {}}
for path in sorted(OUT.iterdir()):
    if path.is_file() and path.name != "capture-receipt.json":
        receipt["files"][path.name] = {"bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
save("capture-receipt.json", receipt)
log("COMPLETE", {"case": CASE["id"], "capture": CAPTURE, "status": receipt["status"], "worst_transport_error_m": worst, "rendered_frames": len(render_manifest)})
