"""Thin deterministic activity intent compiler; native consumer owns IK.

No motion capture, force solver, collision repair or realism qualification.
Definitions, resolved instances, desired targets and observed consumer poses are
separate objects. Morphology is measured after shape edits, before pose binding.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

LIBRARY_PATH = Path(__file__).with_name("library.json")
ALIASES = {"stand": "standing", "sit": "sitting", "crouch": "crouching", "squat": "squatting",
           "walk": "walking", "jog": "jogging", "run": "running", "brush": "brushing_teeth",
           "icecream": "eating_ice_cream_cone"}


class UnsupportedActivity(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def library():
    value = json.loads(LIBRARY_PATH.read_text())
    _keys(value, {"schema", "id", "version", "authorship", "coordinates", "evaluation_order", "realism_qualification", "composition", "activities", "footwear_profiles"}, "library definition")
    allowed = {"implementation", "kind", "duration_s", "period_s", "loop", "contacts", "props", "limits", "from", "to", "base",
               "hip_height_leg_ratio", "hip_back_leg_ratio", "spine_flexion_deg", "stagger_leg_ratio", "stride_leg_ratio", "stance_fraction",
               "hip_bounce_leg_ratio", "swing_clearance_leg_ratio", "heel_strike_deg", "toe_off_deg", "arm_swing_deg", "required_landmarks", "blocked_by", "physics_qualification"}
    for key, item in value["activities"].items(): _keys(item, allowed, "activity definition "+key)
    return value


def need(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name):
    need(type(value) in (int, float) and math.isfinite(value), name + " must be a finite numeric value, not bool/string")
    return float(value)


def vec(value, name):
    need(isinstance(value, (list, tuple)) and len(value) == 3, name + " must have three coordinates")
    result = [number(x, name) for x in value]
    return result


def add(a, b): return [x + y for x, y in zip(a, b)]
def sub(a, b): return [x - y for x, y in zip(a, b)]
def mul(a, k): return [x * k for x in a]
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))
def cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def unit(a):
    n = norm(a)
    need(n > 1e-10, "degenerate direction")
    return mul(a, 1/n)


def rotate(vector, axis, angle):
    c, s = math.cos(angle), math.sin(angle)
    return add(add(mul(vector, c), mul(cross(axis, vector), s)), mul(axis, dot(axis, vector)*(1-c)))


def quaternion(axis, angle):
    return mul(axis, math.sin(angle/2)) + [math.cos(angle/2)]


def ease(value):
    t = min(1., max(0., value))
    return t*t*t*(10+t*(-15+6*t))


def _keys(value, allowed, name):
    unknown = sorted(set(value) - set(allowed))
    need(not unknown, name + " has unsupported fields: " + ",".join(unknown))


def validate_morphology(value):
    allowed = {"id", "source_bind_sha256", "source_revision", "stature_m", "hip_center_m", "hips_m", "knees_m", "ankles_m",
               "feet", "shoulder_width_m", "thigh_radius_m", "clearance_m", "landmarks_m", "dominant_hand", "measurement_notes"}
    _keys(value, allowed, "morphology")
    result = copy.deepcopy(value)
    need(isinstance(result.get("id"), str) and bool(result["id"]), "morphology id required")
    bind = result.get("source_bind_sha256", "")
    need(bind == "UNVERIFIED_SYNTHETIC" or (len(bind) == 64 and all(x in "0123456789abcdef" for x in bind)), "source bind SHA256 required")
    for name in ("stature_m",):
        result[name] = number(result[name], name)
        need(result[name] > 0, name + " must be positive")
    result["hip_center_m"] = vec(result["hip_center_m"], "hip center")
    lengths = {}
    for side in ("L", "R"):
        for field in ("hips_m", "knees_m", "ankles_m"):
            _keys(result[field], {"L", "R"}, field)
            result[field][side] = vec(result[field][side], field + side)
        thigh = norm(sub(result["hips_m"][side], result["knees_m"][side]))
        shin = norm(sub(result["knees_m"][side], result["ankles_m"][side]))
        need(thigh > .01 and shin > .01, "degenerate measured leg")
        lengths[side] = {"thigh_m": thigh, "shank_m": shin, "total_m": thigh+shin}
        foot = result["feet"][side]
        _keys(foot, {"heel_from_ankle_m", "forefoot_from_ankle_m", "toe_from_ankle_m", "toe_pivot_from_ankle_m", "width_m"}, "foot")
        for field in ("heel_from_ankle_m", "forefoot_from_ankle_m", "toe_from_ankle_m", "toe_pivot_from_ankle_m"):
            foot[field] = vec(foot[field], field)
        foot["width_m"] = number(foot["width_m"], "foot width")
        need(foot["width_m"] > 0, "positive foot width")
        need(foot["forefoot_from_ankle_m"][2] > foot["heel_from_ankle_m"][2] and foot["toe_from_ankle_m"][2] >= foot["forefoot_from_ankle_m"][2], "sole landmarks must use canonical +Z forward")
    _keys(result["feet"], {"L", "R"}, "feet")
    result.setdefault("clearance_m", .015)
    result.setdefault("thigh_radius_m", .035*result["stature_m"])
    result.setdefault("shoulder_width_m", norm(sub(result["hips_m"]["L"], result["hips_m"]["R"]))*1.8)
    for field in ("clearance_m", "thigh_radius_m", "shoulder_width_m"):
        result[field] = number(result[field], field)
        need(result[field] >= 0, field + " must be nonnegative")
    result.setdefault("landmarks_m", {})
    _keys(result["landmarks_m"], {"mouth", "head", "shoulder_L", "shoulder_R", "wrist_L", "wrist_R"}, "landmarks")
    result["landmarks_m"] = {k: vec(v, k) for k, v in result["landmarks_m"].items()}
    result.setdefault("dominant_hand", "R")
    need(result["dominant_hand"] in ("L", "R"), "dominant_hand must be L or R")
    return result, lengths


def footwear_from_profile(profile_id, morphology):
    m, _ = validate_morphology(morphology)
    profiles = library()["footwear_profiles"]
    need(profile_id in profiles, "unsupported footwear profile " + str(profile_id))
    p = profiles[profile_id]
    length = sum(norm(sub(m["feet"][s]["toe_from_ankle_m"], m["feet"][s]["heel_from_ankle_m"])) for s in ("L", "R"))/2
    width = sum(m["feet"][s]["width_m"] for s in ("L", "R"))/2
    return {"id": profile_id, "heel_stack_m": p["heel_stack_foot_length_ratio"]*length,
            "forefoot_stack_m": p["forefoot_stack_foot_length_ratio"]*length,
            "heel_footprint_m": [p["heel_width_foot_width_ratio"]*width, p["heel_length_foot_length_ratio"]*length],
            "forefoot_footprint_m": [p["forefoot_width_foot_width_ratio"]*width, p["forefoot_length_foot_length_ratio"]*length],
            "toe_pivot_fraction": 0.0, "measured_foot_length_m": length, "measured_foot_width_m": width,
            "profile_definition_sha256": digest(p)}


def validate_footwear(value, morphology):
    _keys(value, {"id", "heel_stack_m", "forefoot_stack_m", "heel_footprint_m", "forefoot_footprint_m", "toe_pivot_fraction",
                  "measured_foot_length_m", "measured_foot_width_m", "profile_definition_sha256"}, "footwear")
    f = copy.deepcopy(value)
    need(isinstance(f.get("id"), str) and bool(f["id"]), "footwear id required")
    for field in ("heel_stack_m", "forefoot_stack_m"):
        f[field] = number(f[field], field)
        need(f[field] >= 0, "nonnegative footwear stack required")
    for field in ("heel_footprint_m", "forefoot_footprint_m"):
        need(isinstance(f[field], list) and len(f[field]) == 2, "footprint width/length required")
        f[field] = [number(x, field) for x in f[field]]
        need(all(x > 0 for x in f[field]), "positive footprint width/length required")
    need(number(f.get("toe_pivot_fraction"), "toe pivot fraction") == 0., "only measured toe-base pivot (toe_pivot_fraction=0) implemented")
    minimum_width = min(morphology["feet"][s]["width_m"] for s in ("L", "R"))
    need(max(f["heel_footprint_m"][0], f["forefoot_footprint_m"][0]) <= 1.3*minimum_width, "support width incompatible with measured foot; bespoke oversized footwear unsupported")
    return f


def _foot_binding(foot, shoe):
    heel, fore, toe = (foot[k] for k in ("heel_from_ankle_m", "forefoot_from_ankle_m", "toe_from_ankle_m"))
    delta = sub(fore, heel)
    horizontal = math.hypot(delta[0], delta[2])
    radius = math.hypot(delta[1], horizontal)
    need(horizontal > .015, "heel to forefoot baseline too short")
    stack_difference = shoe["forefoot_stack_m"] - shoe["heel_stack_m"]
    need(abs(stack_difference) < radius*.95, "shoe stack difference not supported by measured foot baseline")
    pitch = math.atan2(delta[1], horizontal) - math.asin(stack_difference/radius)
    axis = unit(cross([0., 1., 0.], [delta[0], 0., delta[2]]))
    # Calibrate fixed shoe points once in the unposed foot frame. The shoe's
    # stack directions subsequently rotate with the shoe, not with world -Y.
    heel_out = sub(heel, rotate([0., shoe["heel_stack_m"], 0.], axis, -pitch))
    fore_out = sub(fore, rotate([0., shoe["forefoot_stack_m"], 0.], axis, -pitch))
    toe_out = sub(toe, rotate([0., shoe["forefoot_stack_m"], 0.], axis, -pitch))
    rh, rf = rotate(heel_out, axis, pitch), rotate(fore_out, axis, pitch)
    ankle_y = -rf[1]
    need(abs(ankle_y + rh[1]) < 1e-9, "shoe support geometry mismatch")
    binding = {"axis": axis, "pitch": pitch, "standing_ankle_y": ankle_y,
               "heel": heel, "forefoot": fore, "toe": toe, "toe_pivot": foot["toe_pivot_from_ankle_m"],
               "heel_outsole": heel_out, "forefoot_outsole": fore_out, "toe_outsole": toe_out}
    binding["standing_toe_flex"] = _toe_contact_flex(binding, pitch, ankle_y)
    return binding


def _toe_contact_flex(binding, pitch, ankle_y):
    axis = binding["axis"]
    pivot_y = ankle_y + rotate(binding["toe_pivot"], axis, pitch)[1]
    v = sub(binding["toe_outsole"], binding["toe_pivot"])
    forward = cross(axis, [0., 1., 0.])
    longitudinal = dot(v, forward)
    radius = math.hypot(v[1], longitudinal)
    need(radius > .005 and abs(pivot_y) <= radius+1e-10, "toe contact unreachable for measured pivot and footwear")
    total_angle = math.atan2(v[1], longitudinal)-math.asin(max(-1., min(1., -pivot_y/radius)))
    return total_angle-pitch


def _foot_pose(binding, shoe, ankle_xz, mode="flat", roll_angle=0., clearance=0., anchor=None, toe_flex_override=None):
    pitch = binding["pitch"] + roll_angle
    axis = binding["axis"]
    rh = rotate(binding["heel_outsole"], axis, pitch)
    rf = rotate(binding["forefoot_outsole"], axis, pitch)
    support = "heel" if mode == "heel" else "forefoot"
    support_offset = rh if mode == "heel" else rf
    support_ankle_y = -support_offset[1]
    toe_flex = (_toe_contact_flex(binding, pitch, support_ankle_y) if mode in ("flat", "toe")
                else binding["standing_toe_flex"])
    if toe_flex_override is not None: toe_flex = toe_flex_override
    rt = add(rotate(binding["toe_pivot"], axis, pitch),
             rotate(sub(binding["toe_outsole"], binding["toe_pivot"]), axis, pitch+toe_flex))
    offsets = {"heel": rh, "forefoot": rf, "toe": rt}
    if mode == "swing":
        ankle = [ankle_xz[0], clearance-min(v[1] for v in offsets.values()), ankle_xz[1]]
    else:
        if anchor is None:
            ankle = [ankle_xz[0], -offsets[support][1], ankle_xz[1]]
        else:
            ankle = sub(anchor, offsets[support])
    points = {k: add(ankle, v) for k, v in offsets.items()}
    contacts = {"heel": mode in ("flat", "heel"), "forefoot": mode in ("flat", "toe")}
    regions = []
    for region, active in contacts.items():
        if active:
            center = points[region]
            w, length = shoe[region+"_footprint_m"]
            regions.append({"region": region, "reference": "world:ground_y0", "center_m": center,
                            "footprint_width_length_m": [w, length]})
    return {"ankle_m": ankle, "rotation_xyzw": quaternion(axis, pitch), "pitch_axis_unit": axis,
            "heel_m": points["heel"], "forefoot_m": points["forefoot"], "toe_m": points["toe"],
            "contacts": contacts, "contact_reference": "world:ground_y0", "stance": mode != "swing",
            "phase_mode": mode, "toe_flexion_rad": toe_flex, "support_regions": regions}


def _upper_targets(activity, m, hip, t, definition):
    relative_shift = sub(hip, m["hip_center_m"])
    side = m["dominant_hand"]
    hands, contacts, props = {}, [], []
    if activity == "showering":
        head = add(m["landmarks_m"]["head"], relative_shift)
        for sign, s in ((1, "L"), (-1, "R")):
            hands[s] = add(head, [sign*.045*m["stature_m"], .012*math.sin(2*math.pi*t/definition["period_s"]), .025])
            contacts.append({"actor": "hand."+s, "target": "head", "kind": "authored_task_target", "contact_verified": False})
        props.append({"id": "shower_stream_context", "implementation": "CONTEXT_ONLY", "water_mechanics": "NOT_RUN"})
    else:
        mouth = add(m["landmarks_m"]["mouth"], relative_shift)
        if activity == "brushing_teeth":
            tip = add(mouth, [.009*math.sin(2*math.pi*t/definition["period_s"]), 0., .015])
            hands[side] = add(tip, [.04 if side == "L" else -.04, -.035, .09])
            props.append({"id": "toothbrush", "attachment": "hand."+side, "tip_target_m": tip,
                          "handle_length_m": .075*m["stature_m"], "contact_verified": False})
        else:
            approach = .5-.5*math.cos(2*math.pi*t/definition["period_s"])
            tip = add(mouth, [0., -.12*(1-approach), .025+.10*(1-approach)])
            hands[side] = add(tip, [0., -.085*m["stature_m"], 0.])
            props.append({"id": "ice_cream_cone", "attachment": "hand."+side, "tip_target_m": tip,
                          "cone_height_m": .07*m["stature_m"], "scoop_radius_m": .018*m["stature_m"], "contact_verified": False})
        contacts.append({"actor": "hand."+side, "target": props[0]["id"], "kind": "prop_attachment_intent", "contact_verified": False})
    return hands, contacts, props


def compile_clip(activity_id, morphology, footwear, *, seed=24501, fps=24, duration_s=None, start_time_s=0.0):
    """Return desired contact/pose targets, never actual FK or realism acceptance."""
    lib = library()
    activity_id = ALIASES.get(activity_id, activity_id)
    need(activity_id in lib["activities"], "unknown activity "+str(activity_id))
    definition = lib["activities"][activity_id]
    if definition["implementation"] == "PLANNED":
        raise UnsupportedActivity(activity_id+": "+"; ".join(definition["blocked_by"]))
    need(activity_id in {"standing", "sitting", "sit_to_stand", "crouching", "squatting", "walking", "jogging", "running", "showering", "brushing_teeth", "eating_ice_cream_cone"}, "activity has no implemented compiler adapter")
    m, lengths = validate_morphology(morphology)
    shoe = validate_footwear(footwear, m)
    for name in definition.get("required_landmarks", []):
        need(name in m["landmarks_m"], "actual measured landmark required: "+name)
    need(type(seed) is int and type(fps) is int and 1 <= fps <= 120, "integer seed/fps, not bool; fps in1..120")
    duration = number(definition["duration_s"] if duration_s is None else duration_s, "duration")
    start_time_s = number(start_time_s, "start time")
    need(0 < duration <= 120 and start_time_s >= 0, "bounded positive duration and nonnegative seek")
    bindings = {s: _foot_binding(m["feet"][s], shoe) for s in ("L", "R")}
    leg = sum(lengths[s]["total_m"] for s in ("L", "R"))/2
    ankle_height = sum(bindings[s]["standing_ankle_y"] for s in ("L", "R"))/2
    old_ankle_height = sum(m["ankles_m"][s][1] for s in ("L", "R"))/2
    hip_stand = add(m["hip_center_m"], [0., ankle_height-old_ankle_height, 0.])
    period = definition.get("period_s", duration)
    gait = definition["kind"] == "gait"
    stride = definition.get("stride_leg_ratio", 0.)*leg
    speed = stride/period if gait else 0.
    total = int(round(duration*fps))
    times = [i/fps for i in range(total+1)]
    if times[-1] < duration-1e-9: times.append(duration)
    elif times[-1] > duration+1e-9: times[-1] = duration
    frames, reachability = [], []
    props_static = []
    if activity_id in ("sitting", "sit_to_stand"):
        props_static.append({"id": "chair", "kind": "authored_support_geometry", "seat_height_m": ankle_height+.43*leg,
                             "seat_width_m": max(m["shoulder_width_m"], 2*m["thigh_radius_m"]+m["clearance_m"]),
                             "seat_depth_m": .44*leg, "seat_center_m": [hip_stand[0], ankle_height+.43*leg, hip_stand[2]-.31*leg],
                             "contact_verified": False})
    for local_t in times:
        t = start_time_s+local_t
        phase = (t/period)%1 if definition.get("loop") else min(1., t/period)
        hip = list(hip_stand)
        spine = math.radians(definition.get("spine_flexion_deg", 0.))
        if gait:
            hip[1] = ankle_height+leg*(definition["hip_height_leg_ratio"]+definition["hip_bounce_leg_ratio"]*math.cos(4*math.pi*phase))
            hip[2] += speed*t
        elif activity_id in ("sitting", "crouching"):
            hip[1] = ankle_height+definition["hip_height_leg_ratio"]*leg
            hip[2] -= definition["hip_back_leg_ratio"]*leg
        elif activity_id == "squatting":
            depth = .5-.5*math.cos(2*math.pi*phase)
            hip[1] += depth*(ankle_height+definition["hip_height_leg_ratio"]*leg-hip_stand[1])
            hip[2] -= depth*definition["hip_back_leg_ratio"]*leg
            spine *= depth
        elif activity_id == "sit_to_stand":
            u = min(1., max(0., t/duration))
            # Keep the pelvis at the authored seat during preparation. Release
            # seat contact before translating it; feet retain their world anchors.
            blend = ease((u-.15)/.85)
            hip[1] = (1-blend)*(ankle_height+.52*leg)+blend*hip_stand[1]
            hip[2] -= (1-blend)*.31*leg
            spine = math.radians(8)*(1-blend)+math.radians(22)*math.sin(math.pi*u)**2
        feet = {}
        for side in ("L", "R"):
            ankle = m["ankles_m"][side]
            xz = [ankle[0], ankle[2]]
            binding = bindings[side]
            if gait:
                offset = 0. if side == "L" else .5
                cycle_coordinate = t/period+offset
                cycle = math.floor(cycle_coordinate)
                p = cycle_coordinate-cycle
                stance = definition["stance_fraction"]
                contact_time = (cycle-offset+stance/2)*period
                contact_ankle_z = ankle[2]+speed*contact_time
                flat = _foot_pose(binding, shoe, [ankle[0], contact_ankle_z])
                if p < stance:
                    stance_phase = p/stance
                    if stance_phase < .16 and definition["heel_strike_deg"] > 0:
                        angle = -math.radians(definition["heel_strike_deg"])*(1-ease(stance_phase/.16))
                        foot = _foot_pose(binding, shoe, xz, "heel", angle, anchor=flat["heel_m"])
                    elif stance_phase > .76:
                        angle = math.radians(definition["toe_off_deg"])*ease((stance_phase-.76)/.24)
                        foot = _foot_pose(binding, shoe, xz, "toe", angle, anchor=flat["forefoot_m"])
                    else:
                        foot = flat
                else:
                    swing = (p-stance)/(1-stance)
                    takeoff_angle = math.radians(definition["toe_off_deg"])
                    landing_angle = -math.radians(definition["heel_strike_deg"])
                    takeoff = _foot_pose(binding, shoe, xz, "toe", takeoff_angle, anchor=flat["forefoot_m"])
                    next_flat = _foot_pose(binding, shoe, [ankle[0], contact_ankle_z+stride])
                    landing_mode = "heel" if definition["heel_strike_deg"] > 0 else "flat"
                    landing_anchor = next_flat["heel_m"] if landing_mode == "heel" else next_flat["forefoot_m"]
                    landing = _foot_pose(binding, shoe, xz, landing_mode, landing_angle, anchor=landing_anchor)
                    blend = ease(swing)
                    swing_xz = [(1-blend)*takeoff["ankle_m"][i]+blend*landing["ankle_m"][i] for i in (0, 2)]
                    roll = (1-blend)*takeoff_angle+blend*landing_angle-math.radians(8)*math.sin(math.pi*swing)**2
                    toe_flex = (1-blend)*takeoff["toe_flexion_rad"]+blend*landing["toe_flexion_rad"]
                    clearance = max(m["clearance_m"], definition["swing_clearance_leg_ratio"]*leg)*math.sin(math.pi*swing)**2
                    foot = _foot_pose(binding, shoe, swing_xz, "swing", roll, clearance, toe_flex_override=toe_flex)
                foot["cycle_index"] = cycle
                foot["leg_phase"] = p
            else:
                if activity_id == "crouching": xz[1] += (1 if side == "L" else -1)*definition["stagger_leg_ratio"]*leg
                foot = _foot_pose(binding, shoe, xz)
            feet[side] = foot
            hip_joint = add(hip, sub(m["hips_m"][side], m["hip_center_m"]))
            distance = norm(sub(foot["ankle_m"], hip_joint))
            reachability.append({"time_s": local_t, "side": side, "hip_to_ankle_m": distance,
                                 "minimum_m": abs(lengths[side]["thigh_m"]-lengths[side]["shank_m"]),
                                 "maximum_m": lengths[side]["total_m"],
                                 "within_two_link_distance": abs(lengths[side]["thigh_m"]-lengths[side]["shank_m"])-1e-8 <= distance <= lengths[side]["total_m"]+1e-8})
            foot["knee_pole_m"] = add(hip_joint, [0., -.35*leg, 1.1*leg])
        prop_contacts = []
        if activity_id == "sitting" or (activity_id == "sit_to_stand" and t/duration < .15):
            prop_contacts.append({"actor": "pelvis", "target": "chair:seat", "reference": "world:chair", "kind": "support_intent", "contact_verified": False})
        hands, task_contacts, task_props = {}, [], []
        if definition["kind"] == "upper_body":
            hands, task_contacts, task_props = _upper_targets(activity_id, m, hip, t, definition)
        arm = math.radians(definition.get("arm_swing_deg", 0.))*math.sin(2*math.pi*phase)
        frames.append({"time_s": local_t, "source_time_s": t, "phase": phase, "hip_center_m": hip,
                       "root_orientation_xyzw": [0., 0., 0., 1.], "feet": feet, "hands_m": hands,
                       "joint_intents": {"spine_flexion_rad": spine, "arm_swing_rad": {"L": -arm, "R": arm}},
                       "prop_contacts": prop_contacts+task_contacts, "props": task_props})
    instance = {"activity_id": activity_id, "morphology": m, "footwear": shoe, "seed": seed, "seed_usage": "provenance_only; no stochastic variation",
                "fps": fps, "duration_s": duration, "start_time_s": start_time_s,
                "morphology_sha256": digest(m), "footwear_sha256": digest(shoe), "source_bind_sha256": m["source_bind_sha256"]}
    result = {"schema": "oneirifact.activity-intent-clip/v0.1", "definition": {"library_id": lib["id"], "version": lib["version"], "library_sha256": digest(lib),
               "activity_id": activity_id, "activity_sha256": digest(definition)}, "instance": instance,
              "instance_sha256": digest(instance), "implementation": definition["implementation"], "qualification": "ILLUSTRATIVE_INTENT_ONLY",
              "coordinates": lib["coordinates"], "measured_leg_lengths": lengths, "props": props_static,
              "footwear_bindings": {s: {"pitch_axis_unit": b["axis"], "base_pitch_rad": b["pitch"],
                  "standing_ankle_y_m": b["standing_ankle_y"], "standing_toe_flexion_rad": b["standing_toe_flex"],
                  "heel_outsole_from_ankle_rest_m": b["heel_outsole"], "forefoot_outsole_from_ankle_rest_m": b["forefoot_outsole"],
                  "toe_outsole_from_ankle_rest_m": b["toe_outsole"], "toe_pivot_from_ankle_rest_m": b["toe_pivot"],
                  "semantics": "Fixed rest-frame shoe support points; heel/forefoot rotate rigidly with foot; toe articulates about measured toe joint."}
                  for s, b in bindings.items()},
              "loop": {"enabled": bool(definition.get("loop")), "period_s": period,
                       "cycle_delta_m": [0., 0., stride if gait else 0.], "contact_semantics": "phase-authored world contacts; translate next-cycle targets by cycle_delta_m"},
              "composition": {"base_layer": "lower_body_and_root", "upper_body_masks": ["hands", "arms", "spine", "props"],
                              "arbitrary_contact_transition": "UNSUPPORTED", "authored_transition": activity_id == "sit_to_stand"},
              "target_reachability": {"status": "PASS_DISTANCE_SCREEN" if all(x["within_two_link_distance"] for x in reachability) else "FAIL_DISTANCE_SCREEN",
                                      "scope": "Necessary two-link distance bound only, no native IK, joint range, collisions, balance or realism acceptance", "samples": reachability},
              "consumer_observations": "NOT_RUN", "frames": frames}
    result["clip_sha256"] = digest(result)
    return result


def compose_upper_body(base, overlay, *, mask=("hands", "arms", "props")):
    """Apply explicit upper-body masks; never blend foot contacts or root paths."""
    allowed = {"hands", "arms", "spine", "props"}
    need(mask and set(mask) <= allowed, "unsupported composition mask")
    need(overlay["definition"]["activity_id"] in ("showering", "brushing_teeth", "eating_ice_cream_cone"), "overlay must be a declared upper-body task prototype")
    for key in ("morphology_sha256", "footwear_sha256", "fps", "duration_s", "start_time_s"):
        need(base["instance"][key] == overlay["instance"][key], "incompatible layer instance: "+key)
    need([f["time_s"] for f in base["frames"]] == [f["time_s"] for f in overlay["frames"]], "layer time mismatch")
    result = copy.deepcopy(base)
    for actual, authored in zip(result["frames"], overlay["frames"]):
        shift = sub(actual["hip_center_m"], authored["hip_center_m"])
        if "hands" in mask:
            need(not actual["hands_m"], "hand target conflict; explicit replacement policy required")
            actual["hands_m"] = {s: add(p, shift) for s, p in authored["hands_m"].items()}
        if "arms" in mask:
            # A hand target overrides base arm swing for its side; the other arm
            # remains authored by the base. Native consumer still owns solving.
            for side in authored["hands_m"]: actual["joint_intents"]["arm_swing_rad"][side] = 0.
        if "spine" in mask: actual["joint_intents"]["spine_flexion_rad"] += authored["joint_intents"]["spine_flexion_rad"]
        if "props" in mask:
            need(not actual["props"], "prop layer conflict")
            actual["props"] = copy.deepcopy(authored["props"])
            for prop in actual["props"]:
                if "tip_target_m" in prop: prop["tip_target_m"] = add(prop["tip_target_m"], shift)
            actual["prop_contacts"].extend(copy.deepcopy(authored["prop_contacts"]))
    result["composition"]["applied_overlay"] = {"clip_sha256": overlay["clip_sha256"], "mask": list(mask), "method": "hip-relative upper-body target overlay; base contacts and root untouched"}
    result.pop("clip_sha256", None)
    result["clip_sha256"] = digest(result)
    return result
