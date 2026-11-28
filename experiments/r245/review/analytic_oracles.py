#!/usr/bin/env python3
"""Analytic geometry controls for critic sensitivity; no Blender or compiler."""
import copy
import json
import math
from critic import review
from compiler_audit import audit


class AnalyticIntentField:
    """Constant points, with optional analytic step or changing segment length."""
    def __init__(self, defect=None): self.defect = defect
    def library(self):
        return {"activities": {"walking": {"kind": "gait", "implementation": "ANALYTIC_FIXTURE", "period_s": 1., "stance_fraction": .6}}}
    def compile_clip(self, activity, morphology, footwear, *, fps, duration_s=1., start_time_s=0.):
        times = [start_time_s+i*duration_s/10 for i in range(11)]
        frames = []
        for time in times:
            step = .01 if self.defect == "step" and time >= 2.6 else 0.
            stretch = .01*math.sin(2*math.pi*time) if self.defect == "stretch" else 0.
            foot = {"ankle_m": [step, .1, 0.], "heel_m": [step, 0., 0.], "forefoot_m": [step, 0., .2+stretch],
                    "toe_m": [step, 0., .3], "rotation_xyzw": [0., 0., 0., 1.]}
            frames.append({"feet": {"L": copy.deepcopy(foot), "R": copy.deepcopy(foot)}})
        return {"frames": frames}


def fixture():
    rest = {"thigh_length_m": {"L": .4, "R": .4}, "shin_length_m": {"L": .4, "R": .4},
            "intermediate_bones": {name: {"relative_rotation_xyzw": [0, 0, 0, 1]}
                                   for name in ("upperleg02.L", "upperleg02.R", "lowerleg02.L", "lowerleg02.R")}}
    morphology = {"source_bind_sha256": "UNVERIFIED_SYNTHETIC", "hip_center_m": [0, 1, 0],
                  "hips_m": {"L": [.1, 1, 0], "R": [-.1, 1, 0]}}
    clip = {"coordinates": {"units": "m", "up": "+Y", "forward": "+Z"},
            "instance": {"source_bind_sha256": "UNVERIFIED_SYNTHETIC", "morphology": morphology},
            "loop": {"enabled": True, "period_s": 1, "cycle_delta_m": [0, 0, 0]}}
    frames = []
    for t in (0, .5, 1):
        target = {"time_s": t, "hip_center_m": [0, 1, 0], "feet": {}, "hands_m": {}}
        actual = {"hip_center_m": [0, 1, 0], "feet": {}, "hands_m": {},
                  "intermediate_bones": copy.deepcopy(rest["intermediate_bones"])}
        for side, x in (("L", .1), ("R", -.1)):
            actual["feet"][side] = {"hip_m": [x, 1, 0], "knee_m": [x, .6, 0], "ankle_m": [x, .2, 0],
                                    "heel_m": [x, 0, -.05], "forefoot_m": [x, 0, .15], "toe_m": [x, 0, .25], "skin_sole_min_y_m": 0}
            target["feet"][side] = {"ankle_m": [x, .2, 0], "contacts": {"heel": True, "forefoot": True}, "contact_reference": "world:ground_y0"}
        frames.append({"time_s": t, "target": target, "actual": actual})
    clip["frames"] = [{"time_s": f["time_s"]} for f in frames]
    return {"schema": "oneirifact.motion-consumer-observations/v1", "cases": [{"id": "analytic", "bind_sha": "UNVERIFIED_SYNTHETIC", "rest": rest,
            "clips": [{"activity_id": "standing", "compiler_clip": clip, "frames": frames}]}]}


def run():
    records = []
    def result(data): return review(data)["cases"][0]["clips"][0]
    def expect(name, data, gate, status):
        outcome = result(data)
        observed = outcome["status"] if gate is None else outcome["gates"][gate]["status"]
        if observed != status: raise AssertionError((name, observed, status))
        records.append({"oracle": name, "expected": status, "observed": observed, "pass": True})
    base = fixture()
    if result(base)["failed_gates"]: raise AssertionError("analytic stationary positive control failed")
    records.append({"oracle": "stationary analytic geometry", "expected": "no failed gates", "observed": "no failed gates", "pass": True})
    changed = copy.deepcopy(base)
    changed["cases"][0]["clips"][0]["frames"][1]["actual"]["feet"]["L"]["heel_m"][0] += .02
    expect("20 mm planted heel displacement", changed, "planted_drift_m", "FAIL")
    changed = copy.deepcopy(base)
    changed["cases"][0]["clips"][0]["frames"][1]["actual"]["feet"]["L"]["knee_m"][1] += .02
    expect("20 mm anatomical segment length drift", changed, "limb_length_drift_m", "FAIL")
    changed = copy.deepcopy(base)
    changed["cases"][0]["clips"][0]["frames"][1]["target"]["feet"]["L"]["ankle_m"][1] = -.1
    expect("unreachable intended ankle", changed, "reach_excess_m", "FAIL")
    changed = copy.deepcopy(base)
    changed["cases"][0]["clips"][0]["frames"][-1]["actual"]["feet"]["L"]["ankle_m"][2] += .02
    expect("20 mm loop seam", changed, "loop_position_seam_m", "FAIL")
    changed = copy.deepcopy(base)
    changed["cases"][0]["clips"][0]["frames"][1]["actual"]["intermediate_bones"]["upperleg02.L"]["relative_rotation_xyzw"] = [math.sin(.01), 0, 0, math.cos(.01)]
    expect("rigid intermediate bone bends 0.02 rad", changed, "intermediate_rotation_drift_rad", "FAIL")
    changed = copy.deepcopy(base)
    changed["cases"][0]["clips"][0]["frames"][1]["actual"]["intermediate_bones"]["upperleg02.L"]["relative_rotation_xyzw"] = [0, 0, 0, -1]
    expect("quaternion double cover is same pose", changed, "intermediate_rotation_drift_rad", "PASS")
    changed = copy.deepcopy(base)
    changed["cases"][0]["clips"][0]["frames"] = []
    expect("empty observations cannot pass", changed, None, "INVALID_OBSERVATIONS")
    changed = copy.deepcopy(base)
    changed["cases"][0]["clips"][0]["frames"][1]["time_s"] = 0
    expect("duplicate timestamps cannot pass", changed, None, "INVALID_OBSERVATIONS")
    changed = copy.deepcopy(base)
    clip = changed["cases"][0]["clips"][0]
    clip["compiler_clip"]["loop"]["cycle_delta_m"] = [0, 0, .3]
    for frame in clip["frames"]:
        dz = .3*frame["time_s"]
        for group in ("actual", "target"):
            frame[group]["hip_center_m"][2] += dz
            for foot in frame[group]["feet"].values():
                for key, point in foot.items():
                    if key.endswith("_m") and isinstance(point, list): point[2] += dz
                if group == "target": foot["contacts"] = {"heel": False, "forefoot": False}
    expect("travelling loop compensates root delta", changed, "loop_position_seam_m", "PASS")
    for defect, expected in ((None, "PASS"), ("step", "FAIL"), ("stretch", "FAIL")):
        observed = audit(AnalyticIntentField(defect), {"id": "analytic"}, {"id": "analytic"})["status"]
        if observed != expected: raise AssertionError(("intent epsilon oracle", defect, observed, expected))
        records.append({"oracle": "intent field "+str(defect), "expected": expected, "observed": observed, "pass": True})
    return {"schema": "oneirifact.motion-critic-analytic-oracles/v1", "status": "PASS", "oracles": records,
            "scope": "Independent exact synthetic geometry verifies critic sensitivity, not the Blender consumer or realistic human motion."}


if __name__ == "__main__": print(json.dumps(run(), indent=2))
