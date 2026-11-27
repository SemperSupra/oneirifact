"""Recover the actual CC0 MakeHuman rig and weights; independent GLB skin transport.
This is the animation skeleton, NOT anatomical bone meshes or internal tissue rigging.
"""
import sys,json,hashlib,zipfile,struct,math
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"r217"))
from human_inverse import base,delta,ADULT,REGION,obj
PINS={"male":"fd63861d5cd8bab550c282f5490e36bb57f0ca5a45999f88f120b1bcc5fa615f","female":"bfc5e4d5c64d48f4c764ed502aec9af5841c3962a1e6e0a961e752eaf78644e4"}
def sha(x):return hashlib.sha256(x).hexdigest()
def blob(x):return hashlib.sha1(b"blob "+str(len(x)).encode()+b"\0"+x).hexdigest()
def unit(a):
    n=np.linalg.norm(a);assert n>1e-10
    return a/n
def main(body,src,out,sex):
    out.mkdir(parents=True,exist_ok=False)
    assert sha(body.read_bytes())==PINS[sex]
    with zipfile.ZipFile(body) as z:
        receipt=json.loads(z.read("receipt.json"));assert receipt["sex_variant"]==sex
        d=out/"source";d.mkdir()
        for name in z.namelist():
            if name.startswith("source/") and not name.endswith("/"):
                dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
        original=z.read("body-reference.obj");(out/"body-reference.obj").write_bytes(original)
    for name,h in [("default.mhskel","b02cbecae00143856410d7561adf006d83bf9b3e"),("default_weights.mhw","66185806afacf87749be8e5cf6dbf66496b2a6b0")]:
        raw=(src/name).read_bytes();assert blob(raw)==h;(d/name).write_bytes(raw)
    sk=json.loads((d/"default.mhskel").read_text());ww=json.loads((d/"default_weights.mhw").read_text())
    assert sk["license"]==ww["license"]=="CC0"
    v,f,_=base(d/"base.obj")
    v+=sum((delta(d/(n+".target"),h) for n,h in ADULT[sex]),np.zeros_like(v))/3
    for (n,h),c in zip(REGION,receipt["basis"]["truth"]):v+=delta(d/(n+".target"),h)*c
    v[:,2]-=v[:13380,2].min()
    observed=np.array([[float(x) for x in l.split()[1:4]] for l in original.decode().splitlines() if l.startswith("v ")])
    assert observed.shape==(13380,3) and np.max(abs(observed-v[:13380]))<1e-8
    # World Y-up frame for GLB; preserve all original helpers in fitted joint calculation.
    v=v[:,[0,2,1]]*np.array([1,1,-1])
    joints={n:v[np.array(ix)].mean(0) for n,ix in sk["joints"].items()}
    bones=sk["bones"];names=[];pending=set(bones)
    while pending:
        ready=sorted(n for n in pending if bones[n]["parent"] is None or bones[n]["parent"] in names)
        assert ready,"cyclic or orphan bone hierarchy"
        names+=ready;pending.difference_update(ready)
    ix={n:i for i,n in enumerate(names)};N=len(names);world=[];fallback=[]
    for n in names:
        b=bones[n];head=joints[b["head"]];tail=joints[b["tail"]];y=unit(tail-head)
        plane=[joints[p] for p in sk["planes"][b["rotation_plane"]]]
        normal=np.cross(plane[1]-plane[0],plane[2]-plane[0]);normal-=y*np.dot(normal,y)
        if np.linalg.norm(normal)<1e-9:
            fallback.append(n);axis=np.eye(3)[np.argmin(abs(y))];normal=axis-y*np.dot(axis,y)
        z=unit(normal);x=unit(np.cross(y,z));z=unit(np.cross(x,y))
        m=np.eye(4);m[:3,:3]=np.column_stack((x,y,z));m[:3,3]=head;world.append(m)
    world=np.array(world);inv=np.linalg.inv(world);local=[]
    for i,n in enumerate(names):
        p=bones[n]["parent"];local.append(world[i] if p is None else inv[ix[p]]@world[i])
    local=np.array(local)
    # Full donor weights retained verbatim. For portable glTF, retain top four
    # positive influences with normalization, report lost mass explicitly.
    full=np.zeros((13380,N))
    for n,rows in ww["weights"].items():
        assert n in ix
        for i,w in rows:
            assert 0<=i<len(v) and math.isfinite(w) and w>=0
            if i<len(full):full[i,ix[n]]+=w
    sums=full.sum(1);assert np.min(sums)>0
    normalized=full/sums[:,None]
    ids=np.argsort(-normalized,axis=1,kind="stable")[:,:4];weights=np.take_along_axis(normalized,ids,axis=1);lost=1-weights.sum(1);weights/=weights.sum(1)[:,None]
    bodyv=v[:13380];hom=np.column_stack((bodyv,np.ones(len(bodyv))))
    def deform(g,allweights=False):
        trans=g@inv
        if allweights:return np.einsum("vb,bjk,vk->vj",normalized,trans,hom)[:,:3]
        return np.einsum("vi,vijk,vk->vj",weights,trans[ids],hom)[:,:3]
    assert np.max(abs(deform(world)-bodyv))<1e-10
    selected="lowerarm01.L";idx=ix[selected]
    localpose=local.copy();localpose[idx,:3,:3]=localpose[idx,:3,:3]@Rotation.from_euler("x",30,degrees=True).as_matrix()
    posed=[]
    for i,n in enumerate(names):
        parent=bones[n]["parent"];posed.append(localpose[i] if parent is None else posed[ix[parent]]@localpose[i])
    posed=np.array(posed);pv=deform(posed);pf=deform(posed,True);move=np.linalg.norm(pv-bodyv,axis=1);assert move.max()>.01
    # Portable standard glTF 2.0 skin, bind matrices, hierarchy and a diagnostic animation.
    data=bytearray();views=[];access=[]
    def add(a,component,kind,target=None,bounds=False):
        a=np.ascontiguousarray(a);data.extend(b"\0"*(-len(data)%4));off=len(data);data.extend(a.tobytes())
        view={"buffer":0,"byteOffset":off,"byteLength":a.nbytes}
        if target:view["target"]=target
        vi=len(views);views.append(view);entry={"bufferView":vi,"componentType":component,"count":len(a),"type":kind}
        if bounds:entry.update(min=np.min(a,axis=0).reshape(-1).tolist(),max=np.max(a,axis=0).reshape(-1).tolist())
        ai=len(access);access.append(entry);return ai
    pos=add(bodyv.astype("<f4"),5126,"VEC3",34962,True);inds=add(f.astype("<u4").ravel(),5125,"SCALAR",34963)
    ji=add(ids.astype("<u2"),5123,"VEC4",34962);we=add(weights.astype("<f4"),5126,"VEC4",34962)
    ib=add(inv.transpose(0,2,1).astype("<f4").reshape(-1,16),5126,"MAT4")
    time=add(np.array([0,1,2],dtype="<f4"),5126,"SCALAR",bounds=True)
    rotations=np.array([Rotation.from_matrix(m).as_quat() for m in (local[idx,:3,:3],localpose[idx,:3,:3],local[idx,:3,:3])],dtype="<f4")
    anim=add(rotations,5126,"VEC4")
    nodes=[]
    for i,n in enumerate(names):
        node={"name":n,"translation":local[i,:3,3].tolist(),"rotation":Rotation.from_matrix(local[i,:3,:3]).as_quat().tolist()}
        children=[ix[k] for k in names if bones[k]["parent"]==n]
        if children:node["children"]=children
        nodes.append(node)
    nodes.append({"name":"adult_skin","mesh":0,"skin":0})
    doc={"asset":{"version":"2.0","generator":"R219 original donor rig data, independent transport"},"scene":0,"scenes":[{"nodes":[ix["root"],N]}],"nodes":nodes,"meshes":[{"primitives":[{"attributes":{"POSITION":pos,"JOINTS_0":ji,"WEIGHTS_0":we},"indices":inds,"material":0}]}],"materials":[{"doubleSided":True,"pbrMetallicRoughness":{"baseColorFactor":[.65,.72,.76,1],"metallicFactor":0,"roughnessFactor":.9}}],"skins":[{"joints":list(range(N)),"skeleton":ix["root"],"inverseBindMatrices":ib}],"animations":[{"name":"diagnostic elbow rotation","samplers":[{"input":time,"output":anim,"interpolation":"LINEAR"}],"channels":[{"sampler":0,"target":{"node":idx,"path":"rotation"}}]}],"buffers":[{"byteLength":len(data)}],"bufferViews":views,"accessors":access}
    raw=json.dumps(doc,separators=(",",":")).encode();raw+=b" "*(-len(raw)%4);data.extend(b"\0"*(-len(data)%4))
    glb=struct.pack("<4sII",b"glTF",2,28+len(raw)+len(data))+struct.pack("<I4s",len(raw),b"JSON")+raw+struct.pack("<I4s",len(data),b"BIN\0")+data
    (out/"rigged-body.glb").write_bytes(glb)
    # Independent CPU posed mesh for visual evidence; OBJ is metric Z-up.
    obj(out/"posed-body.obj",pv[:,[0,2,1]]*np.array([1,-1,1]),f)
    (out/"fitted-rig.json").write_text(json.dumps({"axis":"Y-up, metres","bones":[{"id":n,"parent":bones[n]["parent"],"head_m":world[i,:3,3].tolist(),"tail_m":joints[bones[n]["tail"]].tolist(),"world_bind":world[i].tolist(),"inverse_bind":inv[i].tolist(),"local_bind":local[i].tolist()} for i,n in enumerate(names)],"fallback_roll_frames":fallback,"source_weights":"source/default_weights.mhw"},indent=2))
    im=Image.new("RGB",(1060,670),"#18232e");draw=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",21)
    draw.text((15,12),sex.title()+" | recovered MakeHuman animation rig, diagnostic pose",font=font,fill="white")
    scale=min(500/np.ptp(bodyv[:,0]),540/np.ptp(bodyv[:,1]))
    for i,(label,points,mat) in enumerate([("Rest / bind",bodyv,world),("30° forearm rotation",pv,posed)]):
        cx=265+i*530;cy=620;xy=np.column_stack((cx+points[:,0]*scale,cy-points[:,1]*scale))
        for tri in f:draw.polygon([tuple(xy[k]) for k in tri],fill="#516878")
        for k,n in enumerate(names):
            a=mat[k,:3,3];b=mat[k]@inv[k]@np.r_[joints[bones[n]["tail"]],1]
            draw.line((cx+a[0]*scale,cy-a[1]*scale,cx+b[0]*scale,cy-b[1]*scale),fill="#e7c58e",width=2)
        draw.text((cx-120,48),label,font=font,fill="white")
    im.save(out/"rig-preview.png")
    report={"sex":sex,"bones":N,"joints":len(joints),"weighted_visible_vertices":int((sums>0).sum()),"raw_weight_sum_max_error":float(np.max(abs(sums-1))),"top4_discarded_weight_mean":float(lost.mean()),"top4_discarded_weight_max":float(lost.max()),"fallback_roll_count":len(fallback),"pose_bone":selected,"pose_max_displacement_m":float(move.max()),"top4_vs_full_pose_rmse_mm":float(np.sqrt(np.mean(np.sum((pv-pf)**2,axis=1)))*1000),"glb_sha256":sha(glb),"status":"DONOR_RIG_DATA_RECOVERED_CPU_POSE_WITNESS","scope":"Animation rig, not anatomical bone mesh. Independent frame construction, diagnostic pose not anatomically qualified; no Blender/browser skin replay, internal bindings or native engine execution."}
    (out/"receipt.json").write_text(json.dumps(report,indent=2));print("R219_RIG",json.dumps(report))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4])
