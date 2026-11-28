"""Recover missing historical HRA pelvic subtrees, separate from current reference.
Verify shared skeletal frame using actual triangles, not merely center proxies.
No automatic fusion, no native or clinical claim.
"""
import hashlib,io,json,sys,zipfile,re
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont
HRA="513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542"
ROOTS={"VH_F_ischium","VH_F_pubis"}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(raw):return trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
def ancestors(scene,n):
    path=[n];parents=scene.graph.transforms.parents
    while n in parents:
        n=parents[n]
        if n in path:break
        path.append(n)
    return path
def mesh(scene,n):
    tf,g=scene.graph[n];q=scene.geometry[g].copy();q.apply_transform(tf)
    assert len(q.faces) and np.isfinite(q.vertices).all()
    return q
def canonical_triangles(m):
    # Sort the vertices within each triangle and the triangles themselves.
    # Micrometre rounding is only for order-insensitive correspondence,
    # independently check coordinate differences for same-topology cases.
    t=m.vertices[m.faces]
    order=np.lexsort((t[:,:,2],t[:,:,1],t[:,:,0]),axis=1)
    q=np.take_along_axis(t,order[:,:,None],axis=1).reshape(-1,9)
    return q[np.lexsort(tuple(q[:,i] for i in reversed(range(9))))]
def skeletal(n,path):
    return any(x in path for x in ("VH_F_skeletal_system","VH_F_lower_limb")) and bool(re.search(r"vertebra|sacrum|sternum|femur|tibia|fibula|patella|ilium|ischium|pubis",n,re.I)) and not re.search(r"cartilage|ligament|meniscus|disk",n,re.I)
def main(old,baseline,out):
    out.mkdir(parents=True,exist_ok=False)
    with baseline.open("rb") as f:assert hashlib.file_digest(f,"sha256").hexdigest()==HRA
    with zipfile.ZipFile(baseline) as z:
        rec=json.loads(z.read("receipt.json"))
        current=z.read("original-female.glb");assert sha(current)==rec["files"]["original-female.glb"]["sha256"]
        attrib=z.read("ATTRIBUTION.txt")
    raw=old.read_bytes();assert 0<len(raw)<512<<20 and raw[:4]==b"glTF"
    a,b=load(raw),load(current)
    names_a=set(a.graph.nodes_geometry);names_b=set(b.graph.nodes_geometry)
    selected=sorted(n for n in names_a if ROOTS.intersection(ancestors(a,n)))
    assert selected,"historical pelvic subtree not found"
    anchors=sorted(n for n in names_a&names_b if skeletal(n,ancestors(a,n)) and skeletal(n,ancestors(b,n)))
    records=[]
    for n in anchors:
        x,y=mesh(a,n),mesh(b,n)
        bound=float(np.max(np.abs(x.bounds-y.bounds)))
        err=None
        if x.faces.shape==y.faces.shape:
            q,r=canonical_triangles(x),canonical_triangles(y)
            err=float(np.max(np.abs(q-r)))
        records.append({"node":n,"old_triangles":len(x.faces),"current_triangles":len(y.faces),"bounds_max_m":bound,"canonical_triangle_coordinate_max_m":err,"exact_screen":err is not None and err<=2e-6})
    # Conservative: enough genuinely shared geometry must agree, and any
    # failed shared comparison is retained as a hold, never silently removed.
    passed=sum(r["exact_screen"] for r in records)
    frame="PASS_SHARED_TRIANGLE_FRAME_ONLY" if passed>=12 and passed==len(records) else "HOLD_SHARED_FRAME"
    result=trimesh.Scene();recovered=[];models=[]
    for n in selected:
        q=mesh(a,n);result.add_geometry(q,node_name=n,geom_name=n)
        models.append(q)
        recovered.append({"node":n,"ancestors":ancestors(a,n),"triangles":len(q.faces),"bounds_m":q.bounds.tolist(),"present_in_v1_10_by_exact_node":n in names_b})
    glb=result.export(file_type="glb");(out/"historical-pelvis-reference.glb").write_bytes(glb)
    check=load(glb);assert set(check.graph.nodes_geometry)==set(selected)
    drift=0.
    for n in selected:
        x,y=mesh(a,n),mesh(check,n);assert x.faces.shape==y.faces.shape
        drift=max(drift,float(np.max(np.abs(x.vertices[x.faces]-y.vertices[y.faces]))))
    assert drift<=2e-6
    # Actual geometry image, not schematic. Fixed orthographic anterior view.
    im=Image.new("RGB",(1000,700),"#17232f");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",22)
    d.text((20,20),"HRA historical female pelvic reference subtrees",font=font,fill="white")
    d.text((20,55),frame,font=font,fill="#d0c5a5")
    allv=np.concatenate([q.vertices for q in models]);lo,hi=allv.min(0),allv.max(0);scale=500/max(hi[0]-lo[0],hi[1]-lo[1],.001);c=(lo+hi)/2
    for j,q in enumerate(models):
        v=q.vertices;idx=np.argsort(v[:,2]);color=("#ddc798","#82b6cd","#d7a7b1","#9fc7a0")[j%4]
        for x,y,z in v[idx[::max(1,len(idx)//12000)]]:
            d.point((500+(x-c[0])*scale,395-(y-c[1])*scale),fill=color)
    im.save(out/"pelvis-preview.png")
    (out/"ATTRIBUTION.txt").write_bytes(attrib+b"\nHistorical 3D Reference Organ Set for Female v1.5, HuBMAP Human Reference Atlas, CC BY 4.0; https://humanatlas.io/3d-reference-library ; https://cdn.humanatlas.io/digital-objects/ref-organ/united-female/v1.5/assets/3d-vh-f-united.glb . Adaptation: original world-space pelvic subset; no anatomical fitting, source retained separately.\n")
    report={"historical_source_sha256":sha(raw),"current_source_sha256":sha(current),"current_archive_sha256":HRA,"frame_screen":frame,"shared_anchor_count":len(records),"shared_exact_pass_count":passed,"shared_anchors":records,"recovered":recovered,"subset_sha256":sha(glb),"transport_max_coordinate_error_m":drift,"status":"SEPARATE_REFERENCE_NOT_FUSED","limitations":"Historical subset, not admission of complete anatomical or sex-specific tissue geometry; common atlas mesh frame is not independent clinical validation."}
    (out/"receipt.json").write_text(json.dumps(report,indent=2))
    print("R228_PELVIS",json.dumps({k:v for k,v in report.items() if k!="shared_anchors"}),flush=True)
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
