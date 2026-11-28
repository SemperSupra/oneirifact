"""Independent R222 mesh transport and semantic coverage audit.
Never change original anatomical reference geometry or claim clinical completeness.
"""
import sys,hashlib,json,zipfile,io,re
from pathlib import Path
from collections import Counter
import numpy as np
import trimesh
PINS={"male":"18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9","female":"513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542"}
BP="b13e23f595be27237ce69246484fd781553181d91e3ab7bda042bafb9aedd133"
def sha(b):return hashlib.sha256(b).hexdigest()
def checked(p,h):
    assert sha(p.read_bytes())==h
    return zipfile.ZipFile(p)
def scene(raw):return trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
def obj(raw):
    v=[];f=[]
    for l in raw.decode("utf-8",errors="replace").splitlines():
        t=l.split()
        if not t:continue
        if t[0]=="v":v.append([float(x) for x in t[1:4]])
        elif t[0]=="f":
            ids=[int(x.split("/")[0]) for x in t[1:]];ids=[i-1 if i>0 else len(v)+i for i in ids]
            f.extend((ids[0],ids[j],ids[j+1]) for j in range(1,len(ids)-1))
    return np.array(v),np.array(f)
def world(s,id):
    mat,g=s.graph[id];m=s.geometry[g]
    return trimesh.transform_points(m.vertices,mat),np.asarray(m.faces)
def compare(a,af,b,bf):
    # Compare actual ordered triangle corners, independent of vertex indexing.
    # No arbitrary vertex sorting, repair or tolerance welding.
    if af.shape!=bf.shape:return {"status":"HOLD_FACE_COUNT","max_corner_error_m":None}
    e=0.
    for k in range(0,len(af),100000):
        p=a[af[k:k+100000]];q=b[bf[k:k+100000]]
        e=max(e,float(np.max(np.linalg.norm(p-q,axis=2))))
    return {"status":"PASS_TRANSPORT" if e<=2e-6 else "HOLD_GEOMETRY_DRIFT","max_corner_error_m":e}
def main(sex,baseline,source,out):
    out.mkdir(parents=True,exist_ok=False)
    with checked(baseline,PINS[sex]) as z:
        inv=json.loads(z.read("inventory.json"));receipt=json.loads(z.read("receipt.json"))
        for name,rec in receipt["files"].items():
            data=z.read(name);assert len(data)==rec["bytes"] and sha(data)==rec["sha256"],name
        target=scene(z.read("baseline.glb"))
        preg=scene(z.read("layers/pregnancy_reference.glb")) if sex=="female" else None
        if sex=="male":
            bp=checked(source,BP);inner=zipfile.ZipFile(io.BytesIO(bp.read("geometry.zip")));paths={Path(x).stem.upper():x for x in inner.namelist() if x.lower().endswith(".obj")}
        else:
            raw=z.read("original-female.glb");assert sha(raw)==receipt["provenance"]["source_sha256"]
            original=scene(raw)
        results=[];systems=Counter()
        for r in inv:
            id=r["id"]
            if sex=="male":
                raw=inner.read(paths[r["source_element"]]);assert sha(raw)==r["source_sha256"]
                a,af=obj(raw);a=a[:,[0,2,1]]*np.array([.001,.001,-.001]);label="; ".join(x[1] for x in r["concepts"])
            else:
                a,af=world(original,r["source_node"]);label="/".join(r["hierarchy"])
                # Record exact original named system ancestry, not keyword
                # display categorization. Ambiguous/missing ancestry is held.
                hits=[n for n in r["hierarchy"] if re.fullmatch(r"VH_F_\w+_system",n)]
                systems[hits[0] if hits else "UNCLASSIFIED_OR_OTHER"]+=1
            b,bf=world(preg if r["category"]=="pregnancy_reference" else target,id)
            m=compare(a,af,b,bf)
            results.append({"id":id,"label":label,"category":r["category"],"triangles":len(af),**m})
        expected={r["id"] for r in inv if r["category"]!="pregnancy_reference"}
        assert set(target.graph.nodes_geometry)==expected
        counts=Counter(x["status"] for x in results)
        report={"sex":sex,"source_archive_sha256":PINS[sex],"counts":dict(counts),"max_corner_error_m":max((x["max_corner_error_m"] or 0) for x in results),"source_system_ancestry":dict(systems),"scope":"Ordered triangle-coordinate transport check, 2 micrometre tolerance; not source anatomical accuracy, biological topology, completeness or rig validation","results":results}
        (out/"audit.json").write_text(json.dumps(report,indent=2))
        print("R223_TRANSPORT",json.dumps({k:v for k,v in report.items() if k!="results"}))
        assert counts.get("PASS_TRANSPORT",0)==len(inv),"one or more geometries held"
if __name__=="__main__":main(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]))
