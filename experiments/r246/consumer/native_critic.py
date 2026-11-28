#!/usr/bin/env python3
"""Independent aquatic observation critic; stdlib only, no solver imports.

These fixed engineering screens are not human-motion, contact-force, clinical,
joint-range or realism acceptance. Source targets never count as observations.
Scientific failures remain in the JSON report; process success is not a PASS.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

SCHEMA = "oneirifact.aquatic-native-observations/v1"
SIDES = ("L", "R")
INTERMEDIATES = {p+"."+s for p in ("upperleg02", "lowerleg02", "upperarm02", "lowerarm02") for s in SIDES}
THRESHOLDS = {
    "pelvis_target_error_m": .005, "rotated_hip_error_m": .005, "rotated_shoulder_error_m": .005,
    "limb_length_drift_m": .0001, "reach_excess_m": .0001,
    "ankle_target_error_m": .005, "hand_target_error_m": .01, "hand_resolution_delta_m": .0001,
    "foot_marker_target_error_m": .005, "foot_orientation_error_rad": .01,
    "rigid_heel_forefoot_length_error_m": .0001, "intermediate_rotation_drift_rad": .0001,
    "root_relative_orientation_error_rad": .005, "loop_position_error_m": .005,
    "loop_orientation_error_rad": .005, "root_cycle_delta_error_m": .005,
    "tub_floor_marker_height_error_m": .005, "tub_floor_skin_subset_penetration_m": .002,
    "tub_floor_marker_bounds_excess_m": .005, "tub_floor_planted_drift_m": .005,
    "tub_floor_planted_speed_m_s": .05, "tub_rim_hand_drift_m": .005, "tub_rim_hand_speed_m_s": .05,
    "context_mesh_agreement_m": .0001, "context_static_drift_m": .0001,
    "evaluated_tub_floor_marker_error_m": .005, "evaluated_tub_floor_skin_subset_penetration_m": .002,
    "evaluated_tub_rim_wrist_error_m": .01
}


def finite(x):
    if type(x) not in (int, float) or not math.isfinite(x): raise ValueError("finite numeric value required")
    return float(x)


def vector(x, n=3):
    if not isinstance(x, (list, tuple)) or len(x) != n: raise ValueError("invalid vector shape")
    return [finite(v) for v in x]


def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def sub(a, b): return [x-y for x, y in zip(a, b)]
def add(a, b): return [x+y for x, y in zip(a, b)]
def norm(v): return math.sqrt(sum(x*x for x in v))
def distance(a, b): return norm(sub(a, b))


def quaternion(q):
    q = vector(q, 4)
    length = norm(q)
    if abs(length-1) > 1e-4: raise ValueError("unit quaternion required")
    return [v/length for v in q]


def qmatrix(q):
    x, y, z, w = quaternion(q)
    return [[1-2*y*y-2*z*z, 2*x*y-2*z*w, 2*x*z+2*y*w],
            [2*x*y+2*z*w, 1-2*x*x-2*z*z, 2*y*z-2*x*w],
            [2*x*z-2*y*w, 2*y*z+2*x*w, 1-2*x*x-2*y*y]]


def transpose(m): return [list(v) for v in zip(*m)]
def matmul(a, b): return [[sum(x*y for x, y in zip(row, col)) for col in zip(*b)] for row in a]
def matvec(a, b): return [sum(x*y for x, y in zip(row, b)) for row in a]
def qdistance(a, b): return 2*math.acos(min(1., abs(sum(x*y for x, y in zip(quaternion(a), quaternion(b))))))


def root_rotation(actual):
    m = actual["root_transform"]
    if not isinstance(m, list) or len(m) != 4: raise ValueError("4x4 observed root required")
    m = [vector(row, 4) for row in m]
    r = [row[:3] for row in m[:3]]
    gram = matmul(r, transpose(r))
    if max(abs(gram[i][j]-(1 if i == j else 0)) for i in range(3) for j in range(3)) > 1e-4:
        raise ValueError("observed root rotation is not orthonormal")
    return r


def rotation_distance(a, b):
    delta = matmul(a, transpose(b))
    return math.acos(max(-1., min(1., (sum(delta[i][i] for i in range(3))-1)/2)))


def gate(rows, threshold, scope):
    if not rows: return {"status": "NOT_RUN", "scope": scope, "reason": "no applicable independent observations", "samples": 0}
    value, witness = max(rows, key=lambda x: x[0])
    return {"status": "PASS" if value <= threshold else "FAIL", "maximum": value, "threshold": threshold,
            "worst_sample": witness, "samples": len(rows), "scope": scope}


def measured(rows, scope):
    if not rows: return {"status": "NOT_RUN", "reason": "observation absent", "scope": scope}
    low, high = min(rows, key=lambda x: x[0]), max(rows, key=lambda x: x[0])
    return {"status": "MEASURED", "minimum": low[0], "maximum": high[0], "minimum_sample": low[1],
            "maximum_sample": high[1], "samples": len(rows), "scope": scope, "contact_acceptance": "NOT_QUALIFIED"}


def snapshot(actual):
    points = {"pelvis": vector(actual["hip_center_m"])}
    rotations = {}
    for s in SIDES:
        for k in ("hip_m", "knee_m", "ankle_m", "heel_m", "forefoot_m", "toe_m"): points[s+".foot."+k] = vector(actual["feet"][s][k])
        for k in ("shoulder_m", "elbow_m", "wrist_m"): points[s+".arm."+k] = vector(actual["arms"][s][k])
        points[s+".hand"] = vector(actual["hands_m"][s])
        rotations[s+".foot"] = quaternion(actual["feet"][s]["rotation_xyzw"])
    for k in ("head_m", "mouth_m", "chest_surface_anchor_m", "sponge_center_m"):
        if k in actual: points[k] = vector(actual[k])
    for name, entry in actual.get("intermediate_bones", {}).items():
        points[name] = vector(entry["position_m"])
        rotations[name] = quaternion(entry["relative_rotation_xyzw"])
    return {"points": points, "rotations": rotations, "root_rotation": root_rotation(actual)}


def rectangle(cx, y, cz, width, length):
    return [[cx+dx*width/2, y, cz+dz*length/2] for dx, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def corner_set(points):
    if not isinstance(points, list) or len(points) != 4: raise ValueError("four evaluated surface corners required")
    return [vector(p) for p in points]


def set_distance(a, b):
    return max(max(min(distance(p, q) for q in b) for p in a), max(min(distance(p, q) for q in a) for p in b))


def plane_rectangle_distance(point, corners):
    # Context contract is axis-aligned in canonical world coordinates. The
    # separate mesh-agreement gate checks planarity and its intended frame.
    y = sum(p[1] for p in corners)/4
    dx = max(0., min(p[0] for p in corners)-point[0], point[0]-max(p[0] for p in corners))
    dz = max(0., min(p[2] for p in corners)-point[2], point[2]-max(p[2] for p in corners))
    return math.sqrt(dx*dx+(point[1]-y)**2+dz*dz)


def mesh_context_review(row, activity, context):
    actual, ref = row["actual"], {"time_s": finite(row["time_s"])}
    geometry = actual.get("context_geometry")
    result = {"mode": "MISSING", "points": {}, "agreement": [], "floor_markers": [], "floor_skin": [], "rim_wrists": [], "seat_offset": [], "mouth_clearance": []}
    if geometry is None: return result
    status = geometry.get("status")
    if status == "NATIVE_CONTEXT_NOT_EXPORTED_TO_BODY_GLB":
        result["mode"] = "OMITTED" if row.get("replay_phase") == "exported_glb_reimported" else "UNEXPECTED_OMISSION"
        return result
    if status != "EVALUATED_NATIVE_MESH_WORLD_VERTICES" or geometry.get("coordinates") != "canonical_metres_y_up":
        raise ValueError("unknown evaluated context status or coordinate units")
    result["mode"] = "OBSERVED"
    if activity == "swimming_front_crawl":
        for key, y in (("surface_corners_m", finite(context["surface_y_m"])),
                       ("bottom_corners_m", finite(context["surface_y_m"])-finite(context["depth_m"]))):
            corners = corner_set(geometry["water"][key])
            for i, p in enumerate(corners):
                result["points"][key+str(i)] = p
                result["agreement"].append((abs(p[1]-y), {**ref, "surface": key, "corner": i}))
        water_y = sum(p[1] for p in corner_set(geometry["water"]["surface_corners_m"]))/4
        result["mouth_clearance"].append((vector(actual["mouth_m"])[1]-water_y, ref))
        return result
    tub = geometry["tub"]
    cx, cz = [finite(v) for v in context["center_xz_m"]]
    floor_y = finite(context["floor_y_m"])
    sx, sy, sz = vector(context["seat_center_m"])
    targets = {"floor": ([cx, floor_y, cz], rectangle(cx, floor_y, cz, finite(context["interior_width_m"]), finite(context["interior_length_m"]))),
               "seat": ([sx, sy, sz], rectangle(sx, sy, sz, finite(context["seat_width_m"]), finite(context["seat_depth_m"])))}
    for name, (center, expected) in targets.items():
        corners, observed_center = corner_set(tub[name+"_top_corners_m"]), vector(tub[name+"_top_center_m"])
        mean = [sum(p[k] for p in corners)/4 for k in range(3)]
        result["agreement"].append((max(set_distance(corners, expected), distance(observed_center, center), distance(mean, observed_center)), {**ref, "surface": name}))
        for i, p in enumerate(corners): result["points"][name+str(i)] = p
    rim_y, width, length = finite(context["rim_y_m"]), finite(context["interior_width_m"]), finite(context["interior_length_m"])
    rim_expected = {"L": [cx+width/2, rim_y, cz], "R": [cx-width/2, rim_y, cz],
                    "back": [cx, rim_y, cz-length/2], "front": [cx, rim_y, cz+length/2]}
    for name, expected in rim_expected.items():
        center = vector(tub["rim_top_centers_m"][name]); corners = corner_set(tub["rim_top_corners_m"][name])
        mean = [sum(p[k] for p in corners)/4 for k in range(3)]
        axis, middle, span = (2, cz, length) if name in SIDES else (0, cx, width)
        error = max(distance(center, expected), distance(center, mean), max(abs(p[1]-rim_y) for p in corners),
                    abs(min(p[axis] for p in corners)-(middle-span/2)), abs(max(p[axis] for p in corners)-(middle+span/2)))
        result["agreement"].append((error, {**ref, "surface": "rim."+name}))
        for i, p in enumerate(corners): result["points"]["rim."+name+str(i)] = p
    floor = corner_set(tub["floor_top_corners_m"])
    observed_floor_y = sum(p[1] for p in floor)/4
    for s in SIDES:
        for marker in ("heel", "forefoot", "toe"):
            point = vector(actual["feet"][s][marker+"_m"])
            result["floor_markers"].append((plane_rectangle_distance(point, floor), {**ref, "side": s, "marker": marker}))
        if "skin_sole_min_y_m" in actual["feet"][s]:
            result["floor_skin"].append((max(0., observed_floor_y-finite(actual["feet"][s]["skin_sole_min_y_m"])), {**ref, "side": s}))
        if row["target"]["hand_targets"][s]["reference"] == "world:tub:rim":
            corners = corner_set(tub["rim_top_corners_m"][s])
            result["rim_wrists"].append((plane_rectangle_distance(vector(actual["hands_m"][s]), corners), {**ref, "side": s}))
    result["seat_offset"].append((vector(actual["hip_center_m"])[1]-vector(tub["seat_top_center_m"])[1], ref))
    return result


def clip_review(case, clip):
    authored, frames = clip["compiler_clip"], clip["frames"]
    activity = clip["activity_id"]
    if activity not in ("swimming_front_crawl", "bathing_seated_wash"): raise ValueError("unsupported aquatic activity")
    if authored.get("schema") != "oneirifact.aquatic-intent-clip/v1": raise ValueError("unknown authored clip schema")
    if not frames: raise ValueError("no observed frames")
    inst = authored["instance"]
    if inst["activity_id"] != activity: raise ValueError("activity identity mismatch")
    m, measure, context = inst["morphology"], inst["limb_measurements"], inst["context"]
    rest, hips0 = case["rest"], vector(m["hip_center_m"])
    bind = case.get("bind_sha")
    identifiers = [bind, m["source_bind_sha256"], measure["source_bind_sha256"], inst["source_bind_sha256"], case["morphology"]["source_bind_sha256"]]
    identity = len(set(identifiers)) == 1 and isinstance(bind, str) and len(bind) == 64 and all(x in "0123456789abcdef" for x in bind)
    synthetic = set(identifiers) == {"UNVERIFIED_SYNTHETIC"}
    payload = dict(authored)
    payload.pop("clip_sha256", None)
    integrity = authored.get("clip_sha256") == digest(payload) and authored.get("definition_sha256") == digest(authored["definition"]) and authored.get("instance_sha256") == digest(inst)
    expected = authored["frames"]
    times = [finite(f["time_s"]) for f in frames]
    authored_times = [finite(f["time_s"]) for f in expected]
    if any(b <= a for a, b in zip(times, times[1:])): raise ValueError("observation timestamps must strictly increase")
    if any(b <= a for a, b in zip(authored_times, authored_times[1:])): raise ValueError("authored timestamps must strictly increase")
    full = len(times) == len(authored_times) and all(abs(a-b) < 1e-7 for a, b in zip(times, authored_times))
    lookup = {round(t, 8): f for t, f in zip(authored_times, expected)}
    target_identity = True
    semantics = True
    chest_identity = True
    values = {k: [] for k in THRESHOLDS}
    diagnostics = {k: [] for k in ("chest_reference_displacement_m", "pelvis_above_seat_m", "sponge_to_chest_m", "mouth_above_water_m", "sponge_distance_readback_error_m", "pelvis_above_evaluated_seat_m", "mouth_above_evaluated_water_m")}
    states, first_contact, previous_contact, first_rim, previous_rim = [], {}, {}, {}, {}
    context_modes, first_context = [], None
    incomplete_intermediates = []
    lengths = {}
    for s in SIDES:
        thigh = distance(vector(m["hips_m"][s]), vector(m["knees_m"][s]))
        shin = distance(vector(m["knees_m"][s]), vector(m["ankles_m"][s]))
        arm = measure["arms"][s]
        upper = distance(vector(arm["shoulder_m"]), vector(arm["elbow_m"]))
        lower = distance(vector(arm["elbow_m"]), vector(arm["wrist_m"]))
        lengths[s] = (thigh, shin, upper, lower)
        if min(lengths[s]) <= 0: raise ValueError("nonpositive source segment length")
        if max(abs(thigh-finite(rest["thigh_length_m"][s])), abs(shin-finite(rest["shin_length_m"][s])),
               abs(upper-finite(rest["arms"][s]["upper_m"])), abs(lower-finite(rest["arms"][s]["lower_m"]))) > 1e-8:
            raise ValueError("rest length does not match source measured anchors")
    for i, row in enumerate(frames):
        actual, target, time = row["actual"], row["target"], times[i]
        ref = {"frame": i, "time_s": time}
        original = lookup.get(round(time, 8))
        target_identity &= original is not None and canonical(target) == canonical(original)
        if abs(time-finite(target["time_s"])) > 1e-7: raise ValueError("actual/target timestamp mismatch")
        root = vector(target["hip_center_m"])
        r = qmatrix(target["root_orientation_xyzw"])
        values["pelvis_target_error_m"].append((distance(vector(actual["hip_center_m"]), root), ref))
        state = snapshot(actual)
        states.append(state)
        geometry = mesh_context_review(row, activity, context)
        context_modes.append(geometry["mode"])
        values["context_mesh_agreement_m"].extend(geometry["agreement"])
        values["evaluated_tub_floor_marker_error_m"].extend(geometry["floor_markers"])
        values["evaluated_tub_floor_skin_subset_penetration_m"].extend(geometry["floor_skin"])
        values["evaluated_tub_rim_wrist_error_m"].extend(geometry["rim_wrists"])
        diagnostics["pelvis_above_evaluated_seat_m"].extend(geometry["seat_offset"])
        diagnostics["mouth_above_evaluated_water_m"].extend(geometry["mouth_clearance"])
        if geometry["mode"] == "OBSERVED":
            if first_context is None: first_context = geometry["points"]
            if set(first_context) != set(geometry["points"]): raise ValueError("evaluated static context point coverage changed")
            values["context_static_drift_m"].append((max(distance(first_context[k], p) for k, p in geometry["points"].items()), ref))
        desired_relative = matmul(r, transpose(qmatrix(frames[0]["target"]["root_orientation_xyzw"])))
        actual_relative = matmul(state["root_rotation"], transpose(states[0]["root_rotation"]))
        values["root_relative_orientation_error_rad"].append((rotation_distance(actual_relative, desired_relative), ref))
        for s in SIDES:
            foot, wanted = actual["feet"][s], target["feet"][s]
            arm, desired_hand = actual["arms"][s], vector(target["hands_m"][s])
            sr = dict(ref, side=s)
            intended_hip = add(root, matvec(r, sub(vector(m["hips_m"][s]), hips0)))
            intended_shoulder = add(root, matvec(r, sub(vector(measure["arms"][s]["shoulder_m"]), hips0)))
            values["rotated_hip_error_m"].append((distance(vector(foot["hip_m"]), intended_hip), sr))
            values["rotated_shoulder_error_m"].append((distance(vector(arm["shoulder_m"]), intended_shoulder), sr))
            thigh, shin, upper, lower = lengths[s]
            for part, start, end, length in (("thigh", foot["hip_m"], foot["knee_m"], thigh), ("shin", foot["knee_m"], foot["ankle_m"], shin),
                                            ("upper_arm", arm["shoulder_m"], arm["elbow_m"], upper), ("forearm", arm["elbow_m"], arm["wrist_m"], lower)):
                values["limb_length_drift_m"].append((abs(distance(vector(start), vector(end))-length), dict(sr, segment=part)))
            for limb, start, end, a, b in (("leg", intended_hip, vector(wanted["ankle_m"]), thigh, shin),
                                          ("arm", intended_shoulder, desired_hand, upper, lower)):
                d = distance(start, end)
                values["reach_excess_m"].append((max(0., abs(a-b)-d, d-a-b), dict(sr, limb=limb)))
            values["ankle_target_error_m"].append((distance(vector(foot["ankle_m"]), vector(wanted["ankle_m"])), sr))
            values["hand_target_error_m"].append((max(distance(vector(actual["hands_m"][s]), desired_hand), distance(vector(arm["wrist_m"]), desired_hand)), sr))
            resolved = row.get("resolved_task", {}).get("resolved_hands_m", {}).get(s)
            if resolved is not None: values["hand_resolution_delta_m"].append((distance(vector(resolved), desired_hand), sr))
            values["foot_orientation_error_rad"].append((qdistance(foot["rotation_xyzw"], wanted["rotation_xyzw"]), sr))
            expected_sole = distance(vector(m["feet"][s]["heel_from_ankle_m"]), vector(m["feet"][s]["forefoot_from_ankle_m"]))
            values["rigid_heel_forefoot_length_error_m"].append((abs(distance(vector(foot["heel_m"]), vector(foot["forefoot_m"]))-expected_sole), sr))
            for marker in ("heel", "forefoot", "toe"):
                p = vector(foot[marker+"_m"])
                values["foot_marker_target_error_m"].append((distance(p, vector(wanted[marker+"_m"])), dict(sr, marker=marker)))
            refs = target["hand_targets"][s]
            semantics &= vector(refs["position_m"]) == desired_hand and target["arm_poles"][s]["reference"] == "world"
            if any(type(x) is not bool for x in wanted["contacts"].values()): raise ValueError("boolean contact flags required")
            if activity == "swimming_front_crawl":
                semantics &= refs["reference"] == "world" and not any(wanted["contacts"].values()) and wanted["contact_reference"] == "none" and not wanted["support_regions"]
            else:
                semantics &= wanted["contact_reference"] == "world:tub:floor" and all(wanted["contacts"].values())
                semantics &= refs["reference"] in ("world:tub:rim", "body:chest_surface_anchor")
                floor = finite(context["floor_y_m"])
                x, z = [finite(v) for v in context["center_xz_m"]]
                for marker in ("heel", "forefoot", "toe"):
                    p = vector(foot[marker+"_m"])
                    values["tub_floor_marker_height_error_m"].append((abs(p[1]-floor), dict(sr, marker=marker)))
                    excess = max(0., abs(p[0]-x)-finite(context["interior_width_m"])/2, abs(p[2]-z)-finite(context["interior_length_m"])/2)
                    values["tub_floor_marker_bounds_excess_m"].append((excess, dict(sr, marker=marker)))
                    key = (s, marker)
                    first_contact.setdefault(key, p)
                    values["tub_floor_planted_drift_m"].append((distance(p, first_contact[key]), dict(sr, marker=marker)))
                    if key in previous_contact:
                        prev, t0 = previous_contact[key]
                        values["tub_floor_planted_speed_m_s"].append((distance(p, prev)/(time-t0), dict(sr, marker=marker)))
                    previous_contact[key] = (p, time)
                if "skin_sole_min_y_m" in foot:
                    values["tub_floor_skin_subset_penetration_m"].append((max(0., floor-finite(foot["skin_sole_min_y_m"])), sr))
                if refs["reference"] == "world:tub:rim":
                    p = vector(actual["hands_m"][s]); first_rim.setdefault(s, p)
                    values["tub_rim_hand_drift_m"].append((distance(p, first_rim[s]), sr))
                    if s in previous_rim:
                        prev, t0 = previous_rim[s]
                        values["tub_rim_hand_speed_m_s"].append((distance(p, prev)/(time-t0), sr))
                    previous_rim[s] = (p, time)
        for name in INTERMEDIATES:
            entry, baseline = actual.get("intermediate_bones", {}).get(name), rest.get("intermediate_bones", {}).get(name)
            if entry is None or baseline is None: incomplete_intermediates.append({**ref, "bone": name})
            else: values["intermediate_rotation_drift_rad"].append((qdistance(entry["relative_rotation_xyzw"], baseline["relative_rotation_xyzw"]), dict(ref, bone=name)))
        chest_identity &= type(actual.get("chest_source_vertex_id")) is int and actual["chest_source_vertex_id"] == measure["chest_source_vertex_id"]
        chest = vector(actual["chest_surface_anchor_m"])
        diagnostics["chest_reference_displacement_m"].append((distance(chest, vector(target["body_anchors"]["chest_surface_anchor_m"])), ref))
        if activity == "swimming_front_crawl":
            diagnostics["mouth_above_water_m"].append((vector(actual["mouth_m"])[1]-finite(context["surface_y_m"]), ref))
        else:
            diagnostics["pelvis_above_seat_m"].append((vector(actual["hip_center_m"])[1]-vector(context["seat_center_m"])[1], ref))
            if "sponge_center_m" in actual:
                d = distance(vector(actual["sponge_center_m"]), chest)
                diagnostics["sponge_to_chest_m"].append((d, ref))
                if "sponge_center_to_chest_vertex_m" in actual:
                    diagnostics["sponge_distance_readback_error_m"].append((abs(d-finite(actual["sponge_center_to_chest_vertex_m"])), ref))
    loop = authored["loop"]
    cycles = (times[-1]-times[0])/finite(loop["period_s"])
    loop_complete = bool(loop["enabled"]) and full and cycles >= 1-1e-7 and abs(cycles-round(cycles)) < 1e-7
    if loop_complete:
        delta = [x*round(cycles) for x in vector(loop["cycle_delta_m"])]
        a, b = states[0], states[-1]
        if set(a["points"]) != set(b["points"]) or set(a["rotations"]) != set(b["rotations"]): raise ValueError("loop observation field coverage differs")
        for key in a["points"]:
            values["loop_position_error_m"].append((distance(sub(b["points"][key], delta), a["points"][key]), {"marker": key, "cycles": round(cycles)}))
        for key in a["rotations"]:
            values["loop_orientation_error_rad"].append((qdistance(a["rotations"][key], b["rotations"][key]), {"marker": key}))
        values["loop_orientation_error_rad"].append((rotation_distance(a["root_rotation"], b["root_rotation"]), {"marker": "root"}))
        values["root_cycle_delta_error_m"].append((distance(sub(b["points"]["pelvis"], a["points"]["pelvis"]), delta), {"cycles": round(cycles), "declared_delta_m": delta}))
    scopes = {k: "Independent evaluated observations versus original authored targets or measured source bind; engineering screen only." for k in THRESHOLDS}
    for k in THRESHOLDS:
        if k.startswith("tub_floor"): scopes[k] = "Selected actual FK foot markers or declared skin-sole subset versus the declared bounded tub floor; no independent tub mesh/full-body collision or load-support proof."
        if k.startswith("tub_rim"): scopes[k] = "Actual wrist stationarity during authored rim-support intent; no skin/rim contact or load-support proof."
        if k.startswith("loop_"): scopes[k] = "Complete sampled loop of all supplied joint/marker/chest/head/optional-prop observations after declared root delta; unobserved bones are not qualified."
    scopes["hand_target_error_m"] = "Actual wrist compared directly to frozen authored world target, never to a silently mouth-shifted target."
    scopes["rotated_hip_error_m"] = scopes["rotated_shoulder_error_m"] = "Independent quaternion-matrix rotation of measured source offsets about intended hip center."
    scopes["reach_excess_m"] = "Necessary arm/leg two-link annulus in intended rotated source-anchor frame; no joint-range acceptance."
    scopes["context_mesh_agreement_m"] = "Evaluated native context vertices/centers against declared floor/seat/rim or water plane geometry; support loads and unmodelled wall thickness excluded."
    scopes["context_static_drift_m"] = "Evaluated context vertices remain stationary in world coordinates while the actor moves."
    scopes["evaluated_tub_floor_marker_error_m"] = "Actual rigid FK foot markers versus evaluated bounded tub floor top; no entire-foot or skin contact proof."
    scopes["evaluated_tub_floor_skin_subset_penetration_m"] = "Observed skin-sole subset minimum versus evaluated tub floor top; not full-body collision."
    scopes["evaluated_tub_rim_wrist_error_m"] = "Actual wrist point versus the evaluated same-side rim top rectangle; no palm/skin contact or load claim."
    gates = {k: gate(rows, THRESHOLDS[k], scopes[k]) for k, rows in values.items()}
    gates["bind_identity"] = {"status": "PASS" if identity else "NOT_RUN" if synthetic else "FAIL", "source_bind_sha256": bind, "scope": "Matching supplied bind identities only; artifact custody separate."}
    gates["authored_payload_integrity"] = {"status": "PASS" if integrity else "FAIL", "scope": "Definition, instance and complete authored clip SHA256 readback."}
    gates["authored_target_identity"] = {"status": "PASS" if target_identity else "FAIL", "scope": "Every observed row retains its exact original authored target at the same time."}
    gates["authored_time_coverage"] = {"status": "PASS" if full else "NOT_RUN", "observed_frames": len(times), "authored_frames": len(authored_times), "reason": "Full authored timestamps required for sampled contact/loop qualification."}
    gates["reference_and_contact_semantics"] = {"status": "PASS" if semantics else "FAIL", "scope": "Explicit world/body/tub reference meanings and no swimming ground-support inference."}
    gates["chest_vertex_identity"] = {"status": "PASS" if chest_identity else "FAIL", "scope": "Observed source vertex ID equals the measured immutable source vertex; consumer transport identity guard is separate evidence."}
    gates["intermediate_rotation_coverage"] = {"status": "PASS" if not incomplete_intermediates else "NOT_RUN", "missing": incomplete_intermediates, "expected_bones": sorted(INTERMEDIATES)}
    skin_coverage = activity == "swimming_front_crawl" or len(values["tub_floor_skin_subset_penetration_m"]) == len(frames)*2
    gates["skin_sole_subset_coverage"] = {"status": "NOT_APPLICABLE" if activity == "swimming_front_crawl" else "PASS" if skin_coverage else "NOT_RUN",
                                          "observed_samples": len(values["tub_floor_skin_subset_penetration_m"]),
                                          "scope": "Both declared skin-sole subsets at every bath frame; no full-body surface coverage."}
    context_complete = all(mode == "OBSERVED" for mode in context_modes)
    context_omitted = all(mode == "OMITTED" for mode in context_modes)
    gates["evaluated_context_coverage"] = {"status": "PASS" if context_complete else "NOT_APPLICABLE" if context_omitted else "FAIL" if "UNEXPECTED_OMISSION" in context_modes else "NOT_RUN",
                                           "observed_frames": context_modes.count("OBSERVED"), "explicit_body_glb_omissions": context_modes.count("OMITTED"),
                                           "scope": "Native/reopened evaluated context vertices required; body-only GLB explicitly omits context."}
    if context_omitted:
        for k in ("context_mesh_agreement_m", "context_static_drift_m", "evaluated_tub_floor_marker_error_m", "evaluated_tub_floor_skin_subset_penetration_m", "evaluated_tub_rim_wrist_error_m"):
            gates[k] = {"status": "NOT_APPLICABLE", "reason": "Context is explicitly omitted from body-only GLB; declared-context tracking remains separately reported."}
    if activity == "swimming_front_crawl":
        for k in THRESHOLDS:
            if k.startswith("tub_") or k.startswith("evaluated_tub_"): gates[k] = {"status": "NOT_APPLICABLE", "reason": "Swimming has no authored ground/tub support episode."}
        gates["ground_support"] = {"status": "NOT_APPLICABLE", "reason": "Water is context, not a ground/support plane."}
    else:
        gates["ground_support"] = {"status": "NOT_APPLICABLE", "reason": "Bath floor is handled by explicit world:tub:floor subset gates, not world ground."}
    if not full:
        for k in ("tub_floor_planted_drift_m", "tub_floor_planted_speed_m_s", "tub_rim_hand_drift_m", "tub_rim_hand_speed_m_s", "loop_position_error_m", "loop_orientation_error_rad", "root_cycle_delta_error_m"):
            if gates[k]["status"] != "NOT_APPLICABLE": gates[k] = {"status": "NOT_RUN", "reason": "Incomplete timestamps cannot establish continuous authored episodes or full sampled loops."}
    descriptions = {
        "chest_reference_displacement_m": "Actual posed source skin vertex versus root-transformed rest reference. Skin deformation is measured, not treated as a tracking defect.",
        "pelvis_above_seat_m": "Signed pelvis-center height above declared seat top; pelvis center is not a body/seat contact patch.",
        "sponge_to_chest_m": "Actual rigid sponge mesh center to actual posed source chest vertex; radius, skin surface contact and grip unqualified.",
        "mouth_above_water_m": "Signed mouth proxy height above declared water plane; no airway or breathing acceptance.",
        "sponge_distance_readback_error_m": "Independent recomputation versus consumer-reported center-to-chest distance; no contact claim.",
        "pelvis_above_evaluated_seat_m": "Signed pelvis-center height above evaluated seat top; no body-seat contact patch or load evidence.",
        "mouth_above_evaluated_water_m": "Signed mouth proxy height above evaluated water surface; not airway clearance."}
    for name, reason in {"body_seat_and_rim_contact": "No independent contact patches, body/tub intersection or loads.",
                         "grip_and_washing_contact": "Sponge/skin proximity is not grip or wiping contact.", "airway_and_breathing": "Mouth proxy does not establish airway clearance or breathing.",
                         "fluid_forces_and_buoyancy": "Kinematic context only.", "joint_limits_and_collision": "No calibrated anatomical limits or whole-mesh collision critic.",
                         "motion_realism": "Authored targets and geometry tracking do not establish realistic human motion."}.items():
        gates[name] = {"status": "NOT_RUN", "reason": reason}
    failed = sorted(k for k, g in gates.items() if g["status"] == "FAIL")
    status = "FAIL_BOUNDED_AQUATIC_GATES" if failed else "INCOMPLETE_SAMPLED_OBSERVATIONS" if not full or incomplete_intermediates or not skin_coverage or not (context_complete or context_omitted) else "BOUNDED_AQUATIC_OBSERVATIONS_REPORTED"
    return {"activity_id": activity, "status": status, "failed_gates": failed, "frames": len(frames), "gates": gates,
            "diagnostics": {k: measured(v, descriptions[k]) for k, v in diagnostics.items()}, "realism": "NOT_QUALIFIED"}


def review(observations):
    if observations.get("schema") != SCHEMA or not observations.get("cases"): raise ValueError("expected nonempty "+SCHEMA)
    result = {"schema": "oneirifact.aquatic-independent-native-critic/v1", "thresholds": THRESHOLDS,
              "threshold_scope": "Fixed provisional engineering screens; not physiological, contact-force or realism standards.",
              "observations_sha256": digest(observations), "cases": [], "realism": "NOT_QUALIFIED"}
    for case in observations["cases"]:
        item = {"id": case.get("id"), "clips": []}
        if not case.get("clips"): item["clips"].append({"status": "INVALID_OBSERVATIONS", "error": "no observed clips"})
        for clip in case.get("clips", []):
            try: item["clips"].append(clip_review(case, clip))
            except (ValueError, KeyError, TypeError, ZeroDivisionError, IndexError) as e:
                item["clips"].append({"activity_id": clip.get("activity_id"), "status": "INVALID_OBSERVATIONS", "error": str(e), "realism": "NOT_QUALIFIED"})
        result["cases"].append(item)
    result["failed_or_invalid_clip_count"] = sum(x["status"] in ("INVALID_OBSERVATIONS", "FAIL_BOUNDED_AQUATIC_GATES") for case in result["cases"] for x in case["clips"])
    result["incomplete_clip_count"] = sum(x["status"] == "INCOMPLETE_SAMPLED_OBSERVATIONS" for case in result["cases"] for x in case["clips"])
    return result


if __name__ == "__main__":
    report = review(json.loads(Path(sys.argv[1]).read_text()))
    Path(sys.argv[2]).write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k: report[k] for k in ("failed_or_invalid_clip_count", "incomplete_clip_count", "realism")}))
