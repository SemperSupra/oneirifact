"""R223: region-specific shape-preserving alignment of actual CT skeleton.
All matches are bone bounds centers, not annotated landmarks. Hold unanchored
regions and no fusion with HRA. Independent interleaved holdout within region.
"""
import sys,json,hashlib,zipfile,io,re
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont
CT="6ebcae2937da21450e7f536ceb92d91e96a422862e80320476e7c1d6ef08ee27"
HRA="513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542"
def checked(p,h):
    assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    return zipfile.ZipFile(p)
def fit(a,b):
    ca=a.mean(0);cb=b.mean(0);x=a-ca;y=b-cb
    U,S,V=np.linalg.svd(x.T@y);D=np.eye(3);D[2,2]=np.linalg.det(U@V)
    R=U@D@V;s=np.sum(S*np.diag(D))/np.sum(x*x)
    assert np.linalg.det(R)>.999 and s>0
    return s,R,cb-s*ca@R
def apply(v,t):
    s,R,p=t;return s*v@R+p
def serial(t):
    s,R,p=t;return {"scale":float(s),"rotation":R.tolist(),"translation_m":p.tolist()}
def reg(label):
    if not label:return None
    if "vertebra" in label or label.endswith(("sacrum","sternum")):return "axial"
    if re.search(r"(femur|tibia|fibula|patella)_[LR]$",label):return "leg_"+label[-1]
    return None
def report(rows,t):
    e=np.array([np.linalg.norm(apply(a,t)-b)*1000 for _,a,b in rows])
    return {"count":len(e),"rmse_mm":float(np.sqrt(np.mean(e*e))),"max_mm":float(e.max()),"per_bone":[{"label":n,"error_mm":float(x)} for (n,_,_),x in zip(rows,e)]}
def main(ct,hra,out):
    out.mkdir(parents=True,exist_ok=False)
    with checked(ct,CT) as z,checked(hra,HRA) as h:
        cr=json.loads(z.read("receipt.json"));hr=json.loads(h.read("inventory.json"))
        src=trimesh.load(io.BytesIO(z.read("ct-skeleton-original-frame.glb")),file_type="glb",force="scene",process=False)
        skin=trimesh.load(io.BytesIO(h.read("layers/skin.glb")),file_type="glb",force="scene",process=False).to_geometry()
        dest={r["source_node"]:np.array(r["bounds_m"]).mean(0) for r in hr}
        groups={k:[] for k in ("axial","leg_L","leg_R")}
        for r in cr["inventory"]:
            n=r["atlas_match"];g=reg(n)
            if g and n in dest:groups[g].append((n,np.array(r["bounds_m"]).mean(0),dest[n]))
        old=cr["alignment"];globaltf=(old["scale"],np.array(old["rotation_row_vectors"]),np.array(old["translation_m"]))
        # Compare global vs regional on exactly identical holdouts. Fit axial
        # first; leg region with four centers leaves one for validation.
        rows=[];transforms={}
        for key,items in groups.items():
            items.sort(key=lambda x:x[0]);assert len(items)>=4,(key,len(items))
            train=[x for i,x in enumerate(items) if i%4!=0];test=[x for i,x in enumerate(items) if i%4==0]
            a=np.array([x[1] for x in train]);b=np.array([x[2] for x in train])
            rank=int(np.linalg.matrix_rank(a-a.mean(0),tol=1e-5))
            tf=fit(a,b);metrics=report(test,tf);base=report(test,globaltf)
            admissible=rank>=2 and .85<=tf[0]<=1.15 and metrics["max_mm"]<=20 and len(test)>=2
            rows.append({"region":key,"train_count":len(train),"training_rank":rank,"global_same_holdout":base,"regional_holdout":metrics,"candidate_transform":serial(tf),"screen":"PASS_CENTRES_ONLY" if admissible else "HOLD"})
            transforms[key]=tf
        # Apply only to named matched bones, and use unchanged old global
        # transform for unanchored shapes, clearly label them as such.
        scene=trimesh.Scene();points=[];records=[]
        for r in cr["inventory"]:
            id=r["id"];mat,gn=src.graph[id];m=src.geometry[gn].copy();m.apply_transform(mat)
            key=reg(r["atlas_match"])
            if key in transforms and r["atlas_match"] in dest:tf=transforms[key];status="REGIONAL_CANDIDATE"
            else:tf=globaltf;status="UNANCHORED_GLOBAL_CONTEXT"
            before=m.vertices.copy();m.vertices=apply(before,tf)
            # All three singular values equal declared scale, det positive.
            assert np.linalg.det(tf[1])>.999
            m.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name=status,baseColorFactor=[.85,.75,.53,1] if status=="REGIONAL_CANDIDATE" else [.44,.50,.58,1],metallicFactor=0,roughnessFactor=.85))
            scene.add_geometry(m,node_name=id,geom_name=id)
            points.append((m.vertices[::max(1,len(m.vertices)//4000)],status))
            records.append({"id":id,"status":status,"region":key,"triangles":len(m.faces)})
        (out/"regional-skeleton-candidate.glb").write_bytes(scene.export(file_type="glb"))
        # Diagnostic against actual skin, same scale in both orthographic views.
        im=Image.new("RGB",(1100,860),"#17232f");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",23);sm=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
        d.text((20,13),"Regional female skeleton | held-out alignment",font=font,fill="white")
        d.text((20,48),"Gold: region-fit named bones; gray: unanchored context (not accepted)",font=sm,fill="#bccbd9")
        lo,hi=skin.bounds;scale=710/(hi[1]-lo[1])
        for i,axis in enumerate((0,2)):
            cx=275+550*i;c=(lo[axis]+hi[axis])/2
            def proj(v):return np.column_stack((cx+(v[:,axis]-c)*scale,825-(v[:,1]-lo[1])*scale))
            q=proj(skin.vertices)
            for f in skin.faces:d.polygon([tuple(q[k]) for k in f],fill="#344958")
            for v,status in points:
                for x,y in proj(v):d.point((x,y),fill="#edc686" if status=="REGIONAL_CANDIDATE" else "#8895a4")
        im.save(out/"regional-alignment.png")
        (out/"ATTRIBUTION.txt").write_bytes(z.read("ATTRIBUTION.txt")+b"\nR223: separate regional similarity registration candidates; original CT source preserved in R222. HRA v1.10 used as target.\n"+h.read("ATTRIBUTION.txt"))
        receipt={"source_sha256":[CT,HRA],"regions":rows,"inventory":records,"scope":"Bone center proxies only; no anatomical landmark, joint continuity, contact, surface containment or complete registration qualification. Unanchored bones remain old global context; no fused baseline."}
        (out/"receipt.json").write_text(json.dumps(receipt,indent=2));print("R223_REGIONAL",json.dumps(rows))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
