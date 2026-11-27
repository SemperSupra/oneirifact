"""Fit editable section-loft sources; mesh generation exclusively via shared Go
primitive. Reference-derived shape proposals, no full organ fit or native adapter claim.
"""
import hashlib,io,json,sys,zipfile,subprocess
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw,ImageFont
BP_PIN="b13e23f595be27237ce69246484fd781553181d91e3ab7bda042bafb9aedd133"
BP_INNER="ac7d9ab0b3d75b4c75445f0f39e3782f309bbb321d2191f449773107ae504793"
MALE={"stomach":"FJ2564","esophagus":"FJ2563","trachea":"FJ2541","left_adrenal":"FJ3129","right_adrenal":"FJ3130","pituitary":"FJ1796","left_thymus_lobe":"FJ3150","right_thymus_lobe":"FJ3151","left_ureter":"FJ3144","right_ureter":"FJ3146","urethra":"FJ3148","tongue":"FJ2761","diaphragm":"FJ3131","left_testis":"FJ3138","right_testis":"FJ3142","left_epididymis":"FJ3136","right_epididymis":"FJ3141","left_seminal_vesicle":"FJ3137","right_seminal_vesicle":"FJ3143","corpus_cavernosum":"FJ3132","corpus_spongiosum":"FJ3133","glans":"FJ3134"}
FEMALE={"vagina":("VH_F_Vagina.glb","29cbb27146381494f0a0d618b43b3c2319b95f72"),"left_ureter":("VH_F_Ureter_L.glb","6d1b5084eef08232a519e53cd244cf8f0f030483"),"right_ureter":("VH_F_Ureter_R.glb","e7cf8de3a1afbe4dc44bb736922a38079278398f")}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def blob(raw):return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def load(raw,fmt):
    return trimesh.load(io.BytesIO(raw),file_type=fmt,force="scene",process=False).to_geometry()
def sample(m,n,seed):
    t=m.vertices[m.faces];a=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1);rng=np.random.default_rng(seed)
    t=t[rng.choice(len(t),n,p=a/a.sum())];u=rng.random((n,2));u[u.sum(1)>1]=1-u[u.sum(1)>1]
    return t[:,0]+u[:,0,None]*(t[:,1]-t[:,0])+u[:,1,None]*(t[:,2]-t[:,0])
def measure(ref,cand):
    a=cKDTree(ref).query(cand)[0];b=cKDTree(cand).query(ref)[0]
    return {"rmse_mm":float(np.sqrt((np.mean(a*a)+np.mean(b*b))/2)*1000),"p95_mm":float(max(np.quantile(a,.95),np.quantile(b,.95))) *1000}
def fit(name,points,n):
    c=points.mean(0);_,_,axes=np.linalg.svd(points-c,full_matrices=False)
    frame=axes[[1,2,0]].copy()
    if np.linalg.det(frame)<0:frame[1]*=-1
    q=(points-c)@frame.T;lo,hi=q[:,2].min(),q[:,2].max();levels=np.linspace(lo,hi,n);span=hi-lo
    sec=[]
    for h in levels:
        # Local cross-section envelope inferred from training samples only.
        select=np.argsort(abs(q[:,2]-h))[:max(45,len(q)//(n*3))]
        p=q[select];a,b=np.quantile(p[:,:2],[.025,.975],axis=0)
        sec.append({"z_m":float(h),"center_m":((a+b)/2).tolist(),"radii_m":np.maximum((b-a)/2,1e-5).tolist()})
    return {"schema":"oneirifact.section_loft/v0.1","name":name,"origin_m":c.tolist(),"frame_columns":frame.tolist(),"sides":48,"sections":sec}
def render_pair(ref,cand,axis,n=230):
    # Shared true scale and center. Orthographic depth-sorted surface triangles;
    # an independent diagnostic, not a photorealistic image or a topology proof.
    v=np.concatenate((ref.vertices,cand.vertices));center=(v.min(0)+v.max(0))/2;scale=(n-18)/max(np.ptp(v,axis=0))
    a=[i for i in range(3) if i!=axis];renders=[];masks=[]
    for mesh,col in ((ref,(201,161,120)),(cand,(103,199,167))):
        q=mesh.vertices-center;xy=np.column_stack((n/2+q[:,a[0]]*scale,n/2-q[:,a[1]]*scale));t=mesh.vertices[mesh.faces];normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);shade=.4+.6*np.abs(normal[:,axis])/(np.linalg.norm(normal,axis=1)+1e-30)
        im=Image.new("RGB",(n,n),"#1c2a35");d=ImageDraw.Draw(im);mask=Image.new("1",(n,n));md=ImageDraw.Draw(mask)
        for i in np.argsort(q[mesh.faces,axis].mean(1)):
            poly=[tuple(x) for x in xy[mesh.faces[i]]];d.polygon(poly,fill=tuple(int(x*shade[i]) for x in col));md.polygon(poly,fill=1)
        renders.append(im);masks.append(np.array(mask))
    union=(masks[0]|masks[1]).sum();iou=float((masks[0]&masks[1]).sum()/max(1,union))
    return renders,iou
def process(name,m,identity,go,out):
    d=out/name;d.mkdir();m.export(d/"reference.obj",file_type="obj",include_color=False,include_texture=False)
    train=sample(m,14000,221);val=sample(m,16000,222);test=sample(m,24000,223)
    rows=[]
    for n in (6,12,24):
        spec=fit(name,train,n);p=d/("loft-"+str(n)+".json");p.write_text(json.dumps(spec,indent=2));q=d/("loft-"+str(n)+".obj")
        rev=subprocess.check_output([str(go),str(p),str(q)],text=True).strip();mesh=load(q.read_bytes(),"obj");mesh.merge_vertices()
        score=measure(val,sample(mesh,16000,224))
        rows.append((score["rmse_mm"],n,spec,p,q,mesh,rev,score))
    _,n,spec,p,q,cand,rev,score=min(rows,key=lambda x:x[0])
    (d/"candidate.oneirifact.json").write_bytes(p.read_bytes());(d/"candidate.obj").write_bytes(q.read_bytes())
    held=measure(test,sample(cand,24000,225))
    images=[];ious=[]
    for axis in (1,0,2):
        pair,iou=render_pair(m,cand,axis);images+=pair;ious.append(iou)
    im=Image.new("RGB",(6*230,290),"#1c2a35");draw=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",18)
    draw.text((8,6),name.replace("_"," ")+" | original reference (tan) and shared Go section-loft (green)",font=font,fill="white")
    for j,im2 in enumerate(images):im.paste(im2,(j*230,36))
    draw.text((8,270),f"Held-out sampled RMSE {held['rmse_mm']:.2f} mm | silhouette IoU "+"/".join(f"{a:.2f}" for a in ious)+" | reference-frame, not registered",font=font,fill="white")
    im.save(d/"comparison.png")
    scale=float(np.max(m.extents))*1000
    # This is a coarse visual screen only. Explicitly hold every clinical,
    # hollow-organ and full anatomical-placement gate.
    visual=held["rmse_mm"]<=.04*scale and min(ious)>=.85 and cand.is_watertight and cand.volume>0
    receipt={"name":name,"reference":identity,"reference_bounds_m":m.bounds.tolist(),"candidate_bounds_m":cand.bounds.tolist(),"reference_triangles":len(m.faces),"candidate_triangles":len(cand.faces),"reference_watertight":bool(m.is_watertight),"candidate_watertight":bool(cand.is_watertight),"candidate_signed_volume_m3":float(cand.volume),"chosen_sections":n,"source_revision":rev,"validation":score,"heldout":held,"silhouette_iou_front_side_axial":ious,"visual_screen":"COARSE_EXTERIOR_PASS" if visual else "HOLD_SHAPE","anatomical_admission":"HELD","scope":"No lumen, branches, tissue layers, native Foundry adapter, placement or clinical qualification"}
    (d/"receipt.json").write_text(json.dumps(receipt,indent=2));return receipt
def main(lane,inp,go,out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    if lane.startswith("bp"):
        raw=(inp/"atlas.zip").read_bytes();assert sha(raw)==BP_PIN
        with zipfile.ZipFile(io.BytesIO(raw)) as outer:
            inner=outer.read("geometry.zip");assert sha(inner)==BP_INNER;inv={x["id"]:x for x in json.loads(outer.read("inventory.json"))}
            for f in ("ATTRIBUTION.txt","LICENSE-source.html","LICENSE-update.html"):(out/f).write_bytes(outer.read(f))
            with zipfile.ZipFile(io.BytesIO(inner)) as z:
                paths={Path(n).stem.upper():n for n in z.namelist() if n.endswith(".obj")}
                for i,(name,id) in enumerate(MALE.items()):
                    if (lane=="bp-general" and i>=13) or (lane=="bp-reproductive" and i<13):continue
                    raw=z.read(paths[id]);rec=inv[id];assert sha(raw)==rec["sha256"]
                    m=load(raw,"obj");m.vertices*=.001
                    row=process(name,m,{"donor":"BodyParts3D 4.0","element":id,"mapped_concepts":rec["mapped_concepts"],"source_sha256":sha(raw),"units":"mm Z-up to metres Z-up"},go,out)
                    (out/name/"original.obj").write_bytes(raw);rows.append(row)
    else:
        for name,(filename,pin) in FEMALE.items():
            raw=(inp/filename).read_bytes();assert blob(raw)==pin
            m=load(raw,"glb");m.apply_transform(np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]],float))
            rows.append(process(name,m,{"donor":"HRA v1.2 female","file":filename,"git_blob":pin,"units":"metre Y-up to metre Z-up"},go,out));(out/name/"original.glb").write_bytes(raw)
        (out/"LICENSE").write_bytes((inp/"LICENSE").read_bytes())
        (out/"ATTRIBUTION.txt").write_text("Human Reference Atlas / HuBMAP, CCF 3D Reference Object Library, CC BY 4.0. https://github.com/hubmapconsortium/ccf-3d-reference-object-library/tree/f1a3a63f110e27ff0736047d52d04dba5d3087f9. Derived editable section-loft geometry and educational previews; original assets preserved.\n")
    (out/"receipt.json").write_text(json.dumps({"lane":lane,"results":rows,"scope":"shared production-intended loft kernel, exact reference geometry; no native integrated Foundry execution"},indent=2))
    print("R221_LOFT",json.dumps([{"name":x["name"],"rmse":x["heldout"]["rmse_mm"],"iou":x["silhouette_iou_front_side_axial"],"screen":x["visual_screen"]} for x in rows]))
if __name__=="__main__":main(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]).resolve(),Path(sys.argv[4]))
