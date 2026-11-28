"""Cross-donor bilateral pelvis rigid surface screen with fixed withheld patches.

Source: female CT HIP_LEFT/RIGHT, female HRA compact ilium + historical
ischium/pubis. These represent different donor references. No mesh fusion,
deformation, individual subject reconstruction or anatomical admission.
"""
import hashlib,io,json,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw,ImageFont

CT="6ebcae2937da21450e7f536ceb92d91e96a422862e80320476e7c1d6ef08ee27"
HRA="513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542"
PELVIS="f4d462ab23fb4a11700c39785e2ace9e8d09f4bac424ce25451f291e64194f09"
REG="de63599d6239bfaef568bb26a5259bf85b8ec2d66c6330025d81b6494eb4b484"
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def checked(p,digest):
    with p.open("rb") as f:require(hashlib.file_digest(f,"sha256").hexdigest()==digest,"archive digest")
    return zipfile.ZipFile(p)
def scene(raw):return trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
def world(s,n):
    tf,g=s.graph[n];m=s.geometry[g].copy();m.apply_transform(tf)
    require(len(m.faces)>0 and np.isfinite(m.vertices).all(),"invalid mesh")
    return m
def fit(a,b):
    x=a-a.mean(0);y=b-b.mean(0)
    u,s,v=np.linalg.svd(x.T@y);d=np.eye(3);d[-1,-1]=np.linalg.det(u@v);r=u@d@v
    require(np.linalg.det(r)>.999999 and np.allclose(r@r.T,np.eye(3),atol=1e-9),"nonrigid transform")
    return r,b.mean(0)-a.mean(0)@r
def apply(a,tf):return a@tf[0]+tf[1]
def compose(a,b):return a[0]@b[0],a[1]@b[0]+b[1]
def tf_json(tf):return {"rotation_row_vectors":tf[0].tolist(),"translation_m":tf[1].tolist(),"scale":1.}
def partition(tri,seed):
    # Hold back complete triangle IDs, not a random split of points sampled
    # from the same face. Partition in initial common Y-up stage, separately
    # per side/donor; no reclassification after optimization.
    y=tri.mean(1)[:,1]
    cut=float(np.quantile(y,.35));train=np.flatnonzero(y>=cut);test=np.flatnonzero(y<cut)
    require(len(train)>100 and len(test)>100 and not np.intersect1d(train,test).size,"empty or leaking spatial holdout")
    require(len(train)+len(test)==len(tri),"lost faces")
    def sample(ids,count,s):
        t=tri[ids];areas=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)
        require(np.isfinite(areas).all() and areas.sum()>0,"surface area")
        rng=np.random.default_rng(s)
        q=t[rng.choice(len(t),count,p=areas/areas.sum())]
        w=rng.random((count,2));w[w.sum(1)>1]=1-w[w.sum(1)>1]
        return q[:,0]+w[:,0,None]*(q[:,1]-q[:,0])+w[:,1,None]*(q[:,2]-q[:,0])
    return sample(train,5000,seed),sample(test,5000,seed+1),{"split_y_m":cut,"train_faces":len(train),"heldout_faces":len(test),"train_ids_sha256":sha(train.astype("<i8").tobytes()),"heldout_ids_sha256":sha(test.astype("<i8").tobytes()),"sample_points_each":5000}
def metric(a,b,tf):
    aa=apply(a,tf);ab=cKDTree(b).query(aa,k=1)[0];ba=cKDTree(aa).query(b,k=1)[0]
    both=np.concatenate([ab,ba])*1000
    return {"symmetric_sample_rmse_mm":float(np.sqrt(np.mean(both**2))),"p95_mm":float(np.quantile(both,.95)),"max_mm":float(both.max()),"source_to_target_mean_mm":float(ab.mean()*1000),"target_to_source_mean_mm":float(ba.mean()*1000)}
def icp(pairs):
    tf=(np.eye(3),np.zeros(3));history=[]
    # Per-side correspondence prevents left/right swapping. Same common
    # rigid transform for both hips preserves bilateral arrangement.
    for _ in range(35):
        aa=[];bb=[]
        for a,b in pairs:
            q=apply(a,tf);dist,idx=cKDTree(b).query(q);rev,jdx=cKDTree(q).query(b)
            take=dist<=np.quantile(dist,.8);rtake=rev<=np.quantile(rev,.8)
            aa.extend((q[take],q[jdx[rtake]]));bb.extend((b[idx[take]],b[rtake]))
        a,b=np.concatenate(aa),np.concatenate(bb);step=fit(a,b);tf=compose(tf,step)
        residual=float(np.sqrt(np.mean(np.sum((apply(a,step)-b)**2,axis=1))))
        history.append(residual*1000)
        if len(history)>1 and abs(history[-1]-history[-2])<.005:break
    return tf,history
def selftest():
    rng=np.random.default_rng(42);a=rng.normal(size=(50,3))
    ang=.17;r=np.array([[np.cos(ang),-np.sin(ang),0],[np.sin(ang),np.cos(ang),0],[0,0,1]])
    b=a@r+np.array([.3,.2,-.1]);require(np.max(abs(apply(a,fit(a,b))-b))<1e-10,"known rigid transform")
    c=b.copy();c[:,0]*=-1;tf=fit(a,c);require(np.linalg.det(tf[0])>.999 and np.max(abs(apply(a,tf)-c))>.1,"reflection rejected")
def material(name,col):
    return trimesh.visual.material.PBRMaterial(name=name,baseColorFactor=col,metallicFactor=0,roughnessFactor=.88)
def model(out,name,parts,ctf):
    sc=trimesh.Scene();expected={}
    for n,m,isct in parts:
        q=m.copy()
        if isct:q.vertices=apply(q.vertices,ctf)
        q.visual=trimesh.visual.TextureVisuals(material=material("CT" if isct else "HRA",[.22,.65,.83,.65] if isct else [.8,.68,.45,1]))
        sc.add_geometry(q,node_name=n,geom_name=n);expected[n]=q
    raw=sc.export(file_type="glb");(out/name).write_bytes(raw)
    reread=scene(raw);require(set(reread.graph.nodes_geometry)==set(expected),"node transport")
    err=0.
    for n,m in expected.items():
        q=world(reread,n);require(q.faces.shape==m.faces.shape,"face transport")
        err=max(err,float(np.max(abs(q.vertices[q.faces]-m.vertices[m.faces]))))
    require(err<=2e-6,"coordinate transport")
    return {"sha256":sha(raw),"nodes":len(expected),"triangles":sum(len(m.faces) for m in expected.values()),"max_coordinate_error_m":err}
def preview(out,data,tf):
    im=Image.new("RGB",(1120,760),"#17232f");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",20)
    d.text((15,12),"Bilateral pelvis surface holdout: CT blue / HRA gold",font=font,fill="white")
    d.text((15,43),"Actual sampled compact-bone surfaces; independent donor references, not fused.",font=font,fill="#bac8d2")
    allp=np.concatenate([p for row in data for p in row[:2]]);c=(allp.max(0)+allp.min(0))/2;s=430/max(np.ptp(allp[:,0]),np.ptp(allp[:,1]),.01)
    for k,trans in enumerate([(np.eye(3),np.zeros(3)),tf]):
        x=280+k*560
        d.text((x-240,95),"Axial centre initialization" if k==0 else "Bilateral rigid surface candidate",font=font,fill="white")
        for a,b,split in data:
            for p,col in ((b,"#d7b57b"),(apply(a,trans),"#6cb5dc")):
                d.point([(x+float(v[0]-c[0])*s,410-float(v[1]-c[1])*s) for v in p],fill=col)
    im.save(out/"pelvic-surface-preview.png")
def main(inp,out):
    selftest();out.mkdir(parents=True,exist_ok=False)
    with checked(inp/"ct.zip",CT) as z,checked(inp/"female.zip",HRA) as h,checked(inp/"pelvis.zip",PELVIS) as p,checked(inp/"registration.zip",REG) as r:
        cr=json.loads(z.read("receipt.json"));hr=json.loads(h.read("receipt.json"));pr=json.loads(p.read("receipt.json"));rr=json.loads(r.read("registration.json"))
        anchors=[f["holdout"] for f in rr["folds"] if f["holdout"]["region"]=="axial"]
        require(len(anchors)==27 and len({a["name"] for a in anchors})==27,"axial anchor inventory")
        a=np.array([x["ct"] for x in anchors]);b=np.array([x["hra"] for x in anchors]);init=fit(a,b)
        raw=h.read("layers/skeletal.glb");require(sha(raw)==hr["files"]["layers/skeletal.glb"]["sha256"],"current layer hash")
        cs=scene(z.read("ct-skeleton-original-frame.glb"));hs=scene(raw)
        raw=p.read("historical-pelvis-reference.glb");require(sha(raw)==pr["subset_sha256"] and pr["shared_exact_pass_count"]==48,"historical receipt");ps=scene(raw)
        parts=[];train=[];test=[];splits=[];views=[]
        for k,(side,ctid) in enumerate((("L","bone_072_HIP_LEFT"),("R","bone_077_HIP_RIGHT"))):
            rec=next(x for x in cr["inventory"] if x["id"]==ctid);m=world(cs,ctid);require(len(m.faces)==rec["triangles"],"CT triangle count")
            hn=next(n for n in hs.graph.nodes_geometry if n.endswith("VH_F_ilium_compact_bone_"+side))
            refs=[(hn,world(hs,hn))]+[(n,world(ps,n)) for n in ("VH_F_ischium_compact_bone_"+side,"VH_F_pubis_compact_bone_"+side)]
            at=apply(m.vertices[m.faces],init);bt=np.concatenate([q.vertices[q.faces] for _,q in refs])
            atr,ate,asp=partition(at,100+k*10);btr,bte,bsp=partition(bt,200+k*10)
            train.append((atr,btr));test.append((ate,bte));splits.append({"side":side,"ct_id":ctid,"hra_nodes":[n for n,_ in refs],"ct":asp,"hra":bsp})
            views.append((np.concatenate([atr,ate]),np.concatenate([btr,bte]),asp))
            parts.append(("CT_"+ctid,m,True));parts.extend(("HRA_"+n,q,False) for n,q in refs)
        delta,hist=icp(train)
        initial=(np.eye(3),np.zeros(3))
        rows=[]
        for k,side in enumerate(("L","R")):
            rows.append({"side":side,"initial_train":metric(*train[k],initial),"fitted_train":metric(*train[k],delta),"initial_heldout":metric(*test[k],initial),"fitted_heldout":metric(*test[k],delta)})
        full=compose(init,delta);angle=float(np.degrees(np.arccos(np.clip((np.trace(delta[0])-1)/2,-1,1))))
        outputs={"initial":model(out,"pelvis-axial-initial.glb",parts,init),"candidate":model(out,"pelvis-bilateral-rigid.glb",parts,full)}
        preview(out,views,delta)
        (out/"ATTRIBUTION.txt").write_bytes(z.read("ATTRIBUTION.txt")+b"\n"+h.read("ATTRIBUTION.txt")+b"\n"+p.read("ATTRIBUTION.txt")+b"\nR231: rigid comparison of separate female donor hip meshes and HRA compact reference subregions. No mesh union or inferred anatomy.\n")
        report={"source_pins":{"CT":CT,"HRA":HRA,"historical":PELVIS,"registration":REG},"axial_training_names":[x["name"] for x in anchors],"axial_transform":tf_json(init),"bilateral_delta":tf_json(delta),"delta_rotation_deg":angle,"delta_translation_mm":float(np.linalg.norm(delta[1])*1000),"spatial_partitions":splits,"iterations":len(hist),"trimmed_training_history_mm":hist,"results":rows,"models":outputs,"status":"HOLD_ANATOMICAL_REGISTRATION","scope":"Two donor-specific pelvis references, sample-to-sample distances not exact surfaces; upper 65% face-centroid partitions train, lower 35% withheld separately per side/donor. No articulated joint, contact, surface equivalence, whole-body fit or clinical admission."}
        (out/"receipt.json").write_text(json.dumps(report,indent=2))
        print("R231_PELVIC_SURFACE",json.dumps({k:v for k,v in report.items() if k not in ("axial_training_names","trimmed_training_history_mm","spatial_partitions")}),flush=True)
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
