"""Execute bounded contract checks and emit replayable illustrative instances.

The fixture is explicitly synthetic. Actual morphology and native FK evaluation
belong to the independent Blender consumer, not this target-only harness.
"""
import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import compiler


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parent
    morphology = json.loads((root / "example-morphology.json").read_text())
    definition = compiler.library()
    (out / "definition.json").write_text(json.dumps(definition, indent=2)+"\n")
    (out / "instances").mkdir()
    (out / "clips").mkdir()
    (out / "audits").mkdir()
    audit_path = root.parent / "review" / "compiler_audit.py"
    spec = importlib.util.spec_from_file_location("independent_boundary_audit", audit_path)
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    rows, audits, loops = [], [], []
    first = None
    for profile in definition["footwear_profiles"]:
        footwear = compiler.footwear_from_profile(profile, morphology)
        inputs = {"morphology": morphology, "footwear": footwear}
        (out / "instances" / (profile+"-inputs.json")).write_text(json.dumps(inputs, indent=2)+"\n")
        audit = review.audit(compiler, morphology, footwear)
        audit["critic_file_sha256"] = compiler.hashlib.sha256(audit_path.read_bytes()).hexdigest()
        (out / "audits" / (profile+"-boundary-audit.json")).write_text(json.dumps(audit, indent=2)+"\n")
        audits.append({"profile": profile, "status": audit["status"], "probes": sum(len(x["boundaries"]) for x in audit["results"])})
        compiler.need(audit["status"] == "PASS", "independent boundary screen failed")
        for name, activity in definition["activities"].items():
            if activity["implementation"] == "PLANNED":
                try: compiler.compile_clip(name, morphology, footwear)
                except compiler.UnsupportedActivity: pass
                else: raise AssertionError("planned activity silently generated placeholder frames")
                continue
            clip = compiler.compile_clip(name, morphology, footwear)
            compiler.need(compiler.canonical(clip) == compiler.canonical(compiler.compile_clip(name, morphology, footwear)), "deterministic replay")
            compiler.need(clip["target_reachability"]["status"] == "PASS_DISTANCE_SCREEN", "fixture target exceeds measured two-link reach")
            compiler.need(all(a["time_s"] < b["time_s"] for a, b in zip(clip["frames"], clip["frames"][1:])), "strict time ordering")
            maximum_contact_height = 0.
            for frame in clip["frames"]:
                for foot in frame["feet"].values():
                    for contact, active in foot["contacts"].items():
                        if active: maximum_contact_height = max(maximum_contact_height, abs(foot[contact+"_m"][1]))
            compiler.need(maximum_contact_height < 1e-9, "declared planar contact target off ground")
            ident = profile+"--"+name
            (out / "instances" / (ident+".json")).write_text(json.dumps(clip["instance"], indent=2)+"\n")
            (out / "clips" / (ident+".json")).write_text(json.dumps(clip, indent=2)+"\n")
            rows.append({"id": ident, "activity": name, "implementation": clip["implementation"], "frames": len(clip["frames"]),
                         "definition_sha256": clip["definition"]["activity_sha256"], "instance_sha256": clip["instance_sha256"],
                         "clip_sha256": clip["clip_sha256"], "contact_target_max_height_m": maximum_contact_height,
                         "target_reachability": clip["target_reachability"]["status"], "actual_consumer": "NOT_RUN", "realism": "NOT_QUALIFIED"})
            if first is None: first = clip
            if activity.get("loop"):
                period = activity.get("period_s", activity["duration_s"])
                a = compiler.compile_clip(name, morphology, footwear, duration_s=.01)["frames"][0]
                b = compiler.compile_clip(name, morphology, footwear, duration_s=.01, start_time_s=period)["frames"][0]
                delta = clip["loop"]["cycle_delta_m"]
                error = compiler.norm(compiler.sub(compiler.sub(b["hip_center_m"], a["hip_center_m"]), delta))
                for side in ("L", "R"):
                    for marker in ("ankle_m", "heel_m", "forefoot_m", "toe_m"):
                        error = max(error, compiler.norm(compiler.sub(compiler.sub(b["feet"][side][marker], a["feet"][side][marker]), delta)))
                compiler.need(error < 1e-9, "loop root-delta replay failed")
                loops.append({"activity": name, "profile": profile, "maximum_root_relative_error_m": error})
    flat = compiler.footwear_from_profile("flats", morphology)
    stand = compiler.compile_clip("standing", morphology, flat)
    sit = compiler.compile_clip("sitting", morphology, flat)
    transition = compiler.compile_clip("sit_to_stand", morphology, flat)
    compiler.need(compiler.norm(compiler.sub(sit["frames"][0]["hip_center_m"], transition["frames"][0]["hip_center_m"])) < 1e-12, "transition source posture")
    compiler.need(compiler.norm(compiler.sub(stand["frames"][0]["hip_center_m"], transition["frames"][-1]["hip_center_m"])) < 1e-12, "transition destination posture")
    seat = transition["frames"][0]["hip_center_m"]
    for frame in transition["frames"]:
        if frame["prop_contacts"]: compiler.need(compiler.norm(compiler.sub(frame["hip_center_m"], seat)) < 1e-12, "seat contact while pelvis translating")
    base = compiler.compile_clip("walking", morphology, flat)
    upper = compiler.compile_clip("brushing_teeth", morphology, flat, duration_s=base["instance"]["duration_s"])
    composed = compiler.compose_upper_body(base, upper)
    compiler.need([x["feet"] for x in base["frames"]] == [x["feet"] for x in composed["frames"]], "upper-body overlay changed foot contacts")
    compiler.need([x["hip_center_m"] for x in base["frames"]] == [x["hip_center_m"] for x in composed["frames"]], "upper-body overlay changed root")
    (out / "clips" / "composed-walk-brush-ILLUSTRATIVE.json").write_text(json.dumps(composed, indent=2)+"\n")
    negatives = []
    def rejected(name, fn):
        try: fn()
        except (ValueError, TypeError, KeyError): negatives.append({"name": name, "status": "PASS_REJECTED"})
        else: raise AssertionError("invalid input accepted: "+name)
    rejected("unknown_activity", lambda: compiler.compile_clip("invented_unknown", morphology, flat))
    rejected("bool_seed", lambda: compiler.compile_clip("standing", morphology, flat, seed=True))
    rejected("bool_fps", lambda: compiler.compile_clip("standing", morphology, flat, fps=True))
    rejected("string_time", lambda: compiler.compile_clip("standing", morphology, flat, start_time_s="0"))
    for bad, label in ((True, "bool_coordinate"), ("0", "string_coordinate"), (float("nan"), "nan_coordinate")):
        altered = copy.deepcopy(morphology); altered["hip_center_m"][0] = bad
        rejected(label, lambda altered=altered: compiler.compile_clip("standing", altered, flat))
    altered = dict(flat, heel_stack_m=True)
    rejected("bool_shoe_stack", lambda: compiler.compile_clip("standing", morphology, altered))
    altered2 = dict(flat, heel_stack_m=1.0)
    rejected("unreachable_shoe_geometry", lambda: compiler.compile_clip("standing", morphology, altered2))
    altered3 = dict(flat, toe_pivot_fraction=.2)
    rejected("unsupported_toe_pivot", lambda: compiler.compile_clip("standing", morphology, altered3))
    altered4 = dict(morphology, presumed_age_weakness=.5)
    rejected("unknown_morph_parameter", lambda: compiler.compile_clip("standing", altered4, flat))
    altered5 = dict(flat, ground_slope=12)
    rejected("unknown_footwear_parameter", lambda: compiler.compile_clip("standing", morphology, altered5))
    rejected("foot_contact_overlay", lambda: compiler.compose_upper_body(base, upper, mask=("feet",)))
    rejected("conflicting_hand_layers", lambda: compiler.compose_upper_body(composed, upper))
    label_only = copy.deepcopy(morphology)
    label_only["id"] = "different-age-sex-description-same-measured-geometry"
    label_only["measurement_notes"] = "Labels must not infer weakness or stereotyped gait"
    compiler.need(compiler.compile_clip("walking", label_only, flat)["frames"] == base["frames"], "demographic label changed gait")
    requested = {"standing", "sitting", "crouching", "squatting", "walking", "jogging", "running", "swimming", "showering", "bathing", "brushing_teeth", "eating_ice_cream_cone"}
    compiler.need(requested <= set(definition["activities"]), "owner activity missing from catalog")
    report = {"schema": "oneirifact.activity-contract-receipt/v0.1", "status": "PASS_BOUNDED_INTENT_CONTRACT",
              "actual_native_consumer": "NOT_RUN", "realism": "NOT_QUALIFIED", "fixture": morphology["id"],
              "definition_sha256": compiler.digest(definition), "source_bind_sha256": morphology["source_bind_sha256"],
              "requested_activity_coverage": {name: definition["activities"][name]["implementation"] for name in sorted(requested)},
              "executed_clips": rows, "independent_boundary_audits": audits, "loop_replays": loops,
              "negative_contracts": negatives, "transition_endpoints": "PASS", "seat_release_before_translation": "PASS",
              "masked_composition_preserves_root_and_feet": "PASS", "demographic_label_invariance": "PASS",
              "source_execution_sha": os.environ.get("SOURCE_HEAD_SHA"), "workflow_sha": os.environ.get("GITHUB_SHA"),
              "limits": ["Synthetic fixture only; native consumer must measure actual morphed male/female models.", "Target phase/contact consistency is not observed FK, balance, physiological motion or realism.", "Water activity kinematic implementations remain planned; fluid physics is a separate gate.", "Hand task prototypes do not establish grip, mouth/tooth contact, collision or safe motion."]}
    report["files"] = {str(p.relative_to(out)): {"sha256": compiler.hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
                       for p in out.rglob("*") if p.is_file()}
    (out / "receipt.json").write_text(json.dumps(report, indent=2)+"\n")
    print("R245_ACTIVITY_CONTRACT", json.dumps({"status": report["status"], "clips": len(rows), "boundary_probes": sum(a["probes"] for a in audits),
          "negative_tests": len(negatives), "requested_activity_coverage": report["requested_activity_coverage"], "realism": report["realism"]}), flush=True)


if __name__ == "__main__": main(Path(sys.argv[1]))
