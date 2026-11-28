"""Read actual post-morph source anchors without editing meshes or weights."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import compiler

PREP_HEAD = "7fc8141fef8e2133ecceb2474005e82da4da69ad"
SOURCE_PINS = [
    {"artifact_id": 15260769266, "archive_sha256": "f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f"},
    {"artifact_id": 15258079477, "archive_sha256": "025145c2af4dc0c0d8936e764b88dd03a06a9e389197cadf97eb9b1d634d54fc"}
]


def measure(case_dir, helper_dir):
    spec = importlib.util.spec_from_file_location("aquatic_exact_gltf", Path(helper_dir)/"gltf.py")
    gltf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gltf)
    case = json.loads((case_dir/"case.json").read_text())
    m = case["morphology"]
    raw = (case_dir/"bound-source.glb").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == m["source_bind_sha256"]
    d, b = gltf.parse(raw)
    w, _ = gltf.worlds(d)
    names = {n["name"]: i for i, n in enumerate(d["nodes"][:163])}
    anchor = lambda name: w[names[name], :3, 3]
    arms, ids = {}, {}
    for s in ("L", "R"):
        shoulder, elbow, wrist = (anchor(n+"."+s) for n in ("upperarm01", "lowerarm01", "wrist"))
        arms[s] = {"shoulder_m": shoulder.tolist(), "elbow_m": elbow.tolist(), "wrist_m": wrist.tolist(),
                   "upper_m": float(np.linalg.norm(elbow-shoulder)), "lower_m": float(np.linalg.norm(wrist-elbow))}
        for n in ("upperarm01", "lowerarm01", "wrist", "upperleg01", "lowerleg01", "foot"): ids[n+"."+s] = names[n+"."+s]
        for k, name in (("hips_m", "upperleg01"), ("knees_m", "lowerleg01"), ("ankles_m", "foot")):
            assert np.max(abs(anchor(name+"."+s)-m[k][s])) < 1e-8
    attrs = d["meshes"][0]["primitives"][0]["attributes"]
    vertices = gltf.read(d, b, attrs["POSITION"])
    hip = np.array(m["hip_center_m"])
    shoulder_center = (anchor("upperarm01.L")+anchor("upperarm01.R"))/2
    target_y = hip[1]+.65*(shoulder_center[1]-hip[1])
    # Select one existing anterior midline skin vertex, never invent a surface
    # point. This is a reproducible task anchor, not a medical sternal landmark.
    band = np.flatnonzero((abs(vertices[:, 0]-hip[0]) < .055*m["stature_m"]) &
                          (abs(vertices[:, 1]-target_y) < .025*m["stature_m"]))
    assert len(band) > 10
    target = np.array([hip[0], target_y, vertices[band, 2].max()])
    vertex_id = int(band[np.argmin(((vertices[band]-target)**2).sum(1))])
    measurements = {"schema": "oneirifact.aquatic-source-measurements/v1", "source_bind_sha256": m["source_bind_sha256"],
                    "arms": arms, "chest_surface_anchor_m": vertices[vertex_id].astype(float).tolist(),
                    "chest_source_vertex_id": vertex_id, "source_mesh_position_sha256": hashlib.sha256(vertices.tobytes()).hexdigest(),
                    "bone_node_ids": ids,
                    "method": "Rest-world upperarm01/lowerarm01/wrist heads. Existing anterior midline skin vertex nearest hip-to-shoulder 0.65-height target in a bounded source band. No source edit."}
    compiler._measurement(measurements, m)
    return {"schema": "oneirifact.aquatic-compiler-input/v1", "morphology": m, "footwear": compiler.barefoot(m),
            "limb_measurements": measurements,
            "source_provenance": {"preparation_repository": "SemperSupra/oneirifact", "preparation_head": PREP_HEAD,
                                  "artifacts": SOURCE_PINS, "source": case["source"], "morphology_scope": case["morphology_scope"],
                                  "input_case_shoe_profile": case["shoe_profile"], "aquatic_footwear": "explicit measured barefoot; no shoe-profile pass inherited",
                                  "original_rig_bones": case["original_rig_bones"], "max_skin_influences": case["max_skin_influences"],
                                  "positive_skin_influences": case["positive_skin_influences"]}}


if __name__ == "__main__":
    result = measure(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
