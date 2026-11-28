"""Verify immutable public aquatic intent/source archive and extract one case."""
import hashlib,json,sys,zipfile
from pathlib import Path
PIN="e694ab4d06bae33bf829e624d03a2bd81bb28d8b8059c42ae83e36819f33dd68"
HEAD="2e93628bbda838887bd51133789aca56e31f3a08"
archive=Path(sys.argv[1]);case=sys.argv[2];out=Path(sys.argv[3])
assert hashlib.sha256(archive.read_bytes()).hexdigest()==PIN
out.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    receipt=json.loads(z.read("receipt.json"));assert receipt["head_sha"]==HEAD and str(receipt["github_run_id"])=="46153095988"
    assert receipt["status"]=="PASS_BOUNDED_AQUATIC_INTENT"
    rows=[r for r in receipt["files"] if r["path"].startswith(case+"/")];assert len(rows)>10
    for row in rows:
        p=Path(row["path"]);assert len(p.parts)==2 and p.parts[0]==case and ".." not in p.parts
        raw=z.read(row["path"]);assert len(raw)==row["bytes"] and hashlib.sha256(raw).hexdigest()==row["sha256"]
        (out/p.name).write_bytes(raw)
    (out/"input-aquatic-intent-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    model=json.loads((out/"case.json").read_text())
    assert hashlib.sha256((out/"bound-source.glb").read_bytes()).hexdigest()==model["morphology"]["source_bind_sha256"]
    provenance={"source_artifact_id":15266855834,"source_archive_sha256":PIN,"source_run_id":46153095988,"source_head_commit":HEAD,
       "source_preparation_head":"7fc8141fef8e2133ecceb2474005e82da4da69ad","case":case,"verified_files":rows,"actual_footwear":"explicit barefoot; source case names retain historical shoe labels"}
    (out/"aquatic-native-input.json").write_text(json.dumps(provenance,indent=2)+"\n")
print("R246_PREPARED",json.dumps({"case":case,"verified_files":len(rows),"source_bind_sha256":model["morphology"]["source_bind_sha256"]}))
