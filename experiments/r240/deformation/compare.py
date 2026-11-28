"""Actual donor skin deformation bakeoff. Compare linear blend and normalized
dual quaternion skinning using identical full-weight GLB transforms.
Quantitative stress metrics are not anatomical or perceptual acceptance.
"""
import hashlib,io,json,struct,sys,zipfile
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation,Slerp
from PIL import Image,ImageDraw,ImageFont
PIN="f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f"
def need(q,m):
    if not q:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def glb(raw):
    magic,v,total=struct.unpack_from("<4sII",raw);need((magic,v,total)==(b"glTF",2,len(raw)),"GLB header")
    n,t=struct.unpack_from("<I4s",raw,12);need(t==b"JSON","JSON");d=json.loads(raw[20:20+n]);s,t=struct.unpack_from("<I4s",raw,20+n);need(t==b"BIN\0" and 28+n+s==len(raw),"BIN");return d,raw[28+n:]
def read(d,b,i):
    a=d["accessors"][i];v=d["bufferViews"][a["bufferView"]];need("byteStride" not in v and "sparse" not in a,"accessor layout")
    k={"SCALAR":1,"VEC3":3,"VEC4":4,"MAT4":16}[a["type"]];dt={5123:"<u2",5125:"<u4",5126:"<f4"}[a["componentType"]]
    return np.frombuffer(b,dtype=dt,count=a["count"]*k,offset=v.get("byteOffset",0)+a.get("byteOffset",0)).copy().reshape(-1,k)
def mul(a,b):
    av,aw=a[...,:3],a[...,3:4];bv,bw=b[...,:3],b[...,3:4]
    return np.concatenate((aw*bv+bw*av+np.cross(av,bv),aw*bw-np.sum(av*bv,axis=-1,keepdims=True)),axis=-1)
def conj(q):return q*np.array([-1,-1,-1,1])
def dqs(v,ids,weights,m):
    # Rigid skin transforms only. Align antipodal quaternion signs to the
    # first (highest-weight) influence before blending real and dual parts.
    r=Rotation.from_matrix(m[:,:3,:3]).as_quat();t=np.column_stack((m[:,:3,3],np.zeros(len(m))))
    dual=.5*mul(t,r);q=r[ids];qd=dual[ids];sign=np.where(np.sum(q*q[:,:1,:],axis=-1)<0,-1.,1.)
    w=weights*sign;a=np.sum(q*w[:,:,None],axis=1);b=np.sum(qd*w[:,:,None],axis=1)
    n=np.linalg.norm(a,axis=1);need(np.min(n)>1e-6,"degenerate blend");a/=n[:,None];b/=n[:,None]
    b-=np.sum(a*b,axis=1)[:,None]*a
    translation=2*mul(b,conj(a))[:,:3]
    return Rotation.from_quat(a).apply(v)+translation
def lbs(v,ids,w,m):
    return np.einsum("vi,vijk,vk->vj",w,m[ids],np.column_stack((v,np.ones(len(v)))))[:,:3]
def stats(v,f,edges,l0,area0):
    length=np.linalg.norm(v[edges[:,0]]-v[edges[:,1]],axis=1);ratio=length/l0;log=np.abs(np.log(np.maximum(ratio,1e-12)))
    tri=v[f];area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2;ar=area/area0
    return {"edge_log_strain_median":float(np.median(log)),"edge_log_strain_p95":float(np.quantile(log,.95)),"edge_log_strain_p99":float(np.quantile(log,.99)),"edge_ratio_min":float(ratio.min()),"edge_ratio_max":float(ratio.max()),"edge_over_25pct":int(np.sum((ratio<.75)|(ratio>1.25))),"triangles_below_10pct_area":int(np.sum(ar<.1)),"triangles_above_2x_area":int(np.sum(ar>2))}
def write_obj(path,v,f):
    with path.open("w") as o:
        for x in v:o.write("v %.9g %.9g %.9g\n"%tuple(x))
        for x in f:o.write("f %d %d %d\n"%tuple(x+1))
def image(out,sex,v,f,area0,results):
    im=Image.new("RGB",(1200,720),"#18242f");draw=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",23)
    draw.text((16,12),sex.title()+" | actual surface deformation at diagnostic pose",font=font,fill="white")
    draw.text((16,46),"Triangle area ratio: blue compressed, grey stable, orange expanded",font=font,fill="#b6c4d0")
    scale=545/np.ptp(v[:,1])
    for col,(label,p) in enumerate(results):
        cx=300+col*600;cy=675;tri=p[f];a=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
        z=tri[:,:,2].mean(1);ratio=a/area0;xy=np.column_stack((cx+(p[:,0]-.35*p[:,2])*scale,cy-p[:,1]*scale))
        draw.text((cx-145,90),label,font=font,fill="white")
        for i in np.argsort(z):
            s=np.clip(np.log(max(ratio[i],1e-8))/.7,-1,1);base=np.array([150,164,174]);goal=np.array([238,126,61]) if s>=0 else np.array([55,125,219]);color=tuple(np.round(base*(1-abs(s))+goal*abs(s)).astype(int))
            draw.polygon([tuple(xy[j]) for j in f[i]],fill=color)
    im.save(out/(sex+"-deformation-comparison.png"))
def run(src,out):
    need(sha(src.read_bytes())==PIN,"exact source pin");out.mkdir(parents=True,exist_ok=False)
    report=[]
    with zipfile.ZipFile(src) as z:
        r=json.loads(z.read("receipt.json"))
        for license in ("LICENSE.md","LICENSE.ASSETS.md"):(out/license).write_bytes(z.read(license))
        for sex in ("male","female"):
            name=sex+"-athletic";raw=z.read(name+"-animated.glb");need(sha(raw)==next(x["glb_sha256"] for x in r["variants"] if x["id"]==name),"GLB source pin")
            d,b=glb(raw);p=d["meshes"][0]["primitives"][0];at=p["attributes"]
            v=read(d,b,at["POSITION"]).astype(float);f=read(d,b,p["indices"]).reshape(-1,3)
            ids=np.concatenate([read(d,b,at["JOINTS_"+str(i)]) for i in range(3)],axis=1);w=np.concatenate([read(d,b,at["WEIGHTS_"+str(i)]) for i in range(3)],axis=1).astype(float)
            need(np.max(abs(w.sum(1)-1))<2e-7 and np.min(w)>=0 and np.sum(w>0)==40156,"weight inventory");w/=w.sum(1)[:,None]
            inv=read(d,b,d["skins"][0]["inverseBindMatrices"]).reshape(-1,4,4).transpose(0,2,1).astype(float)
            N=len(inv);parent=[-1]*N
            for i,n in enumerate(d["nodes"][:N]):
                for j in n.get("children",[]):
                    if j<N:parent[j]=i
            need(all(j<i for i,j in enumerate(parent)) and parent.count(-1)==1,"hierarchy")
            a=d["animations"][0];tracks={}
            for c in a["channels"]:
                s=a["samplers"][c["sampler"]];times=read(d,b,s["input"]).ravel();q=read(d,b,s["output"]);tracks[c["target"]["node"]]=Slerp(times,Rotation.from_quat(q))
            edges=np.unique(np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1),axis=0)
            l0=np.linalg.norm(v[edges[:,0]]-v[edges[:,1]],axis=1);tri=v[f];area0=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
            need(np.min(l0)>1e-10 and np.min(area0)>1e-12,"degenerate source topology")
            ref=np.load(io.BytesIO(z.read(name+"-cpu-reference.npz")))["frames"];rows=[]
            # Single rigid transform and antipodal representation invariance.
            test=np.repeat(np.eye(4)[None],N,axis=0);test[:,:3,:3]=Rotation.from_euler("xyz",[15,35,10],degrees=True).as_matrix();test[:,:3,3]=[.02,-.03,.01]
            expected=v@test[0,:3,:3].T+test[0,:3,3];need(np.max(abs(dqs(v,ids,w,test)-expected))<1e-9,"rigid DQS oracle")
            for t in np.linspace(0,2,9):
                g=[]
                for i,n in enumerate(d["nodes"][:N]):
                    m=np.eye(4);m[:3,:3]=(tracks[i](t) if i in tracks else Rotation.from_quat(n["rotation"])).as_matrix();m[:3,3]=n["translation"];g.append(m if parent[i]<0 else g[parent[i]]@m)
                m=np.array(g)@inv;need(np.max(abs(np.linalg.det(m[:,:3,:3])-1))<1e-6,"nonrigid source transforms")
                l=lbs(v,ids,w,m);q=dqs(v,ids,w,m);need(np.isfinite(l).all() and np.isfinite(q).all(),"nonfinite deformation")
                if t in (0,1,2):need(np.max(abs(l-ref[int(t)]))<2e-6,"LBS reference parity")
                if t in (0,2):need(np.max(abs(q-v))<2e-6,"DQS rest replay")
                delta=np.linalg.norm(l-q,axis=1)
                rows.append({"time_s":float(t),"lbs":stats(l,f,edges,l0,area0),"dqs":stats(q,f,edges,l0,area0),"between_methods_max_mm":float(delta.max()*1000)})
                if t==1:
                    write_obj(out/(sex+"-lbs-posed.obj"),l,f);write_obj(out/(sex+"-dqs-posed.obj"),q,f)
                    image(out,sex,v,f,area0,[("Linear blend",l),("Dual quaternion",q)])
            report.append({"sex":sex,"vertices":len(v),"edges":len(edges),"triangles":len(f),"samples":rows})
    receipt={"status":"PASS_DIAGNOSTIC_BAKEOFF_HOLD_DEFORMATION_ADMISSION","source_sha256":PIN,"variants":report,"scope":"Identical actual full-weight source and rigid animated transforms. Edge/triangle distortion and rigid/rest oracles only. DQS is CPU candidate; no clinical muscle mechanics, collision, physiological motion, glTF DQS transport or perceptual superiority claim."}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print("R240_SKIN_DEFORMATION",json.dumps({"status":receipt["status"],"peak":[{"sex":x["sex"],**x["samples"][4]} for x in report]},sort_keys=True),flush=True)
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
