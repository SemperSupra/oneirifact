#!/usr/bin/env python3
"""Black-box public-API epsilon probes of authored gait intent boundaries."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

EPSILON_S = 1e-5
POSITION_JUMP_M = 0.0001
ROTATION_JUMP_RAD = 0.0001
VELOCITY_JUMP_M_S = 0.05
SOLE_LENGTH_DRIFT_M = 1e-8


def norm(x): return math.sqrt(sum(v*v for v in x))
def sub(a, b): return [x-y for x, y in zip(a, b)]
def distance(a, b): return norm(sub(a, b))
def angle(a, b):
    c = abs(sum(x*y for x, y in zip(a, b)))/(norm(a)*norm(b))
    return 2*math.acos(min(1., max(0., c)))


def audit(compiler, morphology, footwear):
    library = compiler.library()
    results = []
    for activity, definition in library["activities"].items():
        if definition.get("kind") != "gait" or definition["implementation"] == "PLANNED": continue
        period, stance = definition["period_s"], definition["stance_fraction"]
        clip = compiler.compile_clip(activity, morphology, footwear, fps=120)
        lengths = {s: [distance(f["feet"][s]["heel_m"], f["feet"][s]["forefoot_m"]) for f in clip["frames"]] for s in ("L", "R")}
        rigid = max(max(v)-min(v) for v in lengths.values())
        boundaries = []
        for side, offset in (("L", 0.), ("R", .5)):
            # Middle cycles avoid seek-domain zero and exercise both legs.
            for name, phase in (("heel_to_flat", .16*stance), ("flat_to_toe", .76*stance), ("toe_to_swing", stance), ("swing_to_heel", 1.)):
                time = (2+phase-offset)*period
                samples = []
                for dt in (-EPSILON_S, 0., EPSILON_S):
                    small = compiler.compile_clip(activity, morphology, footwear, fps=24, duration_s=.001, start_time_s=time+dt)
                    samples.append(small["frames"][0]["feet"][side])
                jump, derivative_jump = 0., 0.
                marker_rows = {}
                for marker in ("ankle_m", "heel_m", "forefoot_m", "toe_m"):
                    before, middle, after = [f[marker] for f in samples]
                    marker_jump = distance(before, after)
                    v0, v1 = [x/EPSILON_S for x in sub(middle, before)], [x/EPSILON_S for x in sub(after, middle)]
                    vjump = distance(v0, v1)
                    marker_rows[marker] = {"two_sided_position_difference_m": marker_jump, "one_sided_velocity_difference_m_s": vjump}
                    jump, derivative_jump = max(jump, marker_jump), max(derivative_jump, vjump)
                rotation = angle(samples[0]["rotation_xyzw"], samples[2]["rotation_xyzw"])
                boundaries.append({"side": side, "boundary": name, "time_s": time, "marker_measurements": marker_rows,
                                   "rotation_difference_rad": rotation,
                                   "status": "PASS" if jump <= POSITION_JUMP_M and rotation <= ROTATION_JUMP_RAD and derivative_jump <= VELOCITY_JUMP_M_S else "FAIL"})
        results.append({"activity_id": activity, "rigid_heel_forefoot_range_m": rigid,
                        "rigid_support_status": "PASS" if rigid <= SOLE_LENGTH_DRIFT_M else "FAIL",
                        "boundaries": boundaries})
    return {"schema": "oneirifact.motion-intent-boundary-audit/v1", "morphology_id": morphology["id"], "footwear_id": footwear["id"],
            "thresholds": {"epsilon_s": EPSILON_S, "position_jump_m": POSITION_JUMP_M, "rotation_jump_rad": ROTATION_JUMP_RAD,
                           "one_sided_velocity_jump_m_s": VELOCITY_JUMP_M_S, "rigid_sole_length_drift_m": SOLE_LENGTH_DRIFT_M},
            "results": results, "status": "FAIL" if any(x["rigid_support_status"] == "FAIL" or any(b["status"] == "FAIL" for b in x["boundaries"]) for x in results) else "PASS",
            "scope": "Black-box intent geometry and epsilon continuity screen; no actual FK, human realism, force consistency or physiological qualification."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("inputs", type=Path, help="JSON containing morphology and footwear")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("candidate_compiler", args.compiler)
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    data = json.loads(args.inputs.read_text())
    result = audit(compiler, data["morphology"], data["footwear"])
    result["compiler_sha256"] = hashlib.sha256(args.compiler.read_bytes()).hexdigest()
    result["library_sha256"] = hashlib.sha256(args.compiler.with_name("library.json").read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
