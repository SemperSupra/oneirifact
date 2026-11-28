"""Compare the integrated producer with actual frozen v2 public evidence.

The comparison tolerances concern repeat execution only. They do not change
the producer's contact/transport gates or admit a human activity as realistic.
"""
import hashlib,json,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
def sha(raw):return hashlib.sha256(raw).hexdigest()
def compare(root,group):
    root=Path(root);frozen=json.loads((HERE/"qualified-v2-metrics.json").read_text())
    expected={r["id"]:r for r in frozen["clips"] if r["group"]==group}
    present={p.parent.name for p in root.glob("*/receipt.json")}
    assert present==set(expected),(present,set(expected))
    rows=[]
    for activity,old in sorted(expected.items()):
        current=json.loads((root/activity/"receipt.json").read_text());failures=[]
        same={k:current[k]==old[k] for k in ("actors","duration_s","native_fps","helper_source_sha256","probe_scope","contact","realism","physics","retarget","technique","transport_tolerance_m")}
        if not all(same.values()):failures.append("source_scope_or_qualification_changed")
        inventory={k:v for k,v in current["model_inventory"].items() if k not in ("sha256","bytes")}
        if inventory!=old["model_inventory"]:failures.append("source_inventory_changed")
        delta={}
        if set(current["metrics"])!=set(old["metrics"]):failures.append("metric_set_changed")
        for key,before in old["metrics"].items():
            after=current["metrics"].get(key)
            if before is None or after is None:
                ok=before is after;difference=None;tolerance=None
            else:
                difference=abs(after-before)
                tolerance=1e-3 if key.endswith("_m_s") else 1e-6 if key.endswith("_rad") else 1e-5
                ok=difference<=tolerance
            delta[key]={"frozen":before,"replay":after,"absolute_difference":difference,"repeat_tolerance":tolerance,"within_repeat_tolerance":ok}
            if not ok:failures.append("metric_changed:"+key)
        if current["transport"]!="PASS" or current["worst_transport_error_m"]>5e-5:failures.append("transport_failure")
        actual_sha=sha((root/activity/"motion.glb").read_bytes())
        rows.append({"id":activity,"status":"PASS_REPLAY_EQUIVALENCE" if not failures else "FAIL_REPLAY_EQUIVALENCE","failures":failures,"exact_fields":same,
            "frozen_receipt_sha256":old["receipt_sha256"],"frozen_glb_sha256":old["glb_sha256"],"replay_glb_sha256":actual_sha,"glb_byte_identical":actual_sha==old["glb_sha256"],
            "frozen_worst_transport_error_m":old["worst_transport_error_m"],"replay_worst_transport_error_m":current["worst_transport_error_m"],"metrics":delta})
    result={"schema":"oneirifact.motion-source-integration-comparison/v1","status":"PASS" if all(not r["failures"] for r in rows) else "FAIL","group":group,
        "frozen_source":frozen["producer"],"baseline_metric_file_sha256":sha((HERE/"qualified-v2-metrics.json").read_bytes()),"clips":rows,
        "scope":"Source/runtime integration replay only. Existing contact/realism/technique holds and failures remain. GLB byte identity is reported separately from numerical equivalence; no native .blend byte identity is claimed."}
    (root/"source-integration-comparison.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":result["status"],"group":group,"clips":len(rows),"identical_glbs":sum(r["glb_byte_identical"] for r in rows)}))
    assert result["status"]=="PASS",[(r["id"],r["failures"]) for r in rows if r["failures"]]
if __name__=="__main__":compare(sys.argv[1],sys.argv[2])
