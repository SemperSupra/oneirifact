"""Qualify exact public CC0 adult-design and HRA display candidate archives.

Copy only allowlisted browser files, not raw donor source or screenshots.
No native or clinical claim. Release publisher is separate.
"""
import hashlib,io,json,stat,sys,tempfile,zipfile
from pathlib import Path
import anatomy_pack as p
MAM_OUTER="243c4f6e5efc4e74237a452f7dffa441cdd6de44f42f4da74d125b00bdc708ef"
MAM_SHA="d72fbb77b1b0603005131bbd387a36ce1c2c9965dfce13a30150a0f4b22d56be"
MORPH_OUTER="95333f23f479752970e25fe41b6c96f707cfa2d114436e0467973e2b6bd758aa"
BASE_SHA="ffac8867db9951a3d721558e7aad8ae9250b00798d4bf65b8c53e3d811ec0947"
MAM="anatomy-display-r233-v3.zip"
MORPH="adult-design-r233-v1.zip"
FILES={"index.html","style.css","app.mjs","morph-core.mjs","data/basis.bin","data/faces.bin","data/rig.json","data/LICENSE.md","data/LICENSE.ASSETS.md"}
def add(z,n,b):
    i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.create_system=3;i.external_attr=(stat.S_IFREG|0o644)<<16;i.compress_type=zipfile.ZIP_DEFLATED
    z.writestr(i,b,compresslevel=6)
def verify_design(path,expected):
    p.require(p.digest(path)==expected,"design pack hash")
    with zipfile.ZipFile(path) as z:
        names=z.namelist();p.require(len(names)==len(FILES)+1 and set(names)==FILES|{"manifest.json"},"design inventory")
        doc=p.parse(z.read("manifest.json"));p.require(doc["schema"]=="oneirifact.adult-design-pack/v1","design manifest")
        rows=doc["files"];p.require(len(rows)==len(FILES) and {r["path"] for r in rows}==FILES,"manifest inventory")
        for row in rows:
            i=z.getinfo(row["path"]);p.require(0<i.file_size<=8<<20 and stat.S_ISREG(i.external_attr>>16),"asset type/budget")
            b=z.read(i);p.require(len(b)==row["bytes"] and p.sha(b)==row["sha256"],"design asset digest")
        p.require(len(z.read("data/basis.bin"))==2988648 and len(z.read("data/faces.bin"))==26756*3*4,"basis topology")
        rig=p.parse(z.read("data/rig.json"));p.require(rig["visible"]==13380 and len(rig["bones"])==163 and len(rig["weights"])==13380,"rig inventory")
        return rows
def main(base,mammary,morph,out):
    out.mkdir(parents=True,exist_ok=False)
    p.require(p.digest(mammary)==MAM_OUTER and p.digest(morph)==MORPH_OUTER,"transport archive")
    with zipfile.ZipFile(mammary) as z:
        i=z.getinfo("mammary-display-candidate.zip");p.require(i.file_size<=64<<20,"mammary archive size")
        (out/MAM).write_bytes(z.read(i))
    a=p.verify(out/MAM,MAM_SHA);b=p.verify(base,BASE_SHA)
    p.require(len(a)==80 and len(b)==60 and all(a.get(n)==r for n,r in b.items() if n!="catalog.json"),"existing base asset changed")
    with zipfile.ZipFile(out/MAM) as z:
        cat=p.parse(z.read("catalog.json"))
        p.require(len(cat["datasets"])==7 and sum(len(d["layers"]) for d in cat["datasets"])==53 and cat["datasets"][-1]["id"]=="mammary","catalog identity")
    with zipfile.ZipFile(morph) as z:
        p.require(len(z.namelist())==18 and len(set(z.namelist()))==18,"morph transport inventory")
        rows=[]
        with zipfile.ZipFile(out/MORPH,"x") as q:
            for n in sorted(FILES):
                i=z.getinfo("site/morph/"+n);p.require(0<i.file_size<=8<<20 and not stat.S_ISLNK(i.external_attr>>16),"source file budget")
                raw=z.read(i);rows.append({"path":n,"bytes":len(raw),"sha256":p.sha(raw)});add(q,n,raw)
            add(q,"manifest.json",(json.dumps({"schema":"oneirifact.adult-design-pack/v1","files":rows},sort_keys=True,separators=(",",":"))+"\n").encode())
    design_sha=p.digest(out/MORPH);p.require(verify_design(out/MORPH,design_sha)==rows,"design verify")
    report={"schema":"oneirifact.human-design-release/v1","anatomy":{"sha256":MAM_SHA,"assets":80,"datasets":7,"models":53,"unpacked_bytes":sum(r["bytes"] for r in a.values()),"unchanged_v2_assets":59,"qualified_artifact":15257186134,"qualified_head":"7951cb68133458ef3be6c62f1fd7f584518a2cb9"},"design":{"sha256":design_sha,"files":len(rows),"unpacked_bytes":sum(r["bytes"] for r in rows),"qualified_artifact":15256567522,"qualified_head":"43f295a2b3ff84671c2378acb9c9551a0d6aff5d"},"scope":"Read-only reference anatomy and separate generic adult female exterior design. No integrated clinical/native body or individual donor inference."}
    (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R233_DELIVERY_PACKS",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":main(*(Path(x) for x in sys.argv[1:]))
