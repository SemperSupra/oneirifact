#!/usr/bin/env python3
"""Independent controlled-corruption probes against a captured observation fixture.

Each control requires its original gate to pass; an already-failing baseline is
NOT_RUN, never called a successful negative oracle. No compiler or solver import.
"""
import copy
import hashlib
import json
import math
import sys
from pathlib import Path
import native_critic as critic


def find_clip(data, activity):
    return next(x for x in data["cases"][0]["clips"] if x["activity_id"] == activity)


def result_clip(report, activity):
    return next(x for x in report["cases"][0]["clips"] if x["activity_id"] == activity)


def rehash(clip):
    a = clip["compiler_clip"]
    a["definition_sha256"] = critic.digest(a["definition"])
    a["instance_sha256"] = critic.digest(a["instance"])
    value = dict(a); value.pop("clip_sha256", None)
    a["clip_sha256"] = critic.digest(value)


def run(observations):
    baseline = critic.review(observations)
    probes = []
    swim, bath = "swimming_front_crawl", "bathing_seated_wash"
    def probe(name, activity, gate, change, expected="FAIL"):
        before = result_clip(baseline, activity).get("gates", {}).get(gate, {}).get("status")
        if before != "PASS":
            probes.append({"name": name, "status": "NOT_RUN", "reason": "baseline gate was not PASS", "gate": gate, "baseline_gate": before})
            return
        corrupted = copy.deepcopy(observations)
        clip = find_clip(corrupted, activity)
        change(corrupted["cases"][0], clip)
        reviewed = result_clip(critic.review(corrupted), activity)
        observed = reviewed.get("gates", {}).get(gate, {}).get("status")
        if expected == "INVALID_OBSERVATIONS": observed = reviewed["status"]
        probes.append({"name": name, "gate": gate, "baseline_gate": before, "expected": expected, "observed": observed,
                       "status": "PASS_CONTROL" if observed == expected else "FAIL_CONTROL", "scope": "controlled observation corruption, not physiological validation"})
    def unrotated(case, clip):
        row = clip["frames"][len(clip["frames"])//8]
        inst = clip["compiler_clip"]["instance"]; m = inst["morphology"]
        for s in ("L", "R"):
            row["actual"]["feet"][s]["hip_m"] = [x+y-z for x, y, z in zip(row["target"]["hip_center_m"], m["hips_m"][s], m["hip_center_m"])]
            row["actual"]["arms"][s]["shoulder_m"] = [x+y-z for x, y, z in zip(row["target"]["hip_center_m"], inst["limb_measurements"]["arms"][s]["shoulder_m"], m["hip_center_m"])]
    probe("unrotated source hip offsets under prone roll", swim, "rotated_hip_error_m", unrotated)
    probe("unrotated source shoulder offsets under prone roll", swim, "rotated_shoulder_error_m", unrotated)
    def stretch(case, clip):
        foot = clip["frames"][3]["actual"]["feet"]["L"]
        v = critic.sub(foot["ankle_m"], foot["knee_m"]); length = critic.norm(v)
        foot["ankle_m"] = [a+.02*b/length for a, b in zip(foot["ankle_m"], v)]
    probe("20 mm shank stretch", swim, "limb_length_drift_m", stretch)
    def mouth_shift(case, clip):
        row = clip["frames"][3]
        for p in (row["actual"]["hands_m"]["L"], row["actual"]["arms"]["L"]["wrist_m"], row["resolved_task"]["resolved_hands_m"]["L"]): p[0] += .04
    probe("world wrist silently shifted 40 mm despite resolved target", swim, "hand_target_error_m", mouth_shift)
    probe("mouth adapter displacement itself exposed", swim, "hand_resolution_delta_m", mouth_shift)
    def bend(case, clip):
        clip["frames"][3]["actual"]["intermediate_bones"]["lowerleg02.L"]["relative_rotation_xyzw"] = [math.sin(.05/2), 0., 0., math.cos(.05/2)]
    probe("intermediate bone bend without source segment rewrite", swim, "intermediate_rotation_drift_rad", bend)
    def delta(case, clip):
        clip["compiler_clip"]["loop"]["cycle_delta_m"][2] += .05
        clip["compiler_clip"]["instance"]["root_cycle_delta_m"][2] += .05
        rehash(clip)
    probe("wrong 50 mm declared cycle displacement", swim, "root_cycle_delta_error_m", delta)
    def false_ground(case, clip):
        index = 3
        clip["frames"][index]["target"]["feet"]["L"]["contacts"]["heel"] = True
        clip["compiler_clip"]["frames"][index]["feet"]["L"]["contacts"]["heel"] = True
        rehash(clip)
    probe("false swimming ground support", swim, "reference_and_contact_semantics", false_ground)
    def wrong_chest(case, clip): clip["frames"][3]["actual"]["chest_source_vertex_id"] += 1
    probe("wrong chest source vertex identity", bath, "chest_vertex_identity", wrong_chest)
    def floor(case, clip): clip["frames"][3]["actual"]["feet"]["L"]["skin_sole_min_y_m"] -= .02
    probe("20 mm skin-sole penetration into declared tub floor", bath, "tub_floor_skin_subset_penetration_m", floor)
    def rim(case, clip):
        row = clip["frames"][3]
        side = next(s for s, target in row["target"]["hand_targets"].items() if target["reference"] == "world:tub:rim")
        row["actual"]["hands_m"][side][0] += .03
    probe("30 mm rim-hand drift", bath, "tub_rim_hand_drift_m", rim)
    def moved_floor(case, clip):
        tub = clip["frames"][3]["actual"]["context_geometry"]["tub"]
        tub["floor_top_center_m"][1] += .02
        for p in tub["floor_top_corners_m"]: p[1] += .02
    probe("evaluated floor moved 20 mm from declared plane", bath, "context_mesh_agreement_m", moved_floor)
    probe("actual feet separated from moved evaluated floor", bath, "evaluated_tub_floor_marker_error_m", moved_floor)
    def moved_rim(case, clip):
        row = clip["frames"][3]
        side = next(s for s, target in row["target"]["hand_targets"].items() if target["reference"] == "world:tub:rim")
        tub = row["actual"]["context_geometry"]["tub"]
        tub["rim_top_centers_m"][side][1] += .02
        for p in tub["rim_top_corners_m"][side]: p[1] += .02
    probe("actual wrist separated from moved evaluated rim", bath, "evaluated_tub_rim_wrist_error_m", moved_rim)
    def drifting_water(case, clip):
        water = clip["frames"][3]["actual"]["context_geometry"]["water"]
        for key in ("surface_corners_m", "bottom_corners_m"):
            for p in water[key]: p[0] += .05
    probe("static world water context moves 50 mm", swim, "context_static_drift_m", drifting_water)
    def omission(case, clip): clip["frames"][3]["actual"]["context_geometry"] = {"status": "NATIVE_CONTEXT_NOT_EXPORTED_TO_BODY_GLB"}
    probe("native frame cannot claim body-GLB context omission", bath, "evaluated_context_coverage", omission)
    def missing(case, clip): clip["frames"].pop(3)
    probe("missing authored observation cannot pass dense coverage", swim, "authored_time_coverage", missing, "NOT_RUN")
    def boolean(case, clip): clip["frames"][0]["actual"]["hands_m"]["L"][0] = True
    probe("boolean coordinate rejected", swim, "hand_target_error_m", boolean, "INVALID_OBSERVATIONS")
    failed = sum(p["status"] == "FAIL_CONTROL" for p in probes)
    held = sum(p["status"] == "NOT_RUN" for p in probes)
    return {"schema": "oneirifact.aquatic-native-critic-controls/v1", "fixture_sha256": critic.digest(observations),
            "baseline_failed_or_invalid_clips": baseline["failed_or_invalid_clip_count"], "baseline_incomplete_clips": baseline["incomplete_clip_count"],
            "probes": probes, "failed_controls": failed, "not_run_controls": held,
            "status": "FAIL_CONTROLS" if failed else "INCOMPLETE_CONTROLS" if held else "PASS_CONTROLLED_CORRUPTION_PROBES"}


if __name__ == "__main__":
    observations = json.loads(Path(sys.argv[1]).read_text())
    report = run(observations)
    Path(sys.argv[2]).write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k: report[k] for k in ("status", "failed_controls", "not_run_controls")}))
    sys.exit(1 if report["failed_controls"] else 0)
