"""Qualify the exact, independently browser-tested R229 display asset corpus.
No original raw donor or private source data is packaged.
"""
import argparse,json,stat,zipfile
from pathlib import Path
import anatomy_pack as p
INPUT_SHA="f617bbdd25b5d8b4ce94ab95046da7403b82f3d16855d0af2f9d2cc732bffb41"
def qualify(source,work):
    p.require(p.digest(source)==INPUT_SHA,"unexpected browser-qualified input")
    work.mkdir(parents=True,exist_ok=False)
    dest=work/"source";dest.mkdir()
    with zipfile.ZipFile(source) as z:
        infos=z.infolist()
        p.require(len(infos)==47 and len({i.filename for i in infos})==47,"unexpected corpus inventory")
        p.require(sum(i.file_size for i in infos)==49541257,"unexpected corpus byte count")
        for i in infos:
            p.require(p.NAME.fullmatch(i.filename) and i.filename!=p.MANIFEST and not i.is_dir() and 0<i.file_size<=p.MAX_FILE,"invalid input asset")
            p.require(not stat.S_ISLNK(i.external_attr>>16),"symlink")
            (dest/i.filename).write_bytes(z.read(i))
    entries=p.inventory(dest)
    catalog=p.parse((dest/"catalog.json").read_bytes())
    models=[m for d in catalog["datasets"] for m in d["layers"]]
    p.require(len(catalog["datasets"])==4 and len(models)==32,"unexpected model count")
    a=work/"anatomy-display-r229-v1.zip";b=work/"repeat.zip"
    expected=p.pack(dest,a)
    p.require(p.pack(dest,b)==expected and a.read_bytes()==b.read_bytes(),"pack nondeterminism")
    b.unlink()
    restored=p.restore(a,expected,work/"restored")
    p.require(restored==entries,"restored corpus differs")
    report={"schema":"oneirifact.browser-display-qualification/v1","source_artifact_id":15252399892,"source_sha256":INPUT_SHA,"pack_sha256":expected,"assets":len(entries),"models":len(models),"datasets":len(catalog["datasets"]),"bytes":sum(r["bytes"] for r in entries.values()),"qualified_release_pr":52,"qualified_head":"689060c27417619d803e176d73722d5878289e04","status":"PASS_ACTUAL_CORPUS_ROUNDTRIP"}
    (work/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True))
    print("PACK_SHA256",expected)
    return report
if __name__=="__main__":
    q=argparse.ArgumentParser();q.add_argument("source",type=Path);q.add_argument("work",type=Path);a=q.parse_args()
    qualify(a.source,a.work)
