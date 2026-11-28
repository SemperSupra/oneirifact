"""Editable adult morphology and refitted donor-rig pose experiment.
Uses pinned original CC0 MakeHuman targets; not a physiological or patient model.
Age is an artistic adult morphology coordinate, not age prediction.
"""
import argparse,hashlib,json,math,sys,shutil
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"r217"))
from human_inverse import base,delta,ADULT,REGION,BASE,blob
UPSTREAM="a8bc2d54ff0ac92e78ff71431b1023eda42bf482"
OLD=[("african-female-old","d135b064567df7810b3a91396bdd5c2e76b10a9d"),("asian-female-old","a2afe59829cd0caa66c3eea160f2f05d15890e23"),("caucasian-female-old","2359bb525ddc620d43d309ba3dfea12b1fa88671")]
MACRO={
 "young":{(1,0):("universal-female-young-maxmuscle-minweight","7eb470715d485b9f21733dd7142f0cd0369638ac"),(1,1):("universal-female-young-maxmuscle-averageweight","91ca14d335389e4e4a964132fc6580ada688cb64"),(0,0):("universal-female-young-averagemuscle-minweight","7b4dfc290b1228f48f00e7b121ffe8932a7bbb75")},
 "old":{(1,0):("universal-female-old-maxmuscle-minweight","ab6e5bc63b403072bde0e6b75f5b9f36bcf32fd7"),(1,1):("universal-female-old-maxmuscle-averageweight","1c5f1f0945a0c627a8b7df717c218dd0f97fb20a"),(0,0):("universal-female-old-averagemuscle-minweight","bc3a0847f3661babd14252853c5d62fdd0cf4b03")}}
RIG={"default.mhskel":"b02cbecae00143856410d7561adf006d83bf9b3e","default_weights.mhw":"66185806afacf87749be8e5cf6dbf66496b2a6b0"}
def sha(b):return hashlib.sha256(b).hexdigest()
def require(q,msg):
    if not q:raise ValueError(msg)
def readjson(path):
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,"duplicate key");d[k]=v
        return d
    return json.loads(path.read_bytes(),object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError("nonfinite JSON")))
def validate(s):
    fields={"schema","adult","sex","age_years","height_m","muscularity","mass_morph","torso_depth","torso_width","torso_length","torso_vshape","spine_flexion_deg"}
    require(set(s)==fields and s["schema"]=="oneirifact.adult-morphology/v1" and s["adult"] is True and s["sex"]=="female","unsupported adult morphology schema")
    bounds={"age_years":(25,90),"height_m":(1.45,2.0),"muscularity":(0,1),"mass_morph":(0,1),"torso_depth":(0,1),"torso_width":(0,1),"torso_length":(0,1),"torso_vshape":(0,1),"spine_flexion_deg":(-10,20)}
    for k,(lo,hi) in bounds.items():
        v=s[k];require(type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi,"out of range "+k)
    return s
def profile(**kw):
    d={"schema":"oneirifact.adult-morphology/v1","adult":True,"sex":"female","age_years":30,"height_m":1.68,"muscularity":0.,"mass_morph":1.,"torso_depth":0.,"torso_width":0.,"torso_length":0.,"torso_vshape":0.,"spine_flexion_deg":0.}
    d.update(kw);return validate(d)
def load(inp):
    v,f,_=base(inp/"base.obj")
    pins=dict(ADULT["female"]+OLD+REGION)
    for table in MACRO.values():pins.update(table.values())
    targets={n:delta(inp/(n+".target"),h) for n,h in pins.items()}
    rig={}
    for n,h in RIG.items():
        raw=(inp/n).read_bytes();require(blob(raw)==h,n+" digest");rig[n]=readjson(inp/n);require(rig[n]["license"]=="CC0",n+" license")
    return v,f,targets,pins,rig
def shape(s,v,targets):
    age=(s["age_years"]-25)/65
    m,w=s["muscularity"],s["mass_morph"]
    q=v.copy()
    for stage,alpha,anchors in (("young",1-age,ADULT["female"]),("old",age,OLD)):
        q+=alpha*sum((targets[n] for n,h in anchors),np.zeros_like(v))/3
        for (mi,wi),(n,h) in MACRO[stage].items():
            q+=alpha*(m if mi else 1-m)*(w if wi else 1-w)*targets[n]
    for (n,h),k in zip(REGION,("torso_depth","torso_width","torso_length","torso_vshape")):
        q+=s[k]*targets[n]
    # Uniform stature scaling is explicit; separate limb proportions are future.
    q[:,2]-=q[:13380,2].min();q*=s["height_m"]/np.ptp(q[:13380,2])
    require(np.isfinite(q).all(),"nonfinite shape")
    return q[:,[0,2,1]]*np.array([1,1,-1])
def unit(a):
    n=np.linalg.norm(a);require(n>1e-10,"degenerate rig");return a/n
def skeleton(v,rig):
    sk=rig["default.mhskel"];bones=sk["bones"]
    joints={n:v[np.array(ix)].mean(0) for n,ix in sk["joints"].items()}
    names=[];pending=set(bones)
    while pending:
        ready=sorted(n for n in pending if bones[n]["parent"] is None or bones[n]["parent"] in names)
        require(ready,"invalid hierarchy");names+=ready;pending.difference_update(ready)
    ix={n:i for i,n in enumerate(names)};world=[];fallback=[]
    for n in names:
        b=bones[n];head=joints[b["head"]];tail=joints[b["tail"]];y=unit(tail-head)
        plane=[joints[p] for p in sk["planes"][b["rotation_plane"]]]
        normal=np.cross(plane[1]-plane[0],plane[2]-plane[0]);normal-=y*np.dot(normal,y)
        if np.linalg.norm(normal)<1e-9:
            fallback.append(n);axis=np.eye(3)[np.argmin(abs(y))];normal=axis-y*np.dot(axis,y)
        z=unit(normal);x=unit(np.cross(y,z));z=unit(np.cross(x,y))
        a=np.eye(4);a[:3,:3]=np.column_stack((x,y,z));a[:3,3]=head;world.append(a)
    world=np.array(world);inv=np.linalg.inv(world)
    local=np.array([world[i] if bones[n]["parent"] is None else inv[ix[bones[n]["parent"]]]@world[i] for i,n in enumerate(names)])
    require(len(names)==163 and len(joints)==326,"rig inventory")
    return names,ix,bones,joints,world,inv,local,fallback
def pose(v,s,rig):
    names,ix,bones,joints,world,inv,local,fallback=skeleton(v,rig)
    full=np.zeros((13380,len(names)))
    for n,rows in rig["default_weights.mhw"]["weights"].items():
        for i,w in rows:
            require(0<=i<len(v) and math.isfinite(w) and w>=0,"invalid weight")
            if i<len(full):full[i,ix[n]]+=w
    sums=full.sum(1);require(np.min(sums)>0,"unbound visible vertex");full/=sums[:,None]
    hom=np.column_stack((v[:13380],np.ones(13380)))
    def deform(g):return np.einsum("vb,bjk,vk->vj",full,g@inv,hom)[:,:3]
    require(np.max(np.abs(deform(world)-v[:13380]))<1e-9,"rest skin mismatch")
    lp=local.copy();angle=s["spine_flexion_deg"]
    for n in ("spine05","spine04","spine03","spine02","spine01"):
        i=ix[n];axis=world[i,:3,:3].T@np.array([1.,0.,0.])
        lp[i,:3,:3]=lp[i,:3,:3]@Rotation.from_rotvec(axis*math.radians(angle/5)).as_matrix()
    posed=[]
    for i,n in enumerate(names):
        par=bones[n]["parent"];posed.append(lp[i] if par is None else posed[ix[par]]@lp[i])
    posed=np.array(posed);pv=deform(posed)
    require(np.isfinite(pv).all(),"nonfinite pose")
    # Lower limbs unchanged by spine-only rotations.
    for n in ("foot.L","foot.R","upperleg01.L","upperleg01.R"):
        require(np.max(np.abs(posed[ix[n]]-world[ix[n]]))<1e-9,"unexpected lower-limb transform")
    fitted={"bones":[{"id":n,"parent":bones[n]["parent"],"world_bind":world[i].tolist(),"inverse_bind":inv[i].tolist(),"local_bind":local[i].tolist(),"posed_world":posed[i].tolist()} for i,n in enumerate(names)],"fallback_roll_frames":fallback,"joints":len(joints),"pose_axis":"world X expressed in rest-bone local axes, five spine segments"}
    return pv,fitted
def write_model(out,name,v,f):
    m=trimesh.Trimesh(vertices=v,faces=f,process=False)
    m.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name="neutral reference",baseColorFactor=[.66,.72,.77,1],metallicFactor=0,roughnessFactor=.9))
    raw=m.export(file_type="glb");(out/name).write_bytes(raw)
    q=trimesh.load(out/name,force="mesh",process=False)
    require(q.faces.shape==f.shape,"face count")
    error=float(np.max(np.abs(q.vertices[q.faces]-v[f])));require(error<2e-6,"coordinate transport")
    return {"sha256":sha(raw),"triangles":len(f),"vertices":len(v),"transport_max_m":error}
def measure(v):
    # Explicit geometric bounds only, not clinical tape-measure or mass.
    return {"stature_m":float(np.ptp(v[:,1])),"total_width_m":float(np.ptp(v[:,0])),"total_depth_m":float(np.ptp(v[:,2]))}
def render(out,models):
    # Non-detailed silhouettes: inspect body proportions and pose, not surface details.
    im=Image.new("RGB",(280*len(models),750),"#17232f");d=ImageDraw.Draw(im)
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",19)
    sm=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",15)
    d.text((12,12),"Adult female morphology | actual editable donor target outputs",font=font,fill="white")
    d.text((12,40),"Same scale, neutral silhouette. Artist controls, not physiological age/fitness estimates.",font=sm,fill="#bdcad4")
    scale=300/2.0
    for i,(name,v,f,s) in enumerate(models):
        x=280*i;d.text((x+12,72),name,font=font,fill="white")
        for axis,y in ((0,385),(2,715)):
            cx=x+140;center=(v[:,axis].min()+v[:,axis].max())/2
            a=np.column_stack((cx+(v[:,axis]-center)*scale,y-v[:,1]*scale))
            for tri in f:d.polygon([tuple(p) for p in a[tri]],fill="#a9bdcc")
        d.text((x+12,395),f'{s["height_m"]:.2f} m / age {s["age_years"]}',font=sm,fill="white")
    im.save(out/"morphology-comparison.png")
def run(inp,out,spec=None):
    out.mkdir(parents=True,exist_ok=False)
    v,f,targets,pins,rig=load(inp)
    specs={"neutral":profile(),"athletic":profile(muscularity=.85,mass_morph=.55,torso_vshape=.2),"older-athletic":profile(age_years=65,muscularity=.85,mass_morph=.55,torso_vshape=.2),"tall-athletic":profile(height_m=1.80,muscularity=.85,mass_morph=.55,torso_vshape=.2),"flexion":profile(muscularity=.85,mass_morph=.55,torso_vshape=.2,spine_flexion_deg=15)}
    if spec is not None:specs={"custom":validate(readjson(spec))}
    # Negative controls. Reject all values outside the stated adult scope.
    for field,val in (("age_years",17),("height_m",0),("muscularity",float("nan")),("spine_flexion_deg",200),("adult",False)):
        bad=profile();bad[field]=val
        try:validate(bad)
        except ValueError:pass
        else:raise AssertionError("invalid spec admitted "+field)
    rows=[];views=[];rest={}
    for name,s in specs.items():
        q=shape(s,v,targets);require(np.max(abs(q-shape(s,v,targets)))==0,"nonreplayable shape")
        require(abs(np.ptp(q[:13380,1])-s["height_m"])<1e-9,"height calibration")
        pv,fit=pose(q,s,rig);body=q[:13380]
        a=write_model(out,name+"-rest.glb",body,f);b=write_model(out,name+"-posed.glb",pv,f)
        (out/(name+"-spec.json")).write_text(json.dumps(s,indent=2)+"\n")
        (out/(name+"-rig.json")).write_text(json.dumps(fit,indent=2)+"\n")
        moved=float(np.max(np.linalg.norm(pv-body,axis=1)))
        if s["spine_flexion_deg"]==0:require(moved<1e-9,"nonzero rest pose")
        else:require(moved>.005,"pose ineffective")
        rest[name]=body
        rows.append({"id":name,"spec":s,"rest":a,"posed":b,"geometry_bounds":measure(body),"posed_bounds":measure(pv),"pose_max_displacement_m":moved,"rig_bones":len(fit["bones"])})
        views.append((name,pv,f,s))
    if spec is None:
        require(np.sqrt(np.mean((rest["athletic"]-rest["neutral"])**2))>.001,"athletic control ineffective")
        require(np.sqrt(np.mean((rest["older-athletic"]-rest["athletic"])**2))>.001,"age control ineffective")
        require(np.max(np.abs(rest["flexion"]-rest["athletic"]))==0,"posture changed rest shape")
    render(out,views);shutil.copytree(inp,out/"source")
    report={"upstream_revision":UPSTREAM,"source_blob_pins":{"base.obj":BASE,**RIG,**pins},"controls":{"age_years":"25–90 design label interpolates donor young/old anchors; not calibrated biological aging","muscularity":"average to high donor shape morph","mass_morph":"low to average donor weight shape; not measured fat percentage or mass","height_m":"exact uniform stature scaling","torso":"four donor regional modifiers","spine_flexion_deg":"diagnostic bounded spine rotation, not physiological contact/strain qualification"},"variants":rows,"status":"ADULT_DONOR_MORPH_AND_CPU_POSE_WITNESS","scope":"Independent generic adult female design. No internal anatomical layer deformation, native Foundry execution, clinical realism, arbitrary joint editing or automatic fitness inference."}
    (out/"receipt.json").write_text(json.dumps(report,indent=2))
    print("R232_MORPHOLOGY",json.dumps({"status":report["status"],"variants":[{k:r[k] for k in ("id","geometry_bounds","pose_max_displacement_m","rig_bones","spec")} for r in rows]}),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("input",type=Path);p.add_argument("output",type=Path);p.add_argument("--spec",type=Path);a=p.parse_args();run(a.input,a.output,a.spec)
