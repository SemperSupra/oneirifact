"""Package only the exact qualified public shared adult designer assets."""
import json,stat,sys,zipfile
from pathlib import Path
import anatomy_pack as p
from qualify_r233_delivery import add
OUTER="5f7b9fa892a3d32addbfb60f83f87d6957f45f1dd1f68b670ed836888295dd0d"
ASSET="shared-design-r237-v1.zip"
FILES={"index.html","style.css","app.mjs","core.mjs","data/basis.bin","data/faces.bin","data/rig.json","data/LICENSE.md","data/LICENSE.ASSETS.md"}
def verify_design(path,expected):
    p.require(path.is_file() and path.stat().st_size<=16<<20 and p.digest(path)==expected,"archive hash/budget")
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        p.require(len(names)==len(FILES)+1 and set(names)==FILES|{"manifest.json"},"archive inventory")
        m=z.getinfo("manifest.json");p.require(m.file_size<=65536 and stat.S_ISREG(m.external_attr>>16),"manifest budget/type")
        doc=p.parse(z.read(m));p.require(doc["schema"]=="oneirifact.shared-design-pack/v1","manifest schema")
        rows=doc["files"]
        p.require(len(rows)==len(FILES) and {r["path"] for r in rows}==FILES,"manifest inventory")
        for row in rows:
            i=z.getinfo(row["path"]);p.require(0<i.file_size<=8<<20 and stat.S_ISREG(i.external_attr>>16),"asset type/budget")
            b=z.read(i);p.require(len(b)==row["bytes"] and p.sha(b)==row["sha256"],"asset digest")
        p.require(len(z.read("data/basis.bin"))==7356672 and len(z.read("data/faces.bin"))==26756*3*4,"basis topology")
        rig=p.parse(z.read("data/rig.json"))
        p.require(rig["basis_count"]==32 and rig["vertex_count"]==19158 and rig["visible"]==13380 and len(rig["bones"])==163 and len(rig["weights"])==13380 and len(rig["regional_keys"])==11,"rig inventory")
        return rows
def main(source,out):
    p.require(p.digest(source)==OUTER,"qualified transport hash")
    out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(source) as z:
        p.require(len(z.namelist())==18 and len(set(z.namelist()))==18,"transport inventory")
        rows=[]
        with zipfile.ZipFile(out/ASSET,"x") as q:
            for n in sorted(FILES):
                i=z.getinfo("site/morph/"+n)
                p.require(0<i.file_size<=8<<20 and not stat.S_ISLNK(i.external_attr>>16),"source budget/type")
                b=z.read(i);rows.append({"path":n,"bytes":len(b),"sha256":p.sha(b)});add(q,n,b)
            add(q,"manifest.json",(json.dumps({"schema":"oneirifact.shared-design-pack/v1","files":rows},sort_keys=True,separators=(",",":"))+"\n").encode())
    sha=p.digest(out/ASSET);p.require(verify_design(out/ASSET,sha)==rows,"restore parity")
    report={"schema":"oneirifact.shared-design-release/v1","tag":"shared-design-r237-v1","asset":ASSET,"sha256":sha,"files":len(rows),"unpacked_bytes":sum(r["bytes"] for r in rows),"source_head":"631276c95d44e76dbc3571863d0ae2552b41fc3d","source_artifact":15259064051,"source_run":46135477931,"scope":"Adult exterior design only, 11 regional controls, explicit binary/advanced configuration; no internal anatomy generation."}
    (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R237_SHARED_DESIGN_PACK",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":main(*(Path(x) for x in sys.argv[1:]))
