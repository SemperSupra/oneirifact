"""Independent read-only delivery witness for the released v3 human design site."""
import hashlib,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_delivery as v
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"gallery"))
import restore_anatomy_release as a
import restore_adult_design_release as d
import tempfile
ROOT=Path(__file__).resolve().parents[1]
def sha(x):return hashlib.sha256(x).hexdigest()
def require(x,msg):
    if not x:raise ValueError(msg)
def run():
    # The archive restore is independent of live web delivery and needs no token.
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td);al=a.restore(dest=folder/"anatomy");d.restore(dest=folder/"morph");dl=json.loads(d.LOCK.read_text())
        raw=v.fetch(v.BASE+v.MANIFEST,v.MAX_MANIFEST)
        rows=v.validate(json.loads(raw));index={r["path"]:r for r in rows}
        for prefix,src in (("anatomy/data",folder/"anatomy"),("morph",folder/"morph")):
            for f in src.rglob("*"):
                if f.is_file():
                    name=prefix+"/"+f.relative_to(src).as_posix();b=f.read_bytes()
                    require(index[name]["sha256"]==sha(b) and index[name]["bytes"]==len(b),"release asset mismatch "+name)
        for name,src in (("anatomy/index.html",ROOT/"site/anatomy/index.html"),("index.html",ROOT/"site/index.html"),("anatomy/viewer.css",ROOT/"site/anatomy/viewer.css"),("anatomy/viewer.js",ROOT/"site/anatomy/viewer.js")):
            require(index[name]["sha256"]==sha(src.read_bytes()),"released source mismatch "+name)
        for route,name in (("","index.html"),("anatomy/","anatomy/index.html"),("morph/","morph/index.html")):
            r=index[name];b=v.fetch(v.BASE+route,r["bytes"])
            require(len(b)==r["bytes"] and sha(b)==r["sha256"],"route mismatch "+route)
        cat=json.loads((folder/"anatomy/catalog.json").read_text());models=[m for x in cat["datasets"] for m in x["layers"]]
        require(len(cat["datasets"])==al["datasets"]==7 and len(models)==al["models"]==53,"catalog inventory")
        mammary=next(x for x in cat["datasets"] if x["id"]=="mammary")
        require(len(mammary["layers"])==16 and all(x in mammary for x in ("inventory","attribution","receipt")),"mammary inventory")
        count=v.verify(sha(raw))
        return {"status":"LIVE_HUMAN_DESIGN_VERIFIED","base":v.BASE,"manifest_sha256":sha(raw),"assets":count,"models":len(models),"datasets":len(cat["datasets"]),"mammary_models":16,"anatomy_sha256":al["sha256"],"design_sha256":dl["sha256"],"routes":["anatomy/","morph/"]}
if __name__=="__main__":
    for n in range(8):
        try:
            r=run();print("R234_LIVE_HUMAN_DESIGN",json.dumps(r,sort_keys=True),flush=True)
            if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(r,indent=2)+"\n")
            break
        except Exception as e:
            print("LIVE_ATTEMPT",n+1,type(e).__name__,str(e),flush=True)
            if n==7:raise
            time.sleep(12)
