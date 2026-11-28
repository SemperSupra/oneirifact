"""Independent diagnostic requalification of the actual CC0 donor rig.
All positive weights survive in successive glTF JOINTS_n/WEIGHTS_n sets.
Local-axis rotations are transport stress cases, not clinical joint limits.
"""
import hashlib,json,struct,sys,zipfile
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from PIL import Image,ImageDraw
PINS={"male":"6dddef415a60f44f75808962d48fd666d2da9b20d0df7d6144e18db2fa4da013","female":"5f72b2ddac947e71069b98dc77f20424ba7d2913511d8bc9e53706df8a10d94c"}
def require(x,m):
    if not x: raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def parse(b):
    magic,version,total=struct.unpack_from("<4sII",b)
    require((magic,version,total)==(b"glTF",2,len(b)),"GLB header")
    n,t=struct.unpack_from("<I4s",b,12);require(t==b"JSON","JSON chunk")
    d=json.loads(b[20:20+n]);m,t=struct.unpack_from("<I4s",b,20+n);require(t==b"BIN\0" and 28+n+m==len(b),"binary chunk")
    return d,bytearray(b[28+n:])
def read(d,b,i):
    a=d["accessors"][i];v=d["bufferViews"][a["bufferView"]];k={"SCALAR":1,"VEC3":3,"VEC4":4,"MAT4":16}[a["type"]];dt={5123:"<u2",5125:"<u4",5126:"<f4"}[a["componentType"]]
    return np.frombuffer(b,dtype=dt,count=a["count"]*k,offset=v.get("byteOffset",0)+a.get("byteOffset",0)).reshape(-1,k).copy()
def write(d,b):
    b.extend(b"\0"*(-len(b)%4));d["buffers"][0]["byteLength"]=len(b)
    raw=json.dumps(d,separators=(",",":")).encode();raw+=b" "*(-len(raw)%4)
    return struct.pack("<4sII",b"glTF",2,28+len(raw)+len(b))+struct.pack("<I4s",len(raw),b"JSON")+raw+struct.pack("<I4s",len(b),b"BIN\0")+b
def add(d,b,a,component,kind,target=None,bounds=False):
    a=np.ascontiguousarray(a);b.extend(b"\0"*(-len(b)%4));offset=len(b);b.extend(a.tobytes())
    v={"buffer":0,"byteOffset":offset,"byteLength":a.nbytes}
    if target:v["target"]=target
    i=len(d["bufferViews"]);d["bufferViews"].append(v);j=len(d["accessors"])
    ac={"bufferView":i,"componentType":component,"count":len(a),"type":kind}
    if bounds:ac.update(min=np.min(a,axis=0).reshape(-1).tolist(),max=np.max(a,axis=0).reshape(-1).tolist())
    d["accessors"].append(ac);return j
def run(archive,out,sex):
    require(sha(archive.read_bytes())==PINS[sex],"source artifact hash")
    out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        d,b=parse(z.read("rigged-body.glb"));fit=json.loads(z.read("fitted-rig.json"));ww=json.loads(z.read("source/default_weights.mhw"))
    require(ww["license"]=="CC0","weight rights")
    bones=fit["bones"];names=[x["id"] for x in bones];ix={n:i for i,n in enumerate(names)};N=len(names)
    require(N==163 and len(ix)==N and d["skins"][0]["joints"]==list(range(N)),"joint mapping")
    parents=[None if x["parent"] is None else ix[x["parent"]] for x in bones]
    require(all(p is None or p<i for i,p in enumerate(parents)),"hierarchy")
    local=np.array([x["local_bind"] for x in bones]);inv=np.array([x["inverse_bind"] for x in bones]);world=np.array([x["world_bind"] for x in bones])
    attr=d["meshes"][0]["primitives"][0]["attributes"];pos=read(d,b,attr["POSITION"]).astype(float);faces=read(d,b,d["meshes"][0]["primitives"][0]["indices"]).reshape(-1,3)
    oldids=read(d,b,attr["JOINTS_0"]);oldweights=read(d,b,attr["WEIGHTS_0"]).astype(float)
    full=np.zeros((len(pos),N))
    for n,rows in ww["weights"].items():
        require(n in ix,"unknown source bone")
        for i,w in rows:
            require(i>=0 and np.isfinite(w) and w>=0,"invalid weight")
            if i<len(pos):full[i,ix[n]]+=w
    sums=full.sum(1);require(np.min(sums)>0,"unweighted vertex");full/=sums[:,None]
    count=(full>0).sum(1);sets=int((count.max()+3)//4);require(1<=sets<=16,"influence cap")
    ids=np.argsort(-full,axis=1,kind="stable")[:,:sets*4].astype("<u2");weights=np.take_along_axis(full,ids,axis=1).astype("<f4")
    for j in range(sets):
        attr["JOINTS_"+str(j)]=add(d,b,ids[:,4*j:4*j+4],5123,"VEC4",34962)
        attr["WEIGHTS_"+str(j)]=add(d,b,weights[:,4*j:4*j+4],5126,"VEC4",34962)
    def reconstruct():
        allw=np.zeros_like(full)
        for j in range(sets):
            js=read(d,b,attr["JOINTS_"+str(j)]);ws=read(d,b,attr["WEIGHTS_"+str(j)])
            require(np.max(js)<N and np.isfinite(ws).all() and np.min(ws)>=0,"transport influences")
            np.add.at(allw,(np.arange(len(pos))[:,None],js),ws)
        return allw
    decoded=reconstruct();require(np.max(abs(decoded-full))<1e-7 and np.max(abs(decoded.sum(1)-1))<1e-7,"lost source weight")
    old=np.zeros_like(full);np.add.at(old,(np.arange(len(pos))[:,None],oldids),oldweights)
    def globals_for(l):
        g=[]
        for i,p in enumerate(parents):g.append(l[i] if p is None else g[p]@l[i])
        return np.array(g)
    require(np.max(abs(globals_for(local)-world))<1e-9,"local bind replay")
    require(np.max(abs(world@inv-np.eye(4)))<1e-9,"inverse bind replay")
    hom=np.column_stack((pos,np.ones(len(pos))))
    def skin(g,w):
        return np.einsum("vb,bjk,vk->vj",w,g@inv,hom,optimize=True)[:,:3]
    require(np.max(abs(skin(world,full)-pos))<1e-9,"rest source replay")
    require(np.max(abs(skin(world,decoded)-pos))<1e-6,"rest transport replay")
    def pick(*options):
        for n in options:
            if n in ix:return n
        raise ValueError("joint not found: "+str(options)+" available="+str(names))
    arm=pick("upperarm01.L","upperarm.L");elbow=pick("lowerarm01.L","lowerarm.L");hip=pick("upperleg01.L","thigh01.L","thigh.L","upperleg.L");knee=pick("lowerleg01.L","calf01.L","shin.L","lowerleg.L");spine=pick("spine01","spine02","spine")
    cases={"arm-reach":{arm:("z",40),elbow:("x",65)},"leg-flex":{hip:("x",35),knee:("x",70)},"combined":{arm:("z",-35),elbow:("x",85),hip:("x",30),knee:("x",55),spine:("z",18)}}
    rows=[];witness=[("Rest",pos)];d["animations"]=[]
    time=add(d,b,np.array([0,1,2],dtype="<f4"),5126,"SCALAR",bounds=True)
    for name,rot in cases.items():
        pose=local.copy();samplers=[];channels=[]
        for n,(axis,angle) in rot.items():
            i=ix[n];pose[i,:3,:3]=local[i,:3,:3]@Rotation.from_euler(axis,angle,degrees=True).as_matrix()
            quats=Rotation.from_matrix(np.array([local[i,:3,:3],pose[i,:3,:3],local[i,:3,:3]])).as_quat().astype("<f4")
            if np.dot(quats[0],quats[1])<0:quats[1]*=-1
            output=add(d,b,quats,5126,"VEC4");channels.append({"sampler":len(samplers),"target":{"node":i,"path":"rotation"}});samplers.append({"input":time,"output":output,"interpolation":"LINEAR"})
        d["animations"].append({"name":name,"channels":channels,"samplers":samplers})
        g=globals_for(pose);require(np.max(abs(np.linalg.det(g[:,:3,:3])-1))<1e-9,"rigid bone transform")
        for i,p in enumerate(parents):
            if p is not None:require(abs(np.linalg.norm(g[i,:3,3]-g[p,:3,3])-np.linalg.norm(local[i,:3,3]))<1e-9,"bone link length")
        ref=skin(g,full);new=skin(g,decoded);prev=skin(g,old)
        require(np.isfinite(new).all() and np.max(abs(new-ref))<1e-6 and np.max(abs(new-pos))>.01,"pose transport")
        def err(q):
            e=np.linalg.norm(q-ref,axis=1)*1000
            return {"rms_mm":float(np.sqrt(np.mean(e**2))),"p95_mm":float(np.quantile(e,.95)),"max_mm":float(e.max())}
        rows.append({"clip":name,"local_axis_rotations":rot,"full_transport_error":err(new),"old_top4_error":err(prev)})
        witness.append((name,new))
    # No silently dropped weights; exact raw donor data remains source authority.
    lost=1-np.sort(full,axis=1)[:,-4:].sum(1)
    outglb=write(d,b);(out/"full-influence-rig.glb").write_bytes(outglb)
    # Reparse serialized bytes and independently check all skin sets and animation outputs.
    d,b=parse(outglb);attr=d["meshes"][0]["primitives"][0]["attributes"]
    require(np.max(abs(reconstruct()-full))<1e-7 and len(d["animations"])==3,"serialized replay")
    for clip in d["animations"]:
        l=local.copy()
        for channel in clip["channels"]:
            q=read(d,b,clip["samplers"][channel["sampler"]]["output"])
            l[channel["target"]["node"],:3,:3]=Rotation.from_quat(q[1]).as_matrix()
        ref=next(p for n,p in witness if n==clip["name"])
        require(np.max(abs(skin(globals_for(l),decoded)-ref))<1e-6,"serialized animated pose replay")
    im=Image.new("RGB",(1440,570),"#26313b");draw=ImageDraw.Draw(im);scale=440/np.ptp(pos[:,1])
    for i,(name,p) in enumerate(witness):
        xy=np.column_stack((180+i*360+p[:,0]*scale,510-p[:,1]*scale))
        for tri in faces:draw.polygon([tuple(xy[k]) for k in tri],fill="#a0afb9")
        draw.text((12+i*360,10),sex+" / "+name,fill="white")
    im.save(out/"pose-witness.png")
    result={"status":"PASS_FULL_INFLUENCE_CPU_TRANSPORT","sex":sex,"source_artifact_sha256":PINS[sex],"joints":N,"vertices":len(pos),"max_influences":int(count.max()),"glTF_weight_sets":sets,"vertices_over_four":int((count>4).sum()),"old_top4_max_discarded_mass":float(lost.max()),"clips":rows,"glb_sha256":sha(outglb),"limitations":"CPU transport only. Multi-set consumer support, donor runtime equivalence, anatomical range of motion, collisions, skin realism and internal tissues not qualified."}
    (out/"receipt.json").write_text(json.dumps(result,indent=2)+"\n");print("R239_RIG",json.dumps(result),flush=True)
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
