"""Build the bounded, public, read-only anatomy viewer from admitted reference artifacts.
No native product or patient-specific anatomy claim. Never extract arbitrary ZIP paths.
"""
import hashlib,io,json,re,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
ROOT=Path(__file__).resolve().parents[1]
PINS={
 "male":"18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9",
 "female":"513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542",
 "regional":"9ca44d974bd6673d50be866ab12e63557a1d170641d55e0e49f19b72b1a06187",
 "pineal":"295d65c564c798e6f07ef63ee8e60449920ed62b8e6b42a300ad16c6631ec1ce",
 "identity":"320928150b0c0590713287d3841dae897651f07f9d1de303b61885e9839d89eb",
 "registration":"de63599d6239bfaef568bb26a5259bf85b8ec2d66c6330025d81b6494eb4b484"}
LABELS={"skin":"Exterior / skin","skeletal":"Skeleton","muscular":"Muscles","connective":"Connective tissue","vascular":"Blood vessels","neural":"Nervous system","lymphatic":"Lymphatic system","reproductive":"Reproductive anatomy","respiratory":"Respiratory system","digestive":"Digestive system","urinary":"Urinary system","endocrine":"Endocrine system","sensory":"Sensory organs","cardiac":"Heart","other":"Other / unclassified","pregnancy_reference":"Pregnancy reference (separate)"}
def sha(b):return hashlib.sha256(b).hexdigest()
def checked(inp,k):
    p=inp/(k+".zip")
    with p.open("rb") as f:assert hashlib.file_digest(f,"sha256").hexdigest()==PINS[k],k
    return zipfile.ZipFile(p)
def read(z,n,limit=512<<20):
    info=z.getinfo(n)
    assert info.file_size<=limit,n
    return z.read(info)
def write(out,name,b):
    assert re.fullmatch(r"[a-z0-9-]+[.][a-z0-9]+",name),name
    (out/name).write_bytes(b)
    return "data/"+name
def glb(raw):
    assert raw[:4]==b"glTF"
    return trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
def scene_counts(sc):
    return sum(len(sc.geometry[sc.graph[n][1]].faces) for n in sc.graph.nodes_geometry)
def compact(raw,cap):
    s=glb(raw);nodes=sorted(s.graph.nodes_geometry);assert nodes
    original=scene_counts(s)
    if original<=cap:return raw,original,original,len(nodes)
    out=trimesh.Scene()
    # Keep every source node. Distribute a small minimum to small features;
    # remaining budget is proportional to source triangle count.
    counts={n:len(s.geometry[s.graph[n][1]].faces) for n in nodes}
    floors={n:min(v,32) for n,v in counts.items()};remaining=cap-sum(floors.values())
    assert remaining>0
    excess=sum(counts[n]-floors[n] for n in nodes)
    for n in nodes:
        tf,g=s.graph[n];m=s.geometry[g].copy();m.apply_transform(tf)
        target=min(counts[n],floors[n]+int(remaining*(counts[n]-floors[n])/excess))
        if target<len(m.faces):
            original_mesh=m
            try:
                q=m.simplify_quadric_decimation(face_count=max(4,target))
                if len(q.faces)>0 and np.isfinite(q.vertices).all():
                    q.visual=trimesh.visual.TextureVisuals(material=original_mesh.visual.material)
                    m=q
            except (ValueError,RuntimeError,IndexError):pass
        assert len(m.faces)>0 and np.isfinite(m.vertices).all(),n
        out.add_geometry(m,node_name=n,geom_name=n)
    result=out.export(file_type="glb");verify=glb(result)
    assert set(verify.graph.nodes_geometry)==set(nodes)
    display=scene_counts(verify)
    assert display<=cap*1.10,(display,cap)
    return result,original,display,len(nodes)
def model(out,key,label,raw,cap=90000):
    data,source,display,nodes=compact(raw,cap)
    return {"id":key,"label":label,"file":write(out,key+".glb",data),"bytes":len(data),"sha256":sha(data),"source_triangles":source,"display_triangles":display,"nodes":nodes,"fidelity":"Reduced browser display geometry" if source!=display else "Original reference geometry"}
def base(inp,out,sex):
    with checked(inp,sex) as z:
        receipt=json.loads(read(z,"receipt.json"));inv=json.loads(read(z,"inventory.json"))
        assert receipt["sex"]==sex and len(inv)==receipt["named_meshes"]
        assets=[]
        for category,label in LABELS.items():
            name="layers/"+category+".glb"
            if name not in receipt["files"]:continue
            raw=read(z,name);assert sha(raw)==receipt["files"][name]["sha256"]
            assets.append(model(out,sex+"-"+category.replace("_","-"),label,raw))
        assert assets
        rows=[]
        for r in inv:
            names=[v[1] for v in r["concepts"]] if sex=="male" else [r["source_node"]]
            rows.append({"id":r["id"],"names":names,"category":r["category"],"layer":sex+"-"+r["category"].replace("_","-"),"triangles":r["triangles"]})
        for name in ("baseline-preview.png","ATTRIBUTION.txt","inventory.json"):
            assert sha(read(z,name))==receipt["files"][name]["sha256"]
        return {"id":sex,"label":sex.title()+" reference","source":receipt["provenance"]["source"],"scope":"Reference donor; incomplete anatomy, not articulated or native Oneirifact output. Display grouping is heuristic.","preview":write(out,sex+"-preview.png",read(z,"baseline-preview.png")),"attribution":write(out,sex+"-attribution.txt",read(z,"ATTRIBUTION.txt")),"inventory":write(out,sex+"-inventory.json",json.dumps(rows,separators=(",",":")).encode()),"layers":assets,"source_archive_sha256":PINS[sex]}
def regional(inp,out):
    with checked(inp,"regional") as z:
        raw=read(z,"regional-skeleton-candidate.glb")
        return {"id":"ct","label":"Female CT registration candidate","source":"BoneHub female CT, R223 separate candidate","scope":"Unfused candidate. Unanchored limbs retain earlier global context and may be visibly misaligned. Not accepted anatomical registration.","preview":write(out,"ct-preview.png",read(z,"regional-alignment.png")),"attribution":write(out,"ct-attribution.txt",read(z,"ATTRIBUTION.txt")),"layers":[model(out,"ct-regional","Regional candidate",raw,140000)],"source_archive_sha256":PINS["regional"]}
def pineal(inp,out):
    with checked(inp,"pineal") as z:
        rr=json.loads(read(z,"receipt.json"));layers=[]
        for r in rr["results"]:
            sex=r["sex"];raw=read(z,sex+"-pineal-reference.glb");assert sha(raw)==r["sha256"]
            layers.append(model(out,"pineal-"+sex,sex.title()+" donor",raw))
            write(out,"pineal-"+sex+"-attribution.txt",read(z,sex+"-attribution.txt"))
        return {"id":"pineal","label":"Pineal recovery comparison","source":"R225 recovered male and female atlas mesh subregions","scope":"Exact donor subset; different axes and reference provenance. Not proof of sex-specific morphology.","preview":write(out,"pineal-preview.png",read(z,"pineal-comparison.png")),"attribution":"data/pineal-male-attribution.txt","additional_attribution":"data/pineal-female-attribution.txt","layers":layers,"source_archive_sha256":PINS["pineal"]}
def main(inp,out):
    out.mkdir(parents=True,exist_ok=False)
    datasets=[base(inp,out,s) for s in ("male","female")]+[regional(inp,out),pineal(inp,out)]
    with checked(inp,"registration") as z:
        reg=json.loads(read(z,"registration.json"))
        assert len(reg["folds"])==35
        regpath=write(out,"registration.json",read(z,"registration.json"))
        plot=write(out,"registration-review.svg",read(z,"registration-review.svg"))
    with checked(inp,"identity") as z:
        ident=json.loads(read(z,"identity.json"));assert len(ident["records"])==476
        identity=write(out,"identity.json",read(z,"identity.json"))
    catalog={"schema":"oneirifact.reference-viewer/v1","datasets":datasets,"evidence":{"registration":regpath,"registration_plot":plot,"identity":identity},"source_pins":PINS,"limitations":"Mobile display meshes may be decimated. Original donor and native editable source are separate. No clinical or complete anatomy claim."}
    (out/"catalog.json").write_text(json.dumps(catalog,indent=2))
    total=sum(p.stat().st_size for p in out.iterdir());assert total<=78<<20,total
    print("ANATOMY_VIEWER_BUILD",json.dumps({"bytes":total,"datasets":len(datasets),"models":sum(len(d["layers"]) for d in datasets),"triangles":sum(m["display_triangles"] for d in datasets for m in d["layers"])}))
if __name__=="__main__":main(Path(sys.argv[1]),ROOT/"site/anatomy/data")
