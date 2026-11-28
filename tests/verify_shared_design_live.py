"""Read-only production readback of the exact shared adult designer package."""
import json,sys,tempfile,time
from pathlib import Path
import verify_delivery as v
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"gallery"))
import restore_adult_design_release as design
import restore_anatomy_release as anatomy
def run():
    with tempfile.TemporaryDirectory() as td:
        dst=Path(td)
        dl=design.restore(dest=dst/"morph")
        al=anatomy.restore(dest=dst/"anatomy")
        v.require(dl["sha256"]=="5f3d2d1126dce81b813f25f392ae3d9571fe35f69d69de89939bcfcfabe61ff4","wrong design source lock")
        raw=v.fetch(v.BASE+v.MANIFEST,v.MAX_MANIFEST)
        entries={x["path"]:x for x in v.validate(json.loads(raw))}
        for prefix,root in (("morph",dst/"morph"),("anatomy/data",dst/"anatomy")):
            for path in root.rglob("*"):
                if not path.is_file():continue
                key=prefix+"/"+path.relative_to(root).as_posix()
                data=path.read_bytes();v.require(key in entries and entries[key]["bytes"]==len(data) and entries[key]["sha256"]==v.sha(data),"live package mismatch: "+key)
        for route,key in (("","index.html"),("morph/","morph/index.html"),("anatomy/","anatomy/index.html")):
            row=entries[key];v.require(v.sha(v.fetch(v.BASE+route,row["bytes"]))==row["sha256"],"route mismatch: "+route)
        count=v.verify(v.sha(raw))
        return {"status":"PASS_SHARED_DESIGN_LIVE_READBACK","design_sha256":dl["sha256"],"anatomy_sha256":al["sha256"],"manifest_sha256":v.sha(raw),"assets":count,"routes":["","morph/","anatomy/"],"scope":"Exact anonymous package restore, live bytes and HTTP routes. No native or anatomical coupling claim."}
if __name__=="__main__":
    for i in range(3):
        try:
            result=run();Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result));break
        except Exception as e:
            print("LIVE_READBACK",i+1,type(e).__name__,str(e),flush=True)
            if i==2:raise
            time.sleep(5)
