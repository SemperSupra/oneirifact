"""Actual saved-action sign audit and adaptive native/GLB midpoint measurement.

No source scene is saved or repaired. Negative quaternion dots nominate intervals;
only measured midpoint disagreement with matching key endpoints confirms a defect.
"""
import hashlib
import json
import math
import os
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

import bpy
import numpy as np

ARGS = sys.argv[sys.argv.index("--") + 1:]
INPUTS, OUT = map(Path, ARGS[:2])
CUSTODY = json.loads((OUT / "input-custody.json").read_text())
TOLERANCE = 5e-5


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def action_curves(action):
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    return [fc for layer in action.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]


def choose_action(rig, action, slot=None):
    rig.animation_data_create()
    for track in rig.animation_data.nla_tracks:
        track.mute = True
    rig.animation_data.action = action
    if slot is not None:
        rig.animation_data.action_slot = slot
    elif hasattr(action, "slots") and len(action.slots):
        assert len(action.slots) == 1, "Ambiguous native action slot"
        rig.animation_data.action_slot = action.slots[0]


def frame_set(frame):
    bpy.context.scene.frame_set(math.floor(frame), subframe=frame % 1)
    bpy.context.view_layer.update()


def skin_for(rig):
    candidates = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and any(mod.type == "ARMATURE" and mod.object == rig for mod in obj.modifiers)]
    assert len(candidates) == 1, "Missing or ambiguous admitted body mesh"
    skin = candidates[0]
    assert len(skin.data.vertices) == 13380
    return skin


def rest_identity(obj):
    coordinates = np.empty(len(obj.data.vertices) * 3, dtype="<f4")
    obj.data.vertices.foreach_get("co", coordinates)
    indices = np.array([tuple(poly.vertices) for poly in obj.data.polygons], dtype="<i4")
    assert indices.shape == (26756, 3)
    return {"vertices": len(obj.data.vertices), "triangles": len(obj.data.polygons), "raw_mesh_position_sha256": sha(coordinates.tobytes()), "raw_mesh_indices_sha256": sha(indices.tobytes())}


def evaluated(obj):
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    coordinates = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", coordinates)
    coordinates = coordinates.reshape(-1, 3)
    transform = np.array(ev.matrix_world)
    result = coordinates @ transform[:3, :3].T + transform[:3, 3]
    ev.to_mesh_clear()
    return result


def glb_names(path):
    raw = path.read_bytes()
    assert raw[:4] == b"glTF" and struct.unpack_from("<I", raw, 4)[0] == 2
    length, kind = struct.unpack_from("<II", raw, 12)
    assert kind == 0x4E4F534A
    doc = json.loads(raw[20:20 + length])
    return [animation["name"] for animation in doc.get("animations", [])]


def scan(action, rig, origin, seconds_per_frame, role, export_name=None):
    grouped = defaultdict(dict)
    for fc in action_curves(action):
        if fc.data_path.endswith("rotation_quaternion"):
            assert fc.array_index not in grouped[fc.data_path], "Duplicate quaternion FCurve across slots"
            grouped[fc.data_path][fc.array_index] = fc
    result = {"role": role, "rig": rig.name, "rig_bones": len(rig.data.bones), "action": action.name, "export_animation": export_name, "action_frame_range": list(action.frame_range), "native_capture_origin_frame": origin, "seconds_per_native_frame": seconds_per_frame, "quaternion_paths": len(grouped), "quaternion_keys": 0, "minimum_normalized_adjacent_dot": 1.0, "negative_segments": [], "all_component_key_times_synchronized": True}
    assert grouped, "Expected quaternion action has no quaternion curves"
    for path, parts in grouped.items():
        assert set(parts) == {0, 1, 2, 3}, "Incomplete stored quaternion"
        key_times = [np.array([key.co.x for key in parts[i].keyframe_points], float) for i in range(4)]
        assert all(np.array_equal(key_times[0], t) for t in key_times[1:]), "Asynchronous component keys require a separate audit"
        frames = key_times[0]
        assert len(frames) and np.all(np.diff(frames) > 0)
        q = np.column_stack([[key.co.y for key in parts[i].keyframe_points] for i in range(4)])
        norms = np.linalg.norm(q, axis=1)
        assert np.isfinite(q).all() and np.all(norms > 1e-12), "Invalid stored quaternion"
        normalized = q / norms[:, None]
        dots = np.sum(normalized[:-1] * normalized[1:], axis=1)
        result["quaternion_keys"] += len(frames)
        if len(dots):
            result["minimum_normalized_adjacent_dot"] = min(result["minimum_normalized_adjacent_dot"], float(dots.min()))
        bone = None
        match = re.fullmatch(r'pose\.bones\[(".*")\]\.rotation_quaternion', path)
        if match:
            bone = json.loads(match.group(1))
            assert bone in rig.pose.bones
        for i in np.flatnonzero(dots < 0):
            left, right = float(frames[i]), float(frames[i + 1])
            midpoint = (left + right) / 2
            result["negative_segments"].append({"data_path": path, "bone": bone, "left_key_frame": left, "right_key_frame": right, "midpoint_frame": midpoint, "midpoint_time_s": (midpoint - origin) * seconds_per_frame, "left_wxyz": q[i].tolist(), "right_wxyz": q[i + 1].tolist(), "left_norm": float(norms[i]), "right_norm": float(norms[i + 1]), "raw_dot": float(q[i] @ q[i + 1]), "normalized_dot": float(dots[i]), "left_component_interpolation": [parts[j].keyframe_points[i].interpolation for j in range(4)], "within_exported_interval": bool(left >= origin - 1e-6), "native_to_glb_midpoint_check": "PENDING" if export_name and left >= origin - 1e-6 else "NOT_RUN_REFERENCE_TRANSITION_OR_SOURCE_ONLY_ACTION"})
    result["negative_segment_count"] = len(result["negative_segments"])
    return result


def imported_binding(rig, name, names):
    ad = rig.animation_data
    assert ad
    matches = []
    for track in ad.nla_tracks:
        track.mute = True
        if track.name == name:
            for strip in track.strips:
                if strip.action:
                    matches.append((strip.action, getattr(strip, "action_slot", None), track.name))
    if not matches and len(names) == 1 and names[0] == name and ad.action:
        matches.append((ad.action, getattr(ad, "action_slot", None), "single_declared_glTF_animation"))
    assert len(matches) == 1, "Missing or ambiguous exact imported animation " + name
    return matches[0]


def audit_case(row):
    entry = row["input"]
    source = INPUTS / row["input_path"]
    receipt = json.loads((source / entry["receipt"]).read_text())
    assert receipt["source_head_commit"] == entry["producer_head"]
    before = {name: sha((source / name).read_bytes()) for name in (entry["blend"], entry["glb"])}
    assert all(before[name] == row["selected_files"][name]["sha256"] for name in before)
    captured = entry["family"] == "r247"
    origin = 2.0 if captured else 1.0
    dt = float(receipt["source_normalization"]["native_frame_time_s"]) if captured else 1 / 24
    fps = 120 if captured else 24
    names = glb_names(source / entry["glb"])
    bpy.ops.wm.open_mainfile(filepath=str(source / entry["blend"]))
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE" and len(obj.data.bones) == 163]
    assert len(rigs) == 1
    rig = rigs[0]
    skin = skin_for(rig)
    native_identity = rest_identity(skin)
    native_scene_range = [bpy.context.scene.frame_start, bpy.context.scene.frame_end]
    case_id = receipt["case"]["id"]
    if captured:
        assert rig.animation_data and rig.animation_data.action
        mapping = [("CMU_" + receipt["capture"] + "_donor_baseline", rig.animation_data.action)]
        assert mapping[0][0] in names
    else:
        activities = [activity["activity_id"] for activity in receipt["activities"]]
        assert set(activities) == set(names)
        mapping = [(activity, bpy.data.actions[case_id + " / " + activity]) for activity in activities]
    target_reports, native_samples, ancillary_reports = [], {}, []
    for exported, action in mapping:
        choose_action(rig, action)
        report = scan(action, rig, origin, dt, "admitted_163_bone_skin_rig", exported)
        target_reports.append(report)
        nominated = [segment for segment in report["negative_segments"] if segment["within_exported_interval"]]
        frames = sorted({segment[key] for segment in nominated for key in ("left_key_frame", "midpoint_frame", "right_key_frame")})
        samples = {}
        for frame in frames:
            frame_set(frame)
            samples[frame] = evaluated(skin)
        native_samples[exported] = samples
    if captured:
        for source_rig in [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE" and obj != rig and obj.animation_data and obj.animation_data.action]:
            ancillary_reports.append(scan(source_rig.animation_data.action, source_rig, origin, dt, "captured_source_armature_without_GLb_counterpart"))
    measurements = []
    if any(native_samples.values()):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.render.fps = fps
        bpy.context.scene.render.fps_base = 1
        bpy.ops.import_scene.gltf(filepath=str(source / entry["glb"]))
        rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE" and len(obj.data.bones) == 163]
        assert len(rigs) == 1
        imported_rig = rigs[0]
        imported_skin = skin_for(imported_rig)
        imported_identity = rest_identity(imported_skin)
        assert imported_identity == native_identity, "Corresponding vertex comparison requires identical rest mesh order"
        for report in target_reports:
            exported = report["export_animation"]
            samples = native_samples[exported]
            if not samples:
                continue
            action, slot, binding_name = imported_binding(imported_rig, exported, names)
            choose_action(imported_rig, action, slot)
            first_frame = float(action.frame_range[0])
            errors = {}
            for native_frame, expected in samples.items():
                time_s = (native_frame - origin) * dt
                imported_frame = first_frame + time_s * fps
                frame_set(imported_frame)
                actual = evaluated(imported_skin)
                assert actual.shape == expected.shape == (13380, 3)
                distances = np.linalg.norm(actual - expected, axis=1)
                errors[native_frame] = {"max_corresponding_skin_vertex_error_m": float(distances.max()), "rms_corresponding_skin_vertex_error_m": float(np.sqrt(np.mean(distances ** 2))), "max_error_vertex_index": int(np.argmax(distances)), "native_frame": native_frame, "time_s": time_s, "imported_frame": imported_frame}
            for segment in report["negative_segments"]:
                if not segment["within_exported_interval"]:
                    continue
                left, mid, right = (errors[segment[key]] for key in ("left_key_frame", "midpoint_frame", "right_key_frame"))
                endpoints_pass = max(left["max_corresponding_skin_vertex_error_m"], right["max_corresponding_skin_vertex_error_m"]) <= TOLERANCE
                midpoint_pass = mid["max_corresponding_skin_vertex_error_m"] <= TOLERANCE
                if endpoints_pass and not midpoint_pass:
                    status = "CONFIRMED_NATIVE_GLB_MIDPOINT_DEFECT"
                elif endpoints_pass and midpoint_pass:
                    status = "SIGN_CHANGE_WITHOUT_MEASURED_MIDPOINT_DEFECT"
                else:
                    status = "UNRESOLVED_ENDPOINT_TRANSPORT_MISMATCH"
                segment["native_to_glb_midpoint_check"] = status
                segment["measurement_index"] = len(measurements)
                measurements.append({"status": status, "native_action": report["action"], "bone": segment["bone"], "export_animation": exported, "imported_action": action.name, "imported_binding": binding_name, "tolerance_m": TOLERANCE, "left_endpoint": left, "midpoint": mid, "right_endpoint": right})
    confirmed = sum(item["status"] == "CONFIRMED_NATIVE_GLB_MIDPOINT_DEFECT" for item in measurements)
    unresolved = sum(item["status"] == "UNRESOLVED_ENDPOINT_TRANSPORT_MISMATCH" for item in measurements)
    target_flips = sum(report["negative_segment_count"] for report in target_reports)
    source_flips = sum(report["negative_segment_count"] for report in ancillary_reports)
    active_target_flips = sum(segment["within_exported_interval"] for report in target_reports for segment in report["negative_segments"])
    active_source_flips = sum(segment["within_exported_interval"] for report in ancillary_reports for segment in report["negative_segments"])
    if confirmed:
        status = "HOLD_CONFIRMED_NATIVE_INTERPOLATION_DEFECT"
    elif unresolved:
        status = "HOLD_UNRESOLVED_TRANSPORT_MISMATCH"
    elif active_target_flips or active_source_flips:
        status = "HOLD_SIGN_CHANGES_WITH_BOUNDED_OR_MISSING_COUNTERPART_CHECK"
    elif target_flips or source_flips:
        status = "PASS_NO_SIGN_FLIPS_WITHIN_PUBLISHED_CLIPS_REFERENCE_TRANSITIONS_RETAINED"
    else:
        status = "PASS_NO_ADJACENT_QUATERNION_SIGN_FLIPS_IN_SCANNED_NATIVE_ACTIONS"
    after = {name: sha((source / name).read_bytes()) for name in before}
    assert before == after, "Read-only audit modified an input"
    negative_control = entry["family"] == "r246_negative"
    result = {"schema": "oneirifact.native-quaternion-continuity-audit/v1", "status": status, "input": entry, "execution_scope": "PUBLIC_PINNED_RUNTIME" if os.environ.get("GITHUB_RUN_ID") else "LOCAL_DIAGNOSTIC_ONLY", "blender_version": bpy.app.version_string, "source_files_sha256": before, "input_files_unchanged": True, "native_rest_mesh_identity": native_identity, "native_scene_playback_frame_range": native_scene_range, "target_actions": target_reports, "captured_source_actions": ancillary_reports, "target_negative_segments": target_flips, "captured_source_negative_segments": source_flips, "target_negative_segments_within_published_interval": active_target_flips, "captured_source_negative_segments_within_published_interval": active_source_flips, "reference_only_negative_segments": target_flips + source_flips - active_target_flips - active_source_flips, "confirmed_midpoint_defects": confirmed, "unresolved_endpoint_comparisons": unresolved, "adaptive_midpoint_measurements": measurements, "negative_control": negative_control, "negative_control_detection": "PASS_SOURCE_DEFECT_REPRODUCED" if negative_control and confirmed else "FAIL_EXPECTED_DEFECT_NOT_REPRODUCED" if negative_control else "NOT_A_CONTROL", "repair": "PROPOSED_ONLY: align adjacent native quaternion keys to one hemisphere per action/bone before bake; preserve every key time and endpoint rotation; rerun exact native/GLB midpoint comparisons at all detected crossings. No source data or scene modified by this audit." if active_target_flips else "NONE_REQUIRED_BY_THIS_PUBLISHED_INTERVAL_SIGN_AUDIT", "scope_limit": "Stored quaternion sign continuity and nominated native/GLB skin midpoints only. No blanket animation, physical realism, anatomical, collision, contact or physiological acceptance. Captured-source armature sign changes are separately reported where no source GLB action exists. Reference-to-capture transitions are retained but lie outside the published R247 playback interval."}
    return result


results = []
for row in CUSTODY["cases"]:
    result = audit_case(row)
    write(OUT / (str(row["input"]["artifact_id"]) + "-audit.json"), result)
    summary = {"id": row["input"]["id"], "artifact_id": row["input"]["artifact_id"], **{key: result[key] for key in ("status", "target_negative_segments", "captured_source_negative_segments", "confirmed_midpoint_defects", "negative_control_detection")}}
    results.append(summary)
    print("R249_CASE", json.dumps(summary), flush=True)
summary = {"schema": "oneirifact.native-quaternion-group-audit/v1", "status": "AUDIT_COMPLETED_WITH_RETAINED_FINDINGS", "group": CUSTODY["group"], "run_id": os.environ.get("GITHUB_RUN_ID"), "source_head_commit": os.environ.get("SOURCE_HEAD_SHA"), "blender_version": bpy.app.version_string, "cases": results, "case_count": len(results), "all_inputs_read_only": True, "rendering": "NOT_RUN", "manifest_sha256": CUSTODY["manifest_sha256"], "limits": "Green audit job means the audit executed and retained its findings; it does not mean every input scene passed."}
write(OUT / "group-summary.json", summary)
assert all(result["negative_control_detection"] != "FAIL_EXPECTED_DEFECT_NOT_REPRODUCED" for result in results), "Actual public negative-control defect was not reproduced"
