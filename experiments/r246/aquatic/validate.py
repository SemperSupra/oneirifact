"""Bounded source-measured intent contract and falsifiers; no native FK claim."""
import copy
import hashlib
import json
import math
import os
import sys
from pathlib import Path
import compiler as c

EPSILON_S = 1e-5
LIMITS = {"position_jump_m": 1e-4, "orientation_jump_rad": 3e-4, "velocity_jump_m_s": .02,
          "loop_position_m": 1e-8, "rotated_anchor_m": 1e-9}


def qmatrix(q, v):
    # Independent explicit matrix form; never calls the compiler quaternion helper.
    x, y, z, w = q
    return [(1-2*y*y-2*z*z)*v[0]+(2*x*y-2*z*w)*v[1]+(2*x*z+2*y*w)*v[2],
            (2*x*y+2*z*w)*v[0]+(1-2*x*x-2*z*z)*v[1]+(2*y*z-2*x*w)*v[2],
            (2*x*z-2*y*w)*v[0]+(2*y*z+2*x*w)*v[1]+(1-2*x*x-2*y*y)*v[2]]


def points(frame):
    out = {"hip": frame["hip_center_m"]}
    for s in ("L", "R"):
        for k in ("ankle_m", "heel_m", "forefoot_m", "toe_m", "knee_pole_m"): out[s+"."+k] = frame["feet"][s][k]
        out[s+".hand"] = frame["hands_m"][s]
        out[s+".arm_pole"] = frame["arm_poles"][s]["position_m"]
        out[s+".hip"] = frame["body_anchors"]["hips_m"][s]
        out[s+".shoulder"] = frame["body_anchors"]["shoulders_m"][s]
    for k in ("head_m", "mouth_m", "chest_surface_anchor_m"): out[k] = frame["body_anchors"][k]
    for prop in frame["props"]:
        if "position_m" in prop: out["prop."+prop["id"]] = prop["position_m"]
    return out


def rotations(frame):
    return {"root": frame["root_orientation_xyzw"], "head": frame["joint_intents"]["head_orientation_xyzw"],
            **{s: frame["feet"][s]["rotation_xyzw"] for s in ("L", "R")},
            **{"prop."+p["id"]: p["orientation_xyzw"] for p in frame["props"] if "orientation_xyzw" in p}}


def qdistance(a, b):
    value = abs(sum(x*y for x, y in zip(a, b))) / math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return 2*math.acos(max(-1., min(1., value)))


def anchor_audit(frame, morphology, measurements):
    maximum = 0.
    for s in ("L", "R"):
        for key, rest in (("hips_m", morphology["hips_m"][s]), ("shoulders_m", measurements["arms"][s]["shoulder_m"])):
            offset = [x-y for x, y in zip(rest, morphology["hip_center_m"])]
            expected = [x+y for x, y in zip(frame["hip_center_m"], qmatrix(frame["root_orientation_xyzw"], offset))]
            actual = frame["body_anchors"][key][s]
            maximum = max(maximum, math.dist(actual, expected))
    return {"status": "PASS" if maximum <= LIMITS["rotated_anchor_m"] else "FAIL", "maximum_error_m": maximum}


def boundary(sample, t):
    f0, f1, f2, f3 = [sample(t+k*EPSILON_S) for k in (-2, -1, 1, 2)]
    p0, p1, p2, p3 = map(points, (f0, f1, f2, f3))
    position = max(math.dist(p1[k], p2[k]) for k in p1)
    velocity = max(math.dist([(a-b)/EPSILON_S for a, b in zip(p1[k], p0[k])],
                             [(a-b)/EPSILON_S for a, b in zip(p3[k], p2[k])]) for k in p1)
    r1, r2 = rotations(f1), rotations(f2)
    orientation = max(qdistance(r1[k], r2[k]) for k in r1)
    return {"time_s": t, "position_jump_m": position, "orientation_jump_rad": orientation,
            "velocity_jump_m_s": velocity, "status": "PASS" if position < LIMITS["position_jump_m"] and
            orientation < LIMITS["orientation_jump_rad"] and velocity < LIMITS["velocity_jump_m_s"] else "FAIL"}


def loop_audit(a, b, delta):
    pa, pb = points(a), points(b)
    error = max(math.dist([x+y for x, y in zip(pa[k], delta)], pb[k]) for k in pa)
    ra, rb = rotations(a), rotations(b)
    rotation = max(qdistance(ra[k], rb[k]) for k in ra)
    props_a = [p for p in a["props"] if p.get("reference") == "world"]
    props_b = [p for p in b["props"] if p.get("reference") == "world"]
    same_contacts = all(a["feet"][s]["contacts"] == b["feet"][s]["contacts"] and
                        a["feet"][s]["contact_reference"] == b["feet"][s]["contact_reference"] for s in ("L", "R"))
    toe_error = max(abs(a["feet"][s]["toe_flexion_rad"]-b["feet"][s]["toe_flexion_rad"]) for s in ("L", "R"))
    return {"status": "PASS" if error < LIMITS["loop_position_m"] and rotation < 1e-7 and toe_error < 1e-9 and props_a == props_b and same_contacts else "FAIL",
            "maximum_position_error_m": error, "maximum_orientation_error_rad": rotation,
            "maximum_toe_flexion_error_rad": toe_error, "static_world_props_equal": props_a == props_b, "contacts_equal": same_contacts}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def negative_contracts(inputs, folder):
    m, f, lm = (inputs[k] for k in ("morphology", "footwear", "limb_measurements"))
    a = "swimming_front_crawl"
    context = c.context_from_template(a, m)
    base = dict(activity_id=a, morphology=m, footwear=f, context=context, limb_measurements=lm, duration_s=.1)
    rows = []
    def reject(name, changes):
        kw = copy.deepcopy(base)
        changes(kw)
        try: c.compile_clip(**kw)
        except (ValueError, KeyError) as exc: rows.append({"case": name, "status": "PASS_EXPECTED_REJECTION", "reason": str(exc)})
        else: rows.append({"case": name, "status": "FAIL_ACCEPTED_INVALID_INPUT"})
    reject("bool fps", lambda k: k.update(fps=True))
    reject("string seed", lambda k: k.update(seed="24601"))
    reject("string context coordinate", lambda k: k["context"].update(surface_y_m="0"))
    reject("unknown physical context parameter", lambda k: k["context"].update(drag_coefficient=1.0))
    reject("nonmatching source arm bind", lambda k: k["limb_measurements"].update(source_bind_sha256="0"*64))
    reject("false arm length", lambda k: k["limb_measurements"]["arms"]["L"].update(upper_m=.01))
    reject("aquatic stilettos unsupported", lambda k: k.update(footwear=c.core.footwear_from_profile("stilettos", m)))
    reject("unsupported tub entry label", lambda k: k.update(activity_id="bathing_tub_entry"))
    # A deep hip with wrist targets at the surface is deliberately unreachable.
    bad = copy.deepcopy(context)
    bad["root_depth_m"] = .75*m["stature_m"]
    bad["depth_m"] = 2*m["stature_m"]
    clip = c.compile_clip(a, m, f, bad, limb_measurements=lm, duration_s=.1)
    write(folder/"negative-unreachable-surface-wrists.json", clip)
    rows.append({"case": "unreachable surface wrists", "status": "PASS_EXPECTED_DIAGNOSTIC_FAILURE" if clip["qualification"]["reach_distance_screen"] == "FAIL" else "FAIL_FALSE_REACH_PASS",
                 "recorded_failures": len(clip["qualification"]["reach_failures"]), "targets_emitted_without_stretch": True})
    bad = c.context_from_template("bathing_seated_wash", m)
    bad["interior_width_m"] = 10*m["stature_m"]
    clip = c.compile_clip("bathing_seated_wash", m, f, bad, limb_measurements=lm, duration_s=.1)
    write(folder/"negative-unreachable-tub-rim.json", clip)
    rows.append({"case": "unreachable tub rim", "status": "PASS_EXPECTED_DIAGNOSTIC_FAILURE" if clip["qualification"]["reach_distance_screen"] == "FAIL" else "FAIL_FALSE_REACH_PASS",
                 "recorded_failures": len(clip["qualification"]["reach_failures"]), "targets_emitted_without_stretch": True})
    bad = copy.deepcopy(context)
    bad["depth_m"] = bad["root_depth_m"]*1.01
    clip = c.compile_clip(a, m, f, bad, limb_measurements=lm, duration_s=.1)
    write(folder/"negative-shallow-water-context.json", clip)
    rows.append({"case": "water bottom crosses foot markers", "status": "PASS_EXPECTED_DIAGNOSTIC_FAILURE" if clip["qualification"]["context_geometry_screen"] == "FAIL" else "FAIL_FALSE_CONTEXT_PASS"})
    return rows


def validate_case(folder):
    inputs = json.loads((folder/"aquatic-inputs.json").read_text())
    m, f, lm = (inputs[k] for k in ("morphology", "footwear", "limb_measurements"))
    rows = []
    for activity, definition in c.library()["activities"].items():
        context = c.context_from_template(activity, m)
        period = definition["period_s"]
        def compile_at(**kw):
            return c.compile_clip(activity, m, f, context, limb_measurements=lm, **kw)
        def sample(t): return compile_at(start_time_s=t, duration_s=1e-6, fps=1)["frames"][0]
        clip = compile_at()
        repeated = compile_at()
        instance = clip["instance"]
        replayed = c.compile_clip(activity, instance["morphology"], instance["footwear"], instance["context"],
                                  limb_measurements=instance["limb_measurements"], seed=instance["seed"], fps=instance["fps"],
                                  duration_s=instance["duration_s"], start_time_s=instance["start_time_s"])
        loop = loop_audit(sample(period*.31), sample(period*1.31), clip["loop"]["cycle_delta_m"])
        boundaries = [boundary(sample, period*(1+phase)) for phase in (0., .05, .25, .45, .5, .75)]
        anchors = [anchor_audit(fr, m, lm) for fr in clip["frames"]]
        seek = max(math.dist(points(fr)[k], points(sample(fr["source_time_s"]))[k]) for fr in clip["frames"][::17] for k in points(fr))
        if activity.startswith("swimming"):
            contacts = all(not any(fr["feet"][s]["contacts"].values()) and fr["feet"][s]["contact_reference"] == "none" and not fr["feet"][s]["support_regions"] for fr in clip["frames"] for s in ("L", "R"))
            references = all(fr["hand_targets"][s]["reference"] == "world" and fr["arm_poles"][s]["reference"] == "world" for fr in clip["frames"] for s in ("L", "R"))
            prone = max(abs(qmatrix(fr["root_orientation_xyzw"], [0., 1., 0.])[1]) for fr in clip["frames"]) < 1e-9
            breathing = max(abs(fr["joint_intents"]["head_axial_rotation_rad"]) for fr in clip["frames"]) > .8
            phase = all(fr["hand_targets"]["L"]["phase"]["mode"] != fr["hand_targets"]["R"]["phase"]["mode"] for fr in clip["frames"])
            feature = contacts and references and prone and breathing and phase
            feature_result = {"no_ground_contacts": contacts, "world_target_references": references, "horizontal_body_axis": prone, "head_turn_present": breathing, "alternating_pull_recovery": phase}
        else:
            contacts = all(fr["feet"][s]["contact_reference"] == "world:tub:floor" and all(fr["feet"][s]["contacts"].values()) for fr in clip["frames"] for s in ("L", "R"))
            props = all({x["target"] for x in fr["prop_contacts"]} == {"world:tub:seat", "world:tub:rim", "sponge"} for fr in clip["frames"])
            references = all({x["reference"] for x in fr["hand_targets"].values()} == {"world:tub:rim", "body:chest_surface_anchor"} for fr in clip["frames"])
            feature = contacts and props and references
            feature_result = {"tub_floor_references": contacts, "seat_rim_sponge_intent": props, "distinct_hand_reference_frames": references}
        row = {"activity": activity, "source_bind_sha256": m["source_bind_sha256"], "frame_count": len(clip["frames"]),
               "clip_sha256": clip["clip_sha256"], "deterministic": clip["clip_sha256"] == repeated["clip_sha256"],
               "resolved_instance_replay": clip["clip_sha256"] == replayed["clip_sha256"],
               "seek_maximum_position_error_m": seek, "loop": loop, "one_sided_boundaries": boundaries,
               "rotated_anchor_maximum_error_m": max(x["maximum_error_m"] for x in anchors), "features": feature_result,
               "minimum_reach_margin_m": min(r["margin_m"] for fr in clip["frames"] for r in fr["reach_screen"]),
               "reach_distance_screen": clip["qualification"]["reach_distance_screen"], "context_geometry_screen": clip["qualification"]["context_geometry_screen"]}
        row["status"] = "PASS_BOUNDED_INTENT" if row["deterministic"] and row["resolved_instance_replay"] and seek < 1e-9 and loop["status"] == "PASS" and all(x["status"] == "PASS" for x in boundaries+anchors) and feature and row["reach_distance_screen"] == "PASS" and row["context_geometry_screen"] == "PASS" else "FAIL_BOUNDED_INTENT"
        write(folder/(activity+"-clip.json"), clip)
        write(folder/(activity+"-definition.json"), {"definition": clip["definition"], "sha256": clip["definition_sha256"]})
        write(folder/(activity+"-instance.json"), {"instance": clip["instance"], "sha256": clip["instance_sha256"]})
        write(folder/(activity+"-context.json"), context)
        rows.append(row)
    negatives = negative_contracts(inputs, folder)
    # Independent oracle: the identity-root shortcut must be detected for this
    # prone, rolling source. Both hip and shoulder targets are corrupted.
    activity = "swimming_front_crawl"
    context = c.context_from_template(activity, m)
    sample = lambda t: c.compile_clip(activity, m, f, context, limb_measurements=lm, duration_s=1e-6, start_time_s=t, fps=1)["frames"][0]
    good = sample(.6)
    bad = copy.deepcopy(good)
    for s in ("L", "R"):
        for key, rest in (("hips_m", m["hips_m"][s]), ("shoulders_m", lm["arms"][s]["shoulder_m"])):
            bad["body_anchors"][key][s] = [x+y-z for x, y, z in zip(bad["hip_center_m"], rest, m["hip_center_m"])]
    a = anchor_audit(good, m, lm)
    b = anchor_audit(bad, m, lm)
    constant = boundary(lambda t: good, 1.)
    def step(t):
        result = copy.deepcopy(good)
        if t >= 1.: result["hands_m"]["L"][0] += .01
        return result
    step_result = boundary(step, 1.)
    oracles = [{"case": "actual rotated source anchors", "status": "PASS" if a["status"] == "PASS" else "FAIL", "observed": a},
               {"case": "deliberately unrotated source hip and shoulder offsets", "status": "PASS_EXPECTED_FAILURE" if b["status"] == "FAIL" else "FAIL", "observed": b},
               {"case": "constant target continuity", "status": "PASS" if constant["status"] == "PASS" else "FAIL", "observed": constant},
               {"case": "known 10 mm target step", "status": "PASS_EXPECTED_FAILURE" if step_result["status"] == "FAIL" else "FAIL", "observed": step_result}]
    result = {"case": m["id"], "activities": rows, "negative_contracts": negatives, "critic_oracles": oracles,
              "status": "PASS" if all(r["status"].startswith("PASS") for r in rows+negatives+oracles) else "FAIL"}
    write(folder/"aquatic-contract-receipt.json", result)
    return result


def main(root):
    cases = [validate_case(p.parent) for p in sorted(root.glob("*/aquatic-inputs.json"))]
    assert cases, "no actual source-bound inputs"
    from render import render_case
    for p in sorted(root.glob("*/aquatic-inputs.json")): render_case(p.parent)
    files = [{"path": str(p.relative_to(root)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
             for p in sorted(root.rglob("*")) if p.is_file() and p.name != "receipt.json"]
    result = {"schema": "oneirifact.r246-aquatic-intent-receipt/v1", "head_sha": os.getenv("SOURCE_HEAD_SHA", "LOCAL_PREFLIGHT"),
              "github_run_id": os.getenv("GITHUB_RUN_ID"), "execution": "PUBLIC_GHA" if os.getenv("GITHUB_ACTIONS") == "true" else "LOCAL_PREFLIGHT_ONLY",
              "compiler_sha256": hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(), "source_preparation_head": "7fc8141fef8e2133ecceb2474005e82da4da69ad",
              "status": "PASS_BOUNDED_AQUATIC_INTENT" if all(x["status"] == "PASS" for x in cases) else "FAIL_BOUNDED_AQUATIC_INTENT",
              "thresholds_declared_in_source": {"epsilon_s": EPSILON_S, **LIMITS}, "cases": cases, "files": files,
              "native_consumer": "NOT_RUN", "realism": "NOT_QUALIFIED", "physics": "NOT_QUALIFIED", "observed_contacts": "NOT_QUALIFIED",
              "scope": "Two original authored kinematic prototypes, barefoot only. Nine source-case labels represent five unique body binds; previous shoe-profile qualifications are not transferred. Tub entry/exit is unsupported."}
    write(root/"receipt.json", result)
    print(json.dumps({k: result[k] for k in ("status", "execution", "head_sha", "native_consumer")}))
    return result


if __name__ == "__main__":
    result = main(Path(sys.argv[1]))
    sys.exit(0 if result["status"].startswith("PASS") else 1)
