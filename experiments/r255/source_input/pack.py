"""Deterministic exact-byte subset of the qualified aquatic source archive."""
import hashlib,json,sys,zipfile
from pathlib import Path

UPSTREAM_SHA="e694ab4d06bae33bf829e624d03a2bd81bb28d8b8059c42ae83e36819f33dd68"
UPSTREAM_HEAD="2e93628bbda838887bd51133789aca56e31f3a08"
CASES=("male155flat","female155flat","female185flat")
def sha(raw):return hashlib.sha256(raw).hexdigest()
def packed_json(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
def build(source,out):
    source=Path(source);out=Path(out);assert source.is_file() and not out.exists()
    raw=source.read_bytes();assert sha(raw)==UPSTREAM_SHA
    entries={}
    with zipfile.ZipFile(source) as z:
        assert z.testzip() is None
        receipt_raw=z.read("receipt.json");receipt=json.loads(receipt_raw)
        assert receipt["head_sha"]==UPSTREAM_HEAD and str(receipt["github_run_id"])=="46153095988"
        assert receipt["status"]=="PASS_BOUNDED_AQUATIC_INTENT"
        rows=[f for f in receipt["files"] if f["path"].split("/")[0] in CASES];assert len(rows)==54
        for row in rows:
            p=Path(row["path"]);assert len(p.parts)==2 and p.parts[0] in CASES and ".." not in p.parts
            b=z.read(row["path"]);assert len(b)==row["bytes"] and sha(b)==row["sha256"];entries[row["path"]]=b
        entries["upstream-receipt.json"]=receipt_raw
    files=[{"path":name,"bytes":len(b),"sha256":sha(b)} for name,b in sorted(entries.items())]
    manifest={"schema":"oneirifact.exact-motion-source-input/v1","id":"r255-source-bind-inputs-v1","cases":list(CASES),
        "upstream":{"repository":"SemperSupra/oneirifact","artifact_id":15266855834,"archive_sha256":UPSTREAM_SHA,"head":UPSTREAM_HEAD,"run_id":46153095988},
        "source_prepare_head":"7fc8141fef8e2133ecceb2474005e82da4da69ad","files":files,
        "scope":"Exact original source binds, cases, aquatic compiler fixtures, receipts and notices for three admitted morphology cases. No reconstruction from animated GLBs and no geometry edits.",
        "zip_method":"ZIP_STORED with fixed timestamp and Unix regular-file mode; deterministic across compression library versions."}
    entries["source-input-manifest.json"]=packed_json(manifest)
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_STORED) as z:
        for name,b in sorted(entries.items()):
            info=zipfile.ZipInfo(name,(2026,11,28,0,0,0));info.create_system=3;info.external_attr=(0o100644<<16);info.compress_type=zipfile.ZIP_STORED;z.writestr(info,b)
    result={"file_name":out.name,"bytes":out.stat().st_size,"sha256":sha(out.read_bytes()),"files":len(entries),"original_case_files":54,"cases":list(CASES),"upstream_archive_sha256":UPSTREAM_SHA}
    print(json.dumps(result,sort_keys=True));return result
if __name__=="__main__":build(sys.argv[1],sys.argv[2])
