"""Original aquatic target intent. The native consumer owns pose solving.

The frozen R245 math/measurement validation is reused without modifying its
schema. New arm and skin measurements are separate, tied to the same GLB hash.
No force model, collision solver, fitted motion, or observed-contact claim.
"""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[1] / "r245/motion/compiler.py"
CORE_SHA256 = "124ccc6464c0ae19b3766a0d9bb248d105d81e8c1595fc56edae69ed6ce003fd"
CORE_LIBRARY_SHA256 = "0a449e8a980190296d33f915397f1f1deab641d4b0bfd585f7f08fea08784672"
if hashlib.sha256(CORE.read_bytes()).hexdigest() != CORE_SHA256:
    raise RuntimeError("frozen R245 compiler digest mismatch")
if hashlib.sha256(CORE.with_name("library.json").read_bytes()).hexdigest() != CORE_LIBRARY_SHA256:
    raise RuntimeError("frozen R245 library digest mismatch")
_spec = importlib.util.spec_from_file_location("r245_frozen_motion", CORE)
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)
add, sub, mul, dot, norm, cross, unit = core.add, core.sub, core.mul, core.dot, core.norm, core.cross, core.unit
vec, number, need, digest, canonical, quaternion = core.vec, core.number, core.need, core.digest, core.canonical, core.quaternion
SIDES = ("L", "R")


def _keys(value, allowed, name):
    need(isinstance(value, dict), name + " must be an object")
    core._keys(value, allowed, name)


def qmul(a, b):
    av, bv = a[:3], b[:3]
    return add(add(mul(bv, a[3]), mul(av, b[3])), cross(av, bv)) + [a[3]*b[3]-dot(av, bv)]


def qrot(q, value):
    return add(value, add(mul(cross(q[:3], value), 2*q[3]), mul(cross(q[:3], cross(q[:3], value)), 2)))


def library():
    return json.loads((HERE / "library.json").read_text())


def _measurement(value, morphology):
    _keys(value, {"schema", "source_bind_sha256", "arms", "chest_surface_anchor_m", "chest_source_vertex_id", "source_mesh_position_sha256", "method", "bone_node_ids"}, "limb measurements")
    need(value.get("schema") == "oneirifact.aquatic-source-measurements/v1", "unsupported limb measurement schema")
    need(value.get("source_bind_sha256") == morphology["source_bind_sha256"], "arm and leg measurements must share exact source bind")
    result = copy.deepcopy(value)
    _keys(result["arms"], set(SIDES), "arms")
    for s in SIDES:
        a = result["arms"][s]
        _keys(a, {"shoulder_m", "elbow_m", "wrist_m", "upper_m", "lower_m", "total_m"}, "arm")
        for k in ("shoulder_m", "elbow_m", "wrist_m"): a[k] = vec(a[k], k)
        for k, p, q in (("upper_m", "shoulder_m", "elbow_m"), ("lower_m", "elbow_m", "wrist_m")):
            a[k] = number(a[k], k)
            need(a[k] > .02 and abs(a[k] - norm(sub(a[p], a[q]))) < 1e-8, "arm length must match measured bind anchors")
        for k in ("shoulder", "wrist"):
            need(norm(sub(a[k+"_m"], morphology["landmarks_m"][k+"_"+s])) < 1e-8, "arm anchor differs from morphology")
        total = a["upper_m"] + a["lower_m"]
        if "total_m" in a: need(abs(number(a["total_m"], "total arm length")-total) < 1e-8, "resolved total arm length mismatch")
        a["total_m"] = total
    result["chest_surface_anchor_m"] = vec(result["chest_surface_anchor_m"], "chest surface anchor")
    need(type(result["chest_source_vertex_id"]) is int and result["chest_source_vertex_id"] >= 0, "source skin vertex required")
    return result


def barefoot(morphology):
    m, _ = core.validate_morphology(morphology)
    value = core.footwear_from_profile("flats", m)
    value.update(id="barefoot", heel_stack_m=0., forefoot_stack_m=0., profile_definition_sha256=digest({"id": "measured-barefoot/v1", "stack_m": 0.}))
    return value


def context_from_template(activity_id, morphology):
    m, legs = core.validate_morphology(morphology)
    h = m["stature_m"]
    leg = sum(x["total_m"] for x in legs.values())/2
    t = json.loads((HERE / "context-templates.json").read_text())
    if activity_id == "swimming_front_crawl":
        d = t["water"]
        return {"schema": "oneirifact.water-context/v1", "id": d["id"], "surface_y_m": d["surface_y_m"],
                "origin_xz_m": d["origin_xz_m"], "root_depth_m": d["root_depth_stature_ratio"]*h,
                "forward_speed_m_s": d["forward_speed_stature_per_second"]*h, "depth_m": d["depth_stature_ratio"]*h}
    need(activity_id == "bathing_seated_wash", "unsupported aquatic activity")
    d = t["tub"]
    width = d["interior_width_shoulder_ratio"]*m["shoulder_width_m"]
    length = d["interior_length_leg_ratio"]*leg
    x, z = d["center_xz_m"]
    floor = d["floor_y_m"]
    return {"schema": "oneirifact.tub-context/v1", "id": d["id"], "floor_y_m": floor,
            "center_xz_m": [x, z], "interior_width_m": width, "interior_length_m": length,
            "rim_y_m": floor+d["rim_height_leg_ratio"]*leg,
            "seat_center_m": [x, floor+d["seat_height_leg_ratio"]*leg, z-d["seat_back_length_ratio"]*length],
            "seat_width_m": d["seat_width_hip_ratio"]*norm(sub(m["hips_m"]["L"], m["hips_m"]["R"])),
            "seat_depth_m": d["seat_depth_leg_ratio"]*leg,
            "rim_hand_forward_m": d["rim_hand_forward_leg_ratio"]*leg}


def _context(activity, value):
    water = activity == "swimming_front_crawl"
    allowed = ({"schema", "id", "surface_y_m", "origin_xz_m", "root_depth_m", "forward_speed_m_s", "depth_m"} if water else
               {"schema", "id", "floor_y_m", "center_xz_m", "interior_width_m", "interior_length_m", "rim_y_m", "seat_center_m", "seat_width_m", "seat_depth_m", "rim_hand_forward_m"})
    _keys(value, allowed, "context")
    need(set(value) == allowed, "context fields are required; unsupported parameters never silently ignored")
    c = copy.deepcopy(value)
    need(c["schema"] == ("oneirifact.water-context/v1" if water else "oneirifact.tub-context/v1"), "wrong context kind")
    need(isinstance(c["id"], str) and bool(c["id"]), "context id required")
    horizontal = "origin_xz_m" if water else "center_xz_m"
    need(isinstance(c[horizontal], list) and len(c[horizontal]) == 2, "context horizontal pair required")
    c[horizontal] = [number(v, horizontal) for v in c[horizontal]]
    for k in allowed - {"schema", "id", horizontal, "seat_center_m"}: c[k] = number(c[k], k)
    if water:
        need(0 < c["root_depth_m"] < c["depth_m"], "root must lie within positive water depth")
        need(c["forward_speed_m_s"] >= 0, "negative forward speed unsupported")
    else:
        c["seat_center_m"] = vec(c["seat_center_m"], "seat center")
        need(all(c[k] > 0 for k in ("interior_width_m", "interior_length_m", "seat_width_m", "seat_depth_m")), "positive tub dimensions required")
        need(c["floor_y_m"] < c["seat_center_m"][1] < c["rim_y_m"], "seat must be above floor and below rim")
        need(c["seat_width_m"] < c["interior_width_m"] and c["seat_depth_m"] < c["interior_length_m"], "seat must fit tub interior")
        need(abs(c["seat_center_m"][0]-c[horizontal][0])+c["seat_width_m"]/2 <= c["interior_width_m"]/2, "seat width lies outside tub")
        need(abs(c["seat_center_m"][2]-c[horizontal][1])+c["seat_depth_m"]/2 <= c["interior_length_m"]/2, "seat length lies outside tub")
    return c


def _anchors(m, measure, hip, root_q):
    transform = lambda point: add(hip, qrot(root_q, sub(point, m["hip_center_m"])))
    return {"hips_m": {s: transform(m["hips_m"][s]) for s in SIDES},
            "shoulders_m": {s: transform(measure["arms"][s]["shoulder_m"]) for s in SIDES},
            "head_m": transform(m["landmarks_m"]["head"]),
            "mouth_m": transform(m["landmarks_m"]["mouth"]),
            "chest_surface_anchor_m": transform(measure["chest_surface_anchor_m"])}


def _free_foot(m, s, ankle, foot_q, hip, phase):
    foot = m["feet"][s]
    points = {name+"_m": add(ankle, qrot(foot_q, foot[name+"_from_ankle_m"])) for name in ("heel", "forefoot", "toe")}
    return {"ankle_m": ankle, "rotation_xyzw": foot_q, **points, "toe_flexion_rad": 0.,
            "contacts": {"heel": False, "forefoot": False}, "contact_reference": "none",
            "stance": False, "phase_mode": "flutter_kick", "support_regions": [],
            "leg_phase": phase, "knee_pole_m": add(hip, [0., -.4, -.15]), "pole_reference": "world"}


def _swim_frame(m, legs, measure, c, d, source_t):
    period = d["period_s"]
    p = (source_t/period) % 1.
    angle = 2*math.pi*p
    roll = -math.radians(d["body_roll_deg"])*math.sin(angle)
    root_q = qmul(quaternion([0., 0., 1.], roll), quaternion([1., 0., 0.], math.radians(d["root_prone_rotation_x_deg"])))
    hip = [c["origin_xz_m"][0], c["surface_y_m"]-c["root_depth_m"], c["origin_xz_m"][1]+c["forward_speed_m_s"]*source_t]
    a = _anchors(m, measure, hip, root_q)
    feet, hands, targets, poles, phases = {}, {}, {}, {}, {}
    for s, offset, sign in (("L", 0., 1), ("R", .5, -1)):
        arm_phase = (p+offset) % 1.
        theta = 2*math.pi*arm_phase
        length = measure["arms"][s]["total_m"]
        shoulder = a["shoulders_m"][s]
        wrist = [shoulder[0]+sign*d["arm_lateral_offset_ratio"]*length,
                 c["surface_y_m"]-d["arm_vertical_radius_ratio"]*length*math.sin(theta),
                 shoulder[2]+d["arm_longitudinal_reach_ratio"]*length*math.cos(theta)]
        hands[s] = wrist
        phases[s] = {"phase": arm_phase, "mode": "underwater_pull" if arm_phase < .5 else "above_surface_recovery"}
        targets[s] = {"position_m": wrist, "reference": "world", "semantic": "front_crawl_wrist_path", "phase": phases[s], "contact_asserted": False}
        poles[s] = {"position_m": add(shoulder, [sign*.65*length, -.30*length*math.sin(theta), -.05*length]), "reference": "world"}
        leg_phase = (d["flutter_cycles_per_stroke"]*p+offset) % 1.
        kick = math.sin(2*math.pi*leg_phase)
        length_leg = legs[s]["total_m"]
        local = [sign*.035*length_leg, -d["leg_extension_ratio"]*length_leg, -d["kick_amplitude_leg_ratio"]*length_leg*kick]
        ankle = add(a["hips_m"][s], qrot(root_q, local))
        foot_q = qmul(root_q, quaternion([1., 0., 0.], math.radians(d["plantar_flexion_deg"]+d["plantar_flexion_amplitude_deg"]*kick)))
        feet[s] = _free_foot(m, s, ankle, foot_q, a["hips_m"][s], leg_phase)
        feet[s]["knee_pole_m"] = add(a["hips_m"][s], qrot(root_q, [0., -.35*length_leg, .5*length_leg]))
    breath_side = d["breathing_side"]
    bp = phases[breath_side]["phase"]
    lo, hi = d["breathing_recovery_window"]
    # A compact sine-squared pulse is C1 at both breathing window boundaries.
    amount = math.sin(math.pi*(bp-lo)/(hi-lo))**2 if lo < bp < hi else 0.
    head_turn = (-1 if breath_side == "R" else 1)*math.radians(d["breathing_turn_deg"])*amount
    return {"phase": p, "hip_center_m": hip, "root_orientation_xyzw": root_q, "body_anchors": a,
            "feet": feet, "hands_m": hands, "hand_targets": targets, "arm_poles": poles,
            "joint_intents": {"head_axial_rotation_rad": head_turn, "head_orientation_xyzw": qmul(root_q, quaternion([0., 1., 0.], head_turn)),
                              "breathing": {"side": breath_side, "turn_fraction": amount, "airway_clearance": "NOT_QUALIFIED"}},
            "prop_contacts": [], "props": [{"id": c["id"], "kind": "water_context", "reference": "world", "surface_y_m": c["surface_y_m"], "depth_m": c["depth_m"], "support_asserted": False}]}


def _bath_frame(m, legs, measure, shoe, c, d, source_t):
    p = (source_t/d["period_s"]) % 1.
    average_leg = sum(v["total_m"] for v in legs.values())/2
    root_q = [0., 0., 0., 1.]
    hip = add(c["seat_center_m"], [0., d["hip_above_seat_leg_ratio"]*average_leg, 0.])
    a = _anchors(m, measure, hip, root_q)
    feet = {}
    for s in SIDES:
        binding = core._foot_binding(m["feet"][s], shoe)
        x = hip[0]+m["ankles_m"][s][0]-m["hip_center_m"][0]
        z = hip[2]+d["foot_forward_leg_ratio"]*legs[s]["total_m"]
        foot = core._foot_pose(binding, shoe, [x, z])
        shift = [0., c["floor_y_m"], 0.]
        for k in ("ankle_m", "heel_m", "forefoot_m", "toe_m"): foot[k] = add(foot[k], shift)
        foot["contact_reference"] = "world:tub:floor"
        foot["phase_mode"] = "tub_seated_support"
        foot["pole_reference"] = "world"
        foot["knee_pole_m"] = add(a["hips_m"][s], [0., 0., .5*legs[s]["total_m"]])
        for region in foot["support_regions"]:
            region["reference"] = "world:tub:floor"
            region["center_m"] = add(region["center_m"], shift)
        feet[s] = foot
    side = m["dominant_hand"]
    other = "L" if side == "R" else "R"
    theta = 2*math.pi*p
    r = d["wash_radius_stature_ratio"]*m["stature_m"]
    relative = [r*math.cos(theta), r*math.sin(theta), d["sponge_standoff_stature_ratio"]*m["stature_m"]]
    wrist = add(a["chest_surface_anchor_m"], relative)
    rim = [c["center_xz_m"][0]+(1 if other == "L" else -1)*c["interior_width_m"]/2,
           c["rim_y_m"], hip[2]+c["rim_hand_forward_m"]]
    hands = {side: wrist, other: rim}
    targets = {side: {"position_m": wrist, "reference": "body:chest_surface_anchor", "offset_m": relative,
                      "semantic": "sponge_wrist_path", "contact_asserted": False},
               other: {"position_m": rim, "reference": "world:tub:rim", "semantic": "stationary_rim_support_intent", "contact_asserted": False}}
    poles = {s: {"position_m": add(a["shoulders_m"][s], [(1 if s == "L" else -1)*.5*measure["arms"][s]["total_m"], -.5*measure["arms"][s]["total_m"], .1*measure["arms"][s]["total_m"]]), "reference": "world"} for s in SIDES}
    head_down = math.radians(d["head_down_deg"])
    return {"phase": p, "hip_center_m": hip, "root_orientation_xyzw": root_q, "body_anchors": a,
            "feet": feet, "hands_m": hands, "hand_targets": targets, "arm_poles": poles,
            "joint_intents": {"head_flexion_rad": head_down, "head_orientation_xyzw": quaternion([1., 0., 0.], head_down)},
            "prop_contacts": [{"actor": "pelvis", "target": "world:tub:seat", "point_m": c["seat_center_m"], "kind": "seat_support_intent", "contact_verified": False},
                              {"actor": "hand."+other, "target": "world:tub:rim", "point_m": rim, "kind": "rim_support_intent", "contact_verified": False},
                              {"actor": "hand."+side, "target": "sponge", "kind": "attachment_intent", "contact_verified": False}],
            "props": [{"id": c["id"], "kind": "tub_context", "reference": "world", "dimensions": c},
                      {"id": "sponge", "kind": "authored_prop", "reference": "hand."+side, "position_m": wrist,
                       "orientation_xyzw": [0., 0., 0., 1.], "radius_m": d["sponge_radius_stature_ratio"]*m["stature_m"], "contact_verified": False}]}


def reach_screen(frame, legs, measure):
    """Necessary two-link annulus only; no native IK or joint-limit PASS."""
    rows = []
    for s in SIDES:
        for limb, start, target, upper, lower in (
            ("leg", frame["body_anchors"]["hips_m"][s], frame["feet"][s]["ankle_m"], legs[s]["thigh_m"], legs[s]["shank_m"]),
            ("arm", frame["body_anchors"]["shoulders_m"][s], frame["hands_m"][s], measure["arms"][s]["upper_m"], measure["arms"][s]["lower_m"])):
            distance = norm(sub(target, start))
            lo, hi = abs(upper-lower), upper+lower
            margin = min(distance-lo, hi-distance)
            rows.append({"side": s, "limb": limb, "distance_m": distance, "minimum_m": lo, "maximum_m": hi,
                         "margin_m": margin, "status": "PASS_DISTANCE_SCREEN" if margin >= -1e-9 else "FAIL_DISTANCE_SCREEN"})
    return rows


def context_screen(frame, context, activity_id):
    """Target/context geometry screens, distinct from whole-mesh collision."""
    if activity_id == "swimming_front_crawl":
        points = list(frame["hands_m"].values()) + [frame["hip_center_m"]]
        points += [frame["feet"][s][k] for s in SIDES for k in ("ankle_m", "heel_m", "forefoot_m", "toe_m")]
        margin = min(p[1] for p in points) - (context["surface_y_m"]-context["depth_m"])
        return {"status": "PASS" if margin >= 0 else "FAIL", "minimum_bottom_clearance_m": margin,
                "scope": "selected targets against water bottom plane; full-body collision NOT_RUN"}
    x, z = context["center_xz_m"]
    margins = []
    for side in SIDES:
        for key in ("heel_m", "forefoot_m", "toe_m"):
            p = frame["feet"][side][key]
            margins += [context["interior_width_m"]/2-abs(p[0]-x), context["interior_length_m"]/2-abs(p[2]-z)]
            if abs(p[1]-context["floor_y_m"]) > 1e-8: margins.append(-abs(p[1]-context["floor_y_m"]))
    minimum = min(margins)
    return {"status": "PASS" if minimum >= -1e-9 else "FAIL", "minimum_sole_to_tub_edge_m": minimum,
            "scope": "authored sole markers on bounded tub floor; full-body/seat/rim collision NOT_RUN"}


def compile_clip(activity_id, morphology, footwear, context, *, limb_measurements, seed=24601, fps=24, duration_s=None, start_time_s=0.):
    lib = library()
    need(activity_id in lib["activities"], "unsupported aquatic activity")
    d = lib["activities"][activity_id]
    m, legs = core.validate_morphology(morphology)
    measure = _measurement(limb_measurements, m)
    shoe = core.validate_footwear(footwear, m)
    need(shoe["id"] in d["supported_footwear"] and shoe["heel_stack_m"] == 0. and shoe["forefoot_stack_m"] == 0., "aquatic prototype supports measured barefoot only; shoe adaptation unsupported")
    c = _context(activity_id, context)
    need(type(seed) is int and 0 <= seed < 2**53, "seed must be a nonnegative integer")
    fps = number(fps, "fps")
    need(1 <= fps <= 120, "fps must be in [1,120]")
    duration = d["period_s"]*d["default_cycles"] if duration_s is None else number(duration_s, "duration")
    start = number(start_time_s, "start time")
    need(0 < duration <= 60 and 0 <= start <= 3600, "bounded positive duration and nonnegative seek required")
    count = math.ceil(duration*fps)
    times = [min(i/fps, duration) for i in range(count+1)]
    frames = []
    for t in times:
        frame = (_swim_frame(m, legs, measure, c, d, start+t) if activity_id == "swimming_front_crawl"
                 else _bath_frame(m, legs, measure, shoe, c, d, start+t))
        frame.update(time_s=t, source_time_s=start+t)
        frame["reach_screen"] = reach_screen(frame, legs, measure)
        frame["context_geometry_screen"] = context_screen(frame, c, activity_id)
        frames.append(frame)
    failures = [{"time_s": f["time_s"], **row} for f in frames for row in f["reach_screen"] if row["status"].startswith("FAIL")]
    # Invalid physical context returns truthful diagnostic targets; never clips,
    # scales, stretches, or silently substitutes a feasible trajectory.
    cycle_delta = [0., 0., c["forward_speed_m_s"]*d["period_s"]] if activity_id == "swimming_front_crawl" else [0., 0., 0.]
    instance = {"activity_id": activity_id, "morphology": m, "limb_measurements": measure, "footwear": shoe,
                "context": c, "seed": seed, "seed_semantics": "provenance only; no random process", "fps": fps,
                "duration_s": duration, "start_time_s": start, "source_bind_sha256": m["source_bind_sha256"],
                "source_revision": m["source_revision"], "root_cycle_delta_m": cycle_delta}
    definition = {"library_id": lib["id"], "library_version": lib["version"], "activity": d,
                  "compiler_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "frozen_core_sha256": CORE_SHA256,
                  "frozen_core_library_sha256": CORE_LIBRARY_SHA256}
    result = {"schema": "oneirifact.aquatic-intent-clip/v1", "definition": definition, "definition_sha256": digest(definition),
              "instance": instance, "instance_sha256": digest(instance), "frames": frames,
              "loop": {"enabled": True, "period_s": d["period_s"], "cycle_delta_m": cycle_delta,
                       "static_world_contexts_repeat_without_translation": True},
              "qualification": {**lib["qualification"], "reach_distance_screen": "FAIL" if failures else "PASS", "reach_failures": failures,
                                "context_geometry_screen": "FAIL" if any(f["context_geometry_screen"]["status"] == "FAIL" for f in frames) else "PASS"},
              "consumer_contract": {"target_coordinates": "world", "reference_semantics": "world targets are already resolved; body-relative targets carry explicit anchor and offset",
                                    "must_rotate_rest_hip_and_shoulder_offsets": True, "must_not_translate_world_hands_by_mouth": True,
                                    "must_not_stretch_source_limb_segments": True}}
    result["clip_sha256"] = digest(result)
    return result
