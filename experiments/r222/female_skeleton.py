"""Acquire sex-specific CT-derived skeletal geometry and test global alignment.
Original CT geometry is retained; no male bone substitution, no silent fusion.
"""
import sys,json,hashlib,urllib.request,urllib.parse,concurrent.futures as cf,io,zipfile,re
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont
ROOT="https://huggingface.co"
REPO="BoneHub/visible-human-3d-models"
PREFIX="visible_human_3d_models/CT/Mesh/02_Female/"
ATLAS="513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542"
def sha(b):return hashlib.sha256(b).hexdigest()
def fetch(url,cap):
    req=urllib.request.Request(url,headers={"User-Agent":"Oneirifact anatomical reference qualification"})
    with urllib.request.urlopen(req,timeout=90) as r:
        data=r.read(cap+1)
    if len(data)>cap:raise RuntimeError("download budget")
    return data
def labels(p):
    n=Path(p).stem.upper()
    n=n.replace("-","_")
    m=re.search(r"VERTEBRA_?([CTL])_?(\d+)",n)
    if m:
        k={"C":"cervical","T":"thoracic","L":"lumbar"}[m.group(1)]
        return "VH_F_"+k+"_vertebra_"+str(int(m.group(2)))
    side="L" if "LEFT" in p.upper() or n.endswith("_L") else "R" if "RIGHT" in p.upper() or n.endswith("_R") else ""
    for k in ("FEMUR","TIBIA","FIBULA","PATELLA"):
        if k in n and side:return "VH_F_"+k.lower()+"_"+side
    if n=="SACRUM":return "VH_F_sacrum"
    if n=="STERNUM":return "VH_F_sternum"
def fit(a,b):
    ca=a.mean(0);cb=b.mean(0);x=a-ca;y=b-cb
    U,S,V=np.linalg.svd(x.T@y)
    D=np.eye(3);D[2,2]=np.linalg.det(U@V)
    R=U@D@V;scale=np.sum(S*np.diag(D))/np.sum(x*x)
    return scale,R,cb-scale*ca@R
def transform(v,s,R,t):return s*v@R+t
def render(out,skin,meshes,fitmeshes):
    im=Image.new("RGB",(1100,860),"#17232f");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",24);sm=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
    d.text((18,15),"Female CT-derived skeleton | registration diagnostic",font=font,fill="white")
    d.text((18,49),"Left: registered bone candidate over HRA body  |  Right: side projection",font=sm,fill="#bac9d7")
    lo,hi=skin.bounds;h=hi[1]-lo[1];scale=710/h
    for i,axis in enumerate((0,2)):
        center=(lo[axis]+hi[axis])/2;cx=275+i*550
        def project(p):return np.column_stack((cx+(p[:,axis]-center)*scale,820-(p[:,1]-lo[1])*scale))
        q=project(skin.vertices)
        for f in skin.faces:d.polygon([tuple(q[j]) for j in f],fill="#3a4c5a")
        # Surface vertices from actual CT triangles; no generated anatomical shape.
        for k,m in fitmeshes.items():
            q=project(m.vertices[::max(1,len(m.vertices)//10000)])
            for x,y in q:d.point((x,y),fill="#e1d2af")
    im.save(out/"skeletal-registration.png")
def main(atlas,out):
    out.mkdir(parents=True,exist_ok=False)
    assert sha(atlas.read_bytes())==ATLAS
    with zipfile.ZipFile(atlas) as z:
        inventory=json.loads(z.read("inventory.json"))
        skin=trimesh.load(io.BytesIO(z.read("layers/skin.glb")),file_type="glb",force="scene",process=False).to_geometry()
    dest={r["source_node"]:np.array(r["bounds_m"]).mean(0) for r in inventory}
    info=json.loads(fetch(ROOT+"/api/datasets/"+REPO,8<<20))
    rev=info["sha"];assert re.fullmatch(r"[0-9a-f]{40}",rev)
    files=sorted(x["rfilename"] for x in info["siblings"] if x["rfilename"].startswith(PREFIX) and x["rfilename"].lower().endswith(".stl"))
    assert len(files)==143, f"expected 143 female meshes, got {len(files)}"
    (out/"source-dataset.json").write_text(json.dumps({"revision":rev,"paths":files,"license":info.get("cardData",{}).get("license")},indent=2))
    assert info.get("cardData",{}).get("license")=="cc-by-4.0"
    readme=fetch(ROOT+"/datasets/"+REPO+"/resolve/"+rev+"/README.md",2<<20);(out/"source-README.md").write_bytes(readme)
    original=out/"source-stl";original.mkdir()
    def get(path):
        raw=fetch(ROOT+"/datasets/"+REPO+"/resolve/"+rev+"/"+urllib.parse.quote(path,safe="/"),48<<20)
        rel=Path(path).relative_to(PREFIX);assert ".." not in rel.parts
        dst=original/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
        return path,sha(raw),len(raw)
    with cf.ThreadPoolExecutor(max_workers=4) as ex:rows=list(ex.map(get,files))
    assert sum(x[2] for x in rows)<1000<<20,"total budget"
    scene=trimesh.Scene();meshes={};records=[];matches=[]
    for i,(path,digest,nbytes) in enumerate(rows):
        p=original/Path(path).relative_to(PREFIX);m=trimesh.load(p,file_type="stl",force="mesh",process=False);assert len(m.faces)>0 and np.isfinite(m.vertices).all()
        # STL units presumed mm from CT dataset; validate measured extent.
        m.vertices*=.001;m.merge_vertices()
        id="bone_"+str(i).zfill(3)+"_"+Path(path).stem
        meshes[id]=m;scene.add_geometry(m,node_name=id,geom_name=id)
        label=labels(path)
        rec={"id":id,"path":path,"sha256":digest,"triangles":len(m.faces),"bounds_m":m.bounds.tolist(),"atlas_match":label}
        records.append(rec)
        if label in dest:matches.append((label,m.bounds.mean(0),dest[label]))
    assert .8<max(scene.extents)<2.5,"CT scale unresolved"
    (out/"ct-skeleton-original-frame.glb").write_bytes(scene.export(file_type="glb"))
    # Hold-out bone centers, not detailed anatomical landmark truth.
    matches.sort(key=lambda x:x[0]);assert len(matches)>=12,f"too few correspondences {len(matches)}"
    train=[x for i,x in enumerate(matches) if i%3!=0];test=[x for i,x in enumerate(matches) if i%3==0]
    a=np.array([x[1] for x in train]);b=np.array([x[2] for x in train]);s,R,t=fit(a,b)
    assert np.linalg.det(R)>.999
    err=lambda rows:np.linalg.norm(transform(np.array([x[1] for x in rows]),s,R,t)-np.array([x[2] for x in rows]),axis=1)*1000
    trainerr=err(train);testerr=err(test)
    # Rejection is expected if posture or anatomy differ. Never fuse.
    accepted=.85<=s<=1.15 and float(testerr.max())<=20
    fitted={};candidate=trimesh.Scene()
    for id,m in meshes.items():
        q=m.copy();q.vertices=transform(q.vertices,s,R,t);fitted[id]=q;candidate.add_geometry(q,node_name=id,geom_name=id)
    (out/"ct-skeleton-registration-candidate.glb").write_bytes(candidate.export(file_type="glb"))
    render(out,skin,meshes,fitted)
    (out/"ATTRIBUTION.txt").write_text("BoneHub, Visible Human Full-Skeleton 3D Bone Models, CC BY 4.0, https://huggingface.co/datasets/BoneHub/visible-human-3d-models DOI 10.57967/hf/10464. Original STL retained. Underlying Visible Human Project; Andreassen et al. Sci Data 10,34 (2023), DOI 10.1038/s41597-022-01905-2. Changes: STL mm to m, exact vertex welding, GLB transport and separate similarity registration candidate against HRA female v1.10. No clinical claim.\n")
    report={"source_revision":rev,"meshes":len(records),"triangles":sum(r["triangles"] for r in records),"source_bytes":sum(x[2] for x in rows),"source_frame":"original CT axes, converted mm to m; not glTF stage-aligned","alignment":{"scale":float(s),"rotation_row_vectors":R.tolist(),"translation_m":t.tolist(),"training_centres":len(train),"test_centres":len(test),"training_rmse_mm":float(np.sqrt(np.mean(trainerr**2))),"test_rmse_mm":float(np.sqrt(np.mean(testerr**2))),"test_max_mm":float(testerr.max()),"test_details":[{"name":x[0],"error_mm":float(e)} for x,e in zip(test,testerr)],"screen":"PASS_CENTRE_SCREEN_ONLY" if accepted else "HOLD_REGISTRATION"},"status":"SEPARATE_DONOR_NOT_FUSED","scope":"Actual CT skeletal models, not all 206 individual bones; shape/attachment/containment and anatomy not admitted. No inferred female organs.","inventory":records}
    (out/"receipt.json").write_text(json.dumps(report,indent=2));print("R222_SKELETON",json.dumps({k:v for k,v in report.items() if k!="inventory"}))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
