"""Generic adult MakeHuman inverse-fit experiment; bundled CC0 asset data only.
Shape-basis inversion assumes corresponding vertices; spatial primitive fit does not.
No native Foundry execution or person identification.
"""
import sys, json, hashlib, math
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from scipy.optimize import lsq_linear
from PIL import Image,ImageDraw,ImageFont
BASE="d26635e9326e3cca30778fd7b9c00062b03cce09"
ADULT={
 "male":[("african-male-young","dd5743e48700267d76596f575bf17b4b5cc3b3e0"),("asian-male-young","8cd3ef3e9ddb06ee2d166f75f9ac10871251f938"),("caucasian-male-young","c3b82f92c5ced85599199cd184b0faf3b3fc6881")],
 "female":[("african-female-young","a7d2b130667cc81ecd1ca0598da9be27bec1864a"),("asian-female-young","f862c96add11c31ab1ca75c69e1c67ae5e0e3d5f"),("caucasian-female-young","9d1f0cbeedc9a6a51abe33f1ebb5fa7c5a7edbf1")]}
REGION=[("torso-scale-depth-incr","265f5bb7e4cf6f8d69fdc465618875ff16c25d03"),("torso-scale-horiz-incr","f428c36c65c2bd2b43136c95ffd571c9579d0501"),("torso-scale-vert-incr","97f40d58f2d36afc3dbc6e8c5486d411f979aefd"),("torso-vshape-incr","67721c8f8f59059da8baf9ada02c6013ddf695b3")]
def blob(raw):return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def check(path,expected):
    raw=path.read_bytes()
    if blob(raw)!=expected:raise ValueError("donor identity "+path.name)
    return raw
def xyz(p):return p[:,[0,2,1]]*np.array([.1,-.1,.1])
def base(path):
    raw=check(path,BASE);vertices=[];faces=[];groups={};g=""
    for line in raw.decode().splitlines():
        t=line.split()
        if not t:continue
        if t[0]=="v":vertices.append([float(x) for x in t[1:4]])
        elif t[0]=="g":g=" ".join(t[1:])
        elif t[0]=="f":
            q=[int(x.split("/")[0])-1 for x in t[1:]]
            groups.setdefault(g,set()).update(q)
            if all(0<=i<13380 for i in q):faces.extend([q[0],q[j],q[j+1]] for j in range(1,len(q)-1))
    v=xyz(np.array(vertices));f=np.array(faces)
    assert len(v)==19158 and len(f)>10000 and np.isfinite(v).all()
    return v,f,groups
def delta(path,digest):
    raw=check(path,digest);v=np.zeros((19158,3))
    for l in raw.decode().splitlines():
        t=l.split()
        if not t or t[0].startswith("#"):continue
        assert len(t)==4
        i=int(t[0]);assert 0<=i<len(v);v[i]=[float(x) for x in t[1:]]
    return xyz(v)
def obj(path,v,f):
    path.write_text("# metric Z-up; generic MakeHuman derived geometry\n"+"".join("v %.9f %.9f %.9f\n"%tuple(p) for p in v)+"".join("f %d %d %d\n"%tuple(q+1) for q in f))
def sample(v,f,n,seed):
    t=v[f];a=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)
    rng=np.random.default_rng(seed);t=t[rng.choice(len(f),n,p=a/a.sum())];u=rng.random((n,2));u[u.sum(1)>1]=1-u[u.sum(1)>1]
    return t[:,0]+u[:,0,None]*(t[:,1]-t[:,0])+u[:,1,None]*(t[:,2]-t[:,0])
def metrics(a,b):
    x=cKDTree(a).query(b)[0];y=cKDTree(b).query(a)[0]
    return {"rmse_mm":float(np.sqrt((np.mean(x*x)+np.mean(y*y))/2)*1000),"coverage_20mm":float(min(np.mean(x<=.02),np.mean(y<=.02)))}
def split(p,k):
    cells=[p]
    while len(cells)<k:
        i=max(range(len(cells)),key=lambda i:len(cells[i])*np.var(cells[i],axis=0).sum());q=cells.pop(i)
        _,_,R=np.linalg.svd(q-q.mean(0),full_matrices=False);q=q[np.argsort((q-q.mean(0))@R[0])];m=len(q)//2;cells.extend([q[:m],q[m:]])
    return cells
def fit(p,kind):
    c=p.mean(0);_,_,R=np.linalg.svd(p-c,full_matrices=False)
    if np.linalg.det(R)<0:R[2]*=-1
    q=(p-c)@R.T;lo,hi=np.quantile(q,[.01,.99],axis=0);center=c+(lo+hi)/2@R;half=np.maximum((hi-lo)/2,.005)
    if kind=="ellipsoid":
        m=trimesh.creation.icosphere(subdivisions=2);v=m.vertices*half;params={"half_axes_m":half.tolist()}
    else:
        radius=max(float(np.quantile(np.linalg.norm(q[:,1:]-(lo+hi)[1:]/2,axis=1),.9)),.01);h=max(float(half[0]*2),.01)
        m=trimesh.creation.cylinder(radius=radius,height=h,sections=24);v=m.vertices[:,[2,0,1]];params={"radius_m":radius,"height_m":h}
    return v@R+center,m.faces,{"kind":kind,"center_m":center.tolist(),"frame_rows":R.tolist(),**params}
def combine(cells,kind):
    vs=[];fs=[];ps=[];off=0
    for p in cells:
        v,f,param=fit(p,kind);vs.append(v);fs.append(f+off);off+=len(v);ps.append(param)
    return np.concatenate(vs),np.concatenate(fs),ps
def native(params,out):
    defs=[];inst=[]
    for i,p in enumerate(params):
        id="bodypart_"+str(i);R=np.array(p["frame_rows"]);M=np.column_stack((R[1],R[2],R[0]))
        angles=Rotation.from_matrix(M).as_euler("xyz",degrees=True).tolist()
        g={"schema":"oneirifact.graph/v0.1","name":id,"unit":"m","detail":32,"root":"solid","features":[{"id":"solid","op":"cylinder","params":{"radius":p["radius_m"],"height":p["height_m"]}}]}
        defs.append({"schema":"oneirifact.component/v0.1","id":id,"name":id,"unit":"m","graph":g})
        inst.append({"id":id,"definition_id":id,"composition_mode":"scene_assembly","transform":{"translation":p["center_m"],"rotation":angles,"scale":1}})
    (out/"components.candidate.json").write_text(json.dumps(defs,indent=2))
    (out/"scene.candidate.json").write_text(json.dumps({"schema":"oneirifact.scene/v0.1","id":"human_coarse","name":"Coarse human cylinder candidate","composition_mode":"scene_assembly","instances":inst},indent=2))
def silhouette(im,rect,v,f,side,color,scale):
    x,y,w,h=rect;axis=1 if side else 0;d=ImageDraw.Draw(im);q=v[:,[axis,2]];c=(q[:,0].min()+q[:,0].max())/2
    p=np.column_stack((x+w/2+(q[:,0]-c)*scale,y+h-8-q[:,1]*scale))
    for tri in f:d.polygon([tuple(p[i]) for i in tri],fill=color)
def preview(out,models,height,sex):
    im=Image.new("RGB",(300*len(models),780),"#17212b");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",21);small=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
    d.text((12,12),sex.title()+" adult | actual MakeHuman mesh and inverse shape experiments",font=font,fill="white")
    d.text((12,44),"Clinical silhouette views; reference geometry, not native-engine output",font=small,fill="#b9cad8")
    for i,(name,v,f,sub) in enumerate(models):
        x=i*300;d.text((x+10,84),name,font=font,fill="white")
        scale=min(280/max(np.ptp(models[0][1][:,0]),.01),350/height)
        silhouette(im,(x+5,108,290,365),v,f,False,"#afc1ce" if i==0 else "#79c9ac",scale)
        silhouette(im,(x+5,492,290,222),v,f,True,"#afc1ce" if i==0 else "#79c9ac",205/height)
        d.text((x+8,733),sub,font=small,fill="white")
    im.save(out/"comparison.png")
def main(inp,out,sex):
    out.mkdir(parents=True,exist_ok=False)
    v,f,groups=base(inp/"base.obj")
    adult=sum((delta(inp/(n+".target"),h) for n,h in ADULT[sex]),np.zeros_like(v))/3
    basis=np.stack([delta(inp/(n+".target"),h) for n,h in REGION],axis=-1)
    baseline=v+adult;coeff=np.array([.28,.55,.20,.40] if sex=="male" else [.45,.18,.35,.22])
    truth=baseline+basis@coeff
    # Controlled known-correspondence inverse problem: unknown coefficients,
    # known donor basis; disjoint vertex subsets, not blind scan inversion.
    rng=np.random.default_rng(217);ids=rng.permutation(13380);train=ids[:7000];test=ids[7000:]
    A=basis[train].reshape(-1,4);y=(truth[train]-baseline[train]).reshape(-1)
    fitcoef=lsq_linear(A,y,bounds=(0,1),lsmr_tol="auto").x
    recon=baseline+basis@fitcoef
    residual=np.linalg.norm(recon[test]-truth[test],axis=1)
    origin=np.array([0,0,truth[:13380,2].min()]);body=truth[:13380]-origin;recon=recon[:13380]-origin
    assert .8<np.ptp(body[:,2])<2.5 and np.max(np.abs(fitcoef-coeff))<1e-6
    obj(out/"body-reference.obj",body,f);obj(out/"body-basis-recovered.obj",recon,f)
    trainp=sample(body,f,14000,217);val=sample(body,f,18000,218);held=sample(body,f,30000,219)
    rows=[];models=[("Reference",body,f,"Donor-derived adult"),("Basis recovery",recon,f,"Known correspondence")]
    choices={}
    for k,kind in ((8,"ellipsoid"),(16,"ellipsoid"),(32,"ellipsoid"),(16,"cylinder")):
        pv,pf,p=combine(split(trainp,k),kind);tag=f"{k}-{kind}"
        m=metrics(val,sample(pv,pf,18000,220));rows.append({"tag":tag,"validation":m,"parameters":p})
        obj(out/(tag+".obj"),pv,pf);choices[tag]=(pv,pf)
        if kind=="cylinder":native(p,out)
    winner=min(rows,key=lambda r:r["validation"]["rmse_mm"]);pv,pf=choices[winner["tag"]]
    heldm=metrics(held,sample(pv,pf,30000,221))
    models.append((winner["tag"],pv,pf,f"Held-out {heldm['rmse_mm']:.1f} mm"))
    cv,cf=choices["16-cylinder"];models.append(("16-cylinder",cv,cf,"Native-schema candidate"))
    preview(out,models,np.ptp(body[:,2]),sex)
    joint={k:(truth[sorted(ix)].mean(0)-origin).tolist() for k,ix in groups.items() if k.startswith("joint-")}
    receipt={"sex_variant":sex,"source":"MakeHuman CC0 adult morph assets, equal-weight adult basis of three donor anchors plus four regional modifiers","source_blob":BASE,"visible_vertices":len(body),"triangles":len(f),"height_m":float(np.ptp(body[:,2])),"donor_joint_helper_centroids_m":joint,"basis":{"truth":coeff.tolist(),"recovered":fitcoef.tolist(),"heldout_vertex_rmse_mm":float(np.sqrt(np.mean(residual**2))*1000),"scope":"known corresponding vertices; exact donor basis"},"spatial":{"candidates":rows,"chosen":winner["tag"],"heldout":heldm},"native":"cylinder scene candidate only; no native execution; no skinning/rig qualification"}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2))
    # Preserve original asset/target bytes and license for reconstruction.
    import shutil
    shutil.copytree(inp,out/"source")
    print("R217_HUMAN",json.dumps({k:receipt[k] for k in ("sex_variant","height_m","basis")}),winner["tag"],heldm)
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
