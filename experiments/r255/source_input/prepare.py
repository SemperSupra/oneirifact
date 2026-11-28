"""Restore exact source cases from the immutable R255 input release pack."""
import hashlib,json,sys,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
def sha(raw):return hashlib.sha256(raw).hexdigest()
def prepare(archive,out,receipt_path=None):
    lock=json.loads((HERE/"input-lock.json").read_text());archive=Path(archive);out=Path(out)
    raw=archive.read_bytes();assert len(raw)==lock["bytes"] and sha(raw)==lock["sha256"]
    assert not out.exists();out.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read("source-input-manifest.json"));assert manifest["id"]==lock["id"]
        assert manifest["upstream"]["archive_sha256"]==lock["upstream_archive_sha256"]
        expected={f["path"] for f in manifest["files"]}|{"source-input-manifest.json"};assert set(z.namelist())==expected and len(z.namelist())==len(expected)
        for row in manifest["files"]:
            p=Path(row["path"]);assert not p.is_absolute() and ".." not in p.parts
            b=z.read(row["path"]);assert len(b)==row["bytes"] and sha(b)==row["sha256"]
            target=out/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
        (out/"source-input-manifest.json").write_bytes(z.read("source-input-manifest.json"))
        for case in manifest["cases"]:
            model=json.loads((out/case/"case.json").read_text());assert sha((out/case/"bound-source.glb").read_bytes())==model["morphology"]["source_bind_sha256"]
    receipt={"schema":"oneirifact.exact-source-restore/v1","status":"PASS_EXACT_ORIGINAL_ENTRIES","cases":manifest["cases"],"verified_files":len(manifest["files"]),"source_release":lock,"scope":"Original source entries restored byte-for-byte; no source reconstruction or new morphology/contact acceptance."}
    if receipt_path:Path(receipt_path).write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt))
    return receipt
if __name__=="__main__":prepare(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else None)
