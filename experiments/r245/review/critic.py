#!/usr/bin/env python3
"""Independent observations critic. No compiler, FK, Blender, or solver imports.

These are provisional engineering gates, not human-motion or clinical limits.
Targets are compared with evaluated observations; they are never observations.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "oneirifact.motion-consumer-observations/v1"
EXPECTED_MAKEHUMAN_INTERMEDIATES = {
    part+"."+side for part in ("upperleg02", "lowerleg02", "upperarm02", "lowerarm02") for side in ("L", "R")
}
THRESHOLDS = {
    "limb_length_drift_m": 0.0001,
    "ankle_target_error_m": 0.005,
    "pelvis_target_error_m": 0.005,
    "reach_excess_m": 0.0001,
    "planted_drift_m": 0.005,
    "planted_speed_m_s": 0.05,
    "ground_penetration_m": 0.002,
    "active_contact_height_error_m": 0.005,
    "rigid_sole_length_drift_m": 0.0001,
    "intermediate_rotation_drift_rad": 0.0001,
    "hand_target_error_m": 0.01,
    "loop_position_seam_m": 0.005,
}


def finite(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError("non-finite or non-numeric observation")
    return float(x)


def vector(x, n=3):
    if not isinstance(x, (list, tuple)) or len(x) != n:
        raise ValueError("observation vector has wrong shape")
    return [finite(v) for v in x]


def sub(a, b): return [x-y for x, y in zip(a, b)]
def norm(a): return math.sqrt(sum(x*x for x in a))
def distance(a, b): return norm(sub(a, b))


def quaternion_distance(a, b):
    a, b = vector(a, 4), vector(b, 4)
    na, nb = norm(a), norm(b)
    if abs(na-1) > 1e-4 or abs(nb-1) > 1e-4:
        raise ValueError("observed quaternion is not unit length")
    # q and -q represent the same rotation.
    cosine = min(1., max(0., abs(sum(x*y for x, y in zip(a, b))/(na*nb))))
    return 2*math.acos(cosine)


def gate(values, threshold, *, missing, scope):
    if not values:
        return {"status": "NOT_RUN", "reason": missing, "scope": scope, "sample_count": 0}
    maximum = max(values, key=lambda x: x[0])
    return {"status": "PASS" if maximum[0] <= threshold else "FAIL",
            "sample_count": len(values), "maximum": maximum[0], "threshold": threshold,
            "worst_sample": maximum[1], "scope": scope}


def not_run(reason): return {"status": "NOT_RUN", "reason": reason}


def _clip_review(case, clip, thresholds):
    frames, authored = clip["frames"], clip["compiler_clip"]
    if not isinstance(frames, list) or not frames:
        raise ValueError("no evaluated observation frames")
    coord = authored["coordinates"]
    if not (coord.get("units") == "m" and coord.get("up") == "+Y" and coord.get("forward") == "+Z"):
        raise ValueError("critic only accepts declared metres, +Y up, +Z forward")
    rest = case["rest"]
    lengths = {s: [finite(rest["thigh_length_m"][s]), finite(rest["shin_length_m"][s])]
               for s in ("L", "R")}
    if any(min(v) <= 0 for v in lengths.values()):
        raise ValueError("nonpositive rest leg length")
    morphology = authored["instance"]["morphology"]
    ground = finite(case.get("environment", {}).get("ground_y_m", 0.))
    activity = clip["activity_id"]
    ground_applicable = activity not in ("swimming", "bathing") and case.get("environment", {}).get("medium", "ground") == "ground"
    values = {k: [] for k in thresholds}
    skin_penetration, contact_episodes, intermediate_names = [], [], set()
    hand_resolution_deltas = []
    authored_times = [finite(f["time_s"]) for f in authored.get("frames", [])]
    observed_times = [finite(f["time_s"]) for f in frames]
    full_time_coverage = bool(authored_times) and len(authored_times) == len(observed_times) and all(abs(a-b) < 1e-7 for a, b in zip(authored_times, observed_times))
    active, sole_lengths = {}, {}
    previous_time = None
    observed = []
    for index, frame in enumerate(frames):
        time = finite(frame["time_s"])
        if previous_time is not None and time <= previous_time:
            raise ValueError("observation timestamps must strictly increase")
        actual, target = frame["actual"], frame["target"]
        if abs(time-finite(target["time_s"])) > 1e-7:
            raise ValueError("actual and target timestamps differ")
        hip_center = vector(actual["hip_center_m"])
        target_center = vector(target["hip_center_m"])
        ref = {"frame": index, "time_s": time}
        values["pelvis_target_error_m"].append((distance(hip_center, target_center), ref))
        snapshot = {"hip_center_m": hip_center, "feet": {}}
        for side in ("L", "R"):
            foot = actual["feet"][side]
            desired = target["feet"][side]
            points = {key: vector(foot[key]) for key in ("hip_m", "knee_m", "ankle_m", "heel_m", "forefoot_m", "toe_m")}
            snapshot["feet"][side] = points
            sr = dict(ref, side=side)
            for part, a, b, length in (("thigh", "hip_m", "knee_m", lengths[side][0]),
                                      ("shin", "knee_m", "ankle_m", lengths[side][1])):
                values["limb_length_drift_m"].append((abs(distance(points[a], points[b])-length), dict(sr, segment=part)))
            goal = vector(desired["ankle_m"])
            values["ankle_target_error_m"].append((distance(points["ankle_m"], goal), sr))
            # Independent necessary distance bound in the INTENDED pelvis frame.
            offset = sub(vector(morphology["hips_m"][side]), vector(morphology["hip_center_m"]))
            intended_hip = [a+b for a, b in zip(target_center, offset)]
            reach = distance(intended_hip, goal)
            lower, upper = abs(lengths[side][0]-lengths[side][1]), sum(lengths[side])
            values["reach_excess_m"].append((max(0., lower-reach, reach-upper), sr))
            sole_length = distance(points["heel_m"], points["forefoot_m"])
            sole_lengths.setdefault(side, sole_length)
            values["rigid_sole_length_drift_m"].append((abs(sole_length-sole_lengths[side]), sr))
            if ground_applicable:
                for marker in ("heel", "forefoot", "toe"):
                    values["ground_penetration_m"].append((max(0., ground-points[marker+"_m"][1]), dict(sr, marker=marker)))
                if "skin_sole_min_y_m" in foot:
                    skin_penetration.append((max(0., ground-finite(foot["skin_sole_min_y_m"])), sr))
            for marker in ("heel", "forefoot"):
                contact = desired["contacts"][marker]
                if not isinstance(contact, bool):
                    raise ValueError("contact flags must be boolean")
                key = (side, marker)
                point = points[marker+"_m"]
                if contact and ground_applicable:
                    if not str(desired.get("contact_reference", "")).startswith("world:ground"):
                        raise ValueError("ground contact lacks declared world-ground reference")
                    values["active_contact_height_error_m"].append((abs(point[1]-ground), dict(sr, marker=marker)))
                    if key not in active:
                        active[key] = {"first": point, "previous": point, "time": time, "start_time_s": time, "samples": 1}
                    else:
                        episode = active[key]
                        values["planted_drift_m"].append((distance(point, episode["first"]), dict(sr, marker=marker, episode_start_s=episode["start_time_s"])))
                        values["planted_speed_m_s"].append((distance(point, episode["previous"])/(time-episode["time"]), dict(sr, marker=marker)))
                        episode.update(previous=point, time=time, samples=episode["samples"]+1)
                elif key in active:
                    episode = active.pop(key)
                    contact_episodes.append(dict(side=side, marker=marker, start_time_s=episode["start_time_s"], end_time_s=episode["time"], samples=episode["samples"]))
        for side, target_hand in target.get("hands_m", {}).items():
            if side in actual.get("hands_m", {}):
                resolved_hand = frame.get("resolved_task", {}).get("resolved_hands_m", {}).get(side, target_hand)
                hand_resolution_deltas.append((distance(vector(resolved_hand), vector(target_hand)), dict(ref, side=side)))
                values["hand_target_error_m"].append((distance(vector(actual["hands_m"][side]), vector(resolved_hand)), dict(ref, side=side)))
        for name, baseline in rest.get("intermediate_bones", {}).items():
            entry = actual.get("intermediate_bones", {}).get(name)
            if entry is not None:
                intermediate_names.add(name)
                values["intermediate_rotation_drift_rad"].append((quaternion_distance(entry["relative_rotation_xyzw"], baseline["relative_rotation_xyzw"]), dict(ref, bone=name)))
        observed.append(snapshot)
        previous_time = time
    for (side, marker), episode in active.items():
        contact_episodes.append(dict(side=side, marker=marker, start_time_s=episode["start_time_s"], end_time_s=episode["time"], samples=episode["samples"]))

    # Only compare genuinely matching cycle phases; moving loops are not forced
    # to return to world origin. This v1 critic supports translation-only loops.
    loop_reason = "clip is not a complete declared translation-only loop"
    loop = authored.get("loop", {})
    if loop.get("enabled") and len(frames) > 1:
        period = finite(loop["period_s"])
        if period <= 0: raise ValueError("nonpositive loop period")
        cycles = (frames[-1]["time_s"]-frames[0]["time_s"])/period
        delta = vector(loop.get("cycle_delta_m", loop.get("root_cycle_delta_m", [0., 0., 0.])))
        if cycles >= .999 and abs(cycles-round(cycles)) < 1e-6:
            delta = [x*round(cycles) for x in delta]
            values["loop_position_seam_m"].append((distance(sub(observed[-1]["hip_center_m"], delta), observed[0]["hip_center_m"]), {"marker": "hip_center"}))
            for side in ("L", "R"):
                for marker in observed[0]["feet"][side]:
                    values["loop_position_seam_m"].append((distance(sub(observed[-1]["feet"][side][marker], delta), observed[0]["feet"][side][marker]), {"side": side, "marker": marker}))

    descriptions = {
        "limb_length_drift_m": "Observed anatomical hip-knee and knee-ankle distances versus measured post-morphology bind; this alone does not exclude intermediate bends.",
        "ankle_target_error_m": "Evaluated ankle versus authored ankle target; solver tracking only.",
        "pelvis_target_error_m": "Evaluated pelvis center versus authored center; prevents hiding unreachable targets through pelvis drift.",
        "reach_excess_m": "Necessary two-link distance bound in intended pelvis frame; not joint-range or collision acceptance.",
        "planted_drift_m": "Observed world marker displacement from first observed point of each contiguous authored contact episode; no height-derived contact inference.",
        "planted_speed_m_s": "Observed world marker finite-difference speed while the same authored contact remains active.",
        "ground_penetration_m": "Evaluated heel, forefoot and toe markers only; not whole-shoe or body collision.",
        "active_contact_height_error_m": "Evaluated active support marker height against declared ground plane.",
        "rigid_sole_length_drift_m": "Heel-forefoot marker distance relative to first observed frame, under rigid shoe-segment assumption; toe flex excluded.",
        "intermediate_rotation_drift_rad": "Sign-invariant parent-relative rotation drift of explicitly observed intermediate bones versus bind; missing bones are unqualified.",
        "hand_target_error_m": "Evaluated reported hand/wrist point versus explicitly resolved consumer task target when present, otherwise authored target; target-resolution displacement is reported separately. Grip, prop-tip and mouth contact remain unqualified.",
        "loop_position_seam_m": "First versus last observed positions after declared whole-cycle root translation compensation; excludes arbitrary crossfades.",
    }
    gates = {name: gate(samples, thresholds[name], missing=loop_reason if name == "loop_position_seam_m" else "no applicable independent observations", scope=descriptions[name])
             for name, samples in values.items()}
    gates["authored_time_coverage"] = {"status": "PASS" if full_time_coverage else "NOT_RUN", "observed_frames": len(frames), "authored_frames": len(authored_times),
                                       "scope": "Every authored timestamp must have an independent observation for continuous contact-episode qualification; sparse pose metrics remain sampled only."}
    if not full_time_coverage:
        for name in ("planted_drift_m", "planted_speed_m_s"):
            gates[name] = not_run("Sparse or mismatched time coverage can omit contact breaks; observed true flags cannot be joined across unobserved phases")
        contact_episodes = []
    if hand_resolution_deltas:
        maximum = max(hand_resolution_deltas, key=lambda x: x[0])
        gates["hand_target_resolution_delta_m"] = {"status": "MEASURED", "maximum": maximum[0], "worst_sample": maximum[1],
                                                    "scope": "Declared consumer adaptation of authored wrist target to posed proxy; not contact acceptance."}
    else:
        gates["hand_target_resolution_delta_m"] = not_run("No authored hand targets with evaluated observations")
    if not ground_applicable:
        for name in ("ground_penetration_m", "active_contact_height_error_m", "planted_drift_m", "planted_speed_m_s"):
            gates[name] = {"status": "NOT_APPLICABLE", "reason": "non-ground medium; aquatic contact requires a separate critic"}
    gates["skin_sole_ground_penetration_m"] = gate(skin_penetration, thresholds["ground_penetration_m"], missing="evaluated skin sole minima absent", scope="Consumer-declared evaluated skin sole subset only; no complete skin or footwear collision proof.")
    expected_intermediates = set(rest.get("intermediate_bones", {}))
    required_names = set(case.get("required_intermediate_bones", EXPECTED_MAKEHUMAN_INTERMEDIATES))
    required_count = len(expected_intermediates)*len(frames)
    if not expected_intermediates or not required_names <= expected_intermediates or len(values["intermediate_rotation_drift_rad"]) != required_count:
        gates["intermediate_rotation_coverage"] = not_run("Every expected intermediate bone must be observed at every frame; no inference from constant length")
        gates["intermediate_rotation_coverage"]["missing_bind_bones"] = sorted(required_names-expected_intermediates)
    else:
        gates["intermediate_rotation_coverage"] = {"status": "PASS", "bones": sorted(intermediate_names), "samples": required_count}
    bind = case.get("bind_sha")
    requested_bind = authored["instance"].get("source_bind_sha256")
    if bind == requested_bind == "UNVERIFIED_SYNTHETIC":
        gates["bind_identity"] = not_run("Explicit synthetic analytic fixture; no real source identity qualification")
    elif isinstance(bind, str) and len(bind) == 64 and all(x in "0123456789abcdef" for x in bind) and bind == requested_bind:
        gates["bind_identity"] = {"status": "PASS", "source_bind_sha256": bind, "scope": "Matching supplied bind identifiers; custody remains a separate receipt check."}
    else:
        gates["bind_identity"] = {"status": "FAIL", "reason": "Missing or mismatched morphology/bind identifiers"}
    for name, reason in {
        "self_intersection": "No independently evaluated body/prop triangle collision observations.",
        "physiological_joint_limits": "No calibrated anatomical joint frames and supported per-joint limits.",
        "balance_and_dynamics": "No mass, center of mass, forces, friction or dynamic support model.",
        "prop_and_seat_contacts": "Hand/seat target residual is not independently measured skin/prop or body/seat contact.",
        "arbitrary_contact_transition": "Only explicitly authored transitions or masked targets are implemented; no generic transition qualification.",
        "breathing_soft_tissue_organs": "Skeletal replay contains no validated respiration, tissue mechanics or organ model.",
        "motion_realism": "Original authored intent plus transport/kinematics cannot establish captured or realistic human motion.",
    }.items(): gates[name] = not_run(reason)
    failed = sorted(name for name, value in gates.items() if value["status"] == "FAIL")
    return {"activity_id": activity, "frame_count": len(frames), "gates": gates,
            "failed_gates": failed, "status": "FAIL_BOUNDED_KINEMATIC_GATES" if failed else "BOUNDED_OBSERVATIONS_REPORTED",
            "contact_episodes": contact_episodes, "realism": "NOT_QUALIFIED"}


def review(observations, thresholds=None):
    if observations.get("schema") != SCHEMA or not isinstance(observations.get("cases"), list) or not observations["cases"]:
        raise ValueError("expected nonempty "+SCHEMA)
    selected = dict(THRESHOLDS)
    if thresholds is not None:
        if set(thresholds)-set(selected): raise ValueError("unknown threshold override")
        selected.update(thresholds)
    for value in selected.values():
        if finite(value) < 0: raise ValueError("negative threshold")
    result = {"schema": "oneirifact.motion-independent-critic/v1", "thresholds": selected,
              "threshold_scope": "Preregistered provisional engineering criteria, not measured human variation, clinical limits or realism acceptance.",
              "observations_sha256": hashlib.sha256(json.dumps(observations, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
              "cases": [], "realism": "NOT_QUALIFIED"}
    for case in observations["cases"]:
        item = {"id": case.get("id"), "clips": []}
        if not case.get("clips"):
            item["clips"].append({"status": "INVALID_OBSERVATIONS", "error": "case has no clips"})
        for clip in case.get("clips", []):
            try:
                item["clips"].append(_clip_review(case, clip, selected))
            except (KeyError, ValueError, TypeError, ZeroDivisionError) as error:
                item["clips"].append({"activity_id": clip.get("activity_id"), "status": "INVALID_OBSERVATIONS", "error": str(error), "realism": "NOT_QUALIFIED"})
        result["cases"].append(item)
    result["failed_or_invalid_clip_count"] = sum(c["status"] in ("FAIL_BOUNDED_KINEMATIC_GATES", "INVALID_OBSERVATIONS") for case in result["cases"] for c in case["clips"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = review(json.loads(args.observations.read_text()))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"output": str(args.output), "failed_or_invalid_clip_count": result["failed_or_invalid_clip_count"], "realism": result["realism"]}))
