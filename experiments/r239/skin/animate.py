"""Actual shared adult donor meshes, complete skin weights, and editable animation.
Diagnostic motion, not anatomical joint-limit, skin contact or tissue qualification.
"""
import hashlib,json,struct,sys,zipfile,tempfile
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"r217"))
from human_inverse import base,blob
SOURCE="025145c2af4dc0c0d8936e764b88dd03a06a9e389197cadf97eb9b1d634d54fc"
RIG="98f119556087dddfce98028501fe459b61c746f0094cf0e09c6b7f0dc7461e49"
def need(q,msg):
    if not q:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def readglb(raw):
    magic,ver,total=struct.unpack_from("<4sII",raw);need(magic==b"glTF" and ver==2 and total==len(raw),"GLB header")
    n,tag=struct.unpack_from("<I4s",raw,12);need(tag==b"JSON","GLB JSON")
    doc=json.loads(raw[20:20+n]);size,tag=struct.unpack_from("<I4s",raw,20+n);need(tag==b"BIN\0" and 28+n+size==len(raw),"GLB BIN")
    return doc,raw[28+n:]
def accessor(doc,b,i):
    a=doc["accessors"][i];v=doc["bufferViews"][a["bufferView"]];need("byteStride" not in v and "sparse" not in a,"unexpected accessor")
    dt={5123:"<u2",5125:"<u4",5126:"<f4"}[a["componentType"]];cols={"SCALAR":1,"VEC3":3,"VEC4":4,"MAT4":16}[a["type"]]
    return np.frombuffer(b,dtype=dt,count=a["count"]*cols,offset=v.get("byteOffset",0)+a.get("byteOffset",0)).copy().reshape(-1,cols)
def main(src,rigsrc,out):
    need(sha(src.read_bytes())==SOURCE and sha(rigsrc.read_bytes())==RIG,"archive digest")
    out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(src) as z,zipfile.ZipFile(rigsrc) as rz,tempfile.TemporaryDirectory() as td:
        root=Path(td)
        (root/"base.obj").write_bytes(rz.read("source/base.obj"));_,f,_=base(root/"base.obj")
        raw=rz.read("source/default_weights.mhw");need(blob(raw)=="66185806afacf87749be8e5cf6dbf66496b2a6b0","weight pin")
        ww=json.loads(raw);need(ww["license"]=="CC0","weight rights")
        for n in ("LICENSE.md","LICENSE.ASSETS.md"):(out/n).write_bytes(rz.read("source/"+n))
        receipt=json.loads(z.read("receipt.json"));reports=[]
        for sex in ("male","female"):
            name=sex+"-athletic";rr=next(r for r in receipt["variants"] if r["id"]==name);raw=z.read(name+".glb")
            need(sha(raw)==rr["model"]["sha256"],"source mesh hash");g,b=readglb(raw);p=g["meshes"][0]["primitives"][0]
            verts=accessor(g,b,p["attributes"]["POSITION"]).astype(float);faces=accessor(g,b,p["indices"]).reshape(-1,3)
            # Base face order and indexed corners establish weight correspondence.
            need(verts.shape==(13380,3) and np.array_equal(faces,f),"vertex identity / topology")
            rr=json.loads(z.read(name+"-rig.json"));bones=rr["bones"];names=[b["id"] for b in bones];ix={n:i for i,n in enumerate(names)}
            need(len(ix)==163 and rr["joints"]==326,"rig identity")
            world=np.array([x["world_bind"] for x in bones]);inv=np.array([x["inverse_bind"] for x in bones]);local=np.array([x["local_bind"] for x in bones])
            parent=[-1 if x["parent"] is None else ix[x["parent"]] for x in bones]
            need(all(p<i for i,p in enumerate(parent)) and parent.count(-1)==1,"hierarchy")
            need(np.max(abs(world@inv-np.eye(4)))<1e-10,"bind inverse")
            full=np.zeros((len(verts),len(bones)))
            for n,rows in ww["weights"].items():
                for i,w in rows:
                    if i<len(verts):full[i,ix[n]]+=w
            need(np.isfinite(full).all() and np.min(full)>=0 and np.min(full.sum(1))>0,"weights")
            full/=full.sum(1)[:,None];counts=np.sum(full>0,axis=1);need(counts.max()==9,"source influence inventory")
            ids=np.argsort(-full,axis=1,kind="stable")[:,:12];weights=np.take_along_axis(full,ids,axis=1)
            need(np.max(abs(weights.sum(1)-1))<1e-12,"complete weights")
            top4=weights[:,:4];lost=1-top4.sum(1)
            hom=np.column_stack((verts,np.ones(len(verts))))
            def pose(angles):
                lp=local.copy()
                for n,(axis,deg) in angles.items():
                    i=ix[n];a=world[i,:3,:3].T@np.array(axis,float)
                    lp[i,:3,:3]=lp[i,:3,:3]@Rotation.from_rotvec(a*np.radians(deg)).as_matrix()
                posed=[]
                for i,p in enumerate(parent):posed.append(lp[i] if p<0 else posed[p]@lp[i])
                return lp,np.array(posed)
            # Symmetric diagnostic arm and leg movements. World rest axes,
            # no assertion of anatomical axes, physiological range or contact.
            actions=[{},{"upperarm01.L":([0,0,1],-20),"upperarm01.R":([0,0,1],20),"lowerarm01.L":([0,1,0],-30),"lowerarm01.R":([0,1,0],30),"upperleg01.L":([1,0,0],-18),"lowerleg01.L":([1,0,0],32),"spine03":([1,0,0],7)},{}]
            times=np.array([0,1,2],dtype="<f4")
            frames=[pose(a) for a in actions];cpu=[];error=[]
            for lp,mat in frames:
                trans=mat@inv
                v=np.einsum("vb,bjk,vk->vj",full,trans,hom)[:,:3];cpu.append(v)
                limited=np.einsum("vi,vijk,vk->vj",top4/top4.sum(1)[:,None],trans[ids[:,:4]],hom)[:,:3]
                error.append(float(np.max(np.linalg.norm(v-limited,axis=1))))
            need(np.max(abs(cpu[0]-verts))<1e-9 and np.array_equal(cpu[0],cpu[2]) and np.max(abs(cpu[1]-verts))>.01,"pose witness")
            # Full multi-set glTF transport: preserve all nine positive influences,
            # leave unused slots zero. Explicit float32 import parity is checked.
            data=bytearray();views=[];acc=[]
            def add(a,component,kind,target=None,bounds=False):
                a=np.ascontiguousarray(a);data.extend(b"\0"*(-len(data)%4));offset=len(data);data.extend(a.tobytes())
                view={"buffer":0,"byteOffset":offset,"byteLength":a.nbytes}
                if target:view["target"]=target
                v=len(views);views.append(view);entry={"bufferView":v,"componentType":component,"count":len(a),"type":kind}
                if bounds:entry.update(min=np.min(a,axis=0).reshape(-1).tolist(),max=np.max(a,axis=0).reshape(-1).tolist())
                k=len(acc);acc.append(entry);return k
            normal=np.zeros_like(verts);tri=verts[faces];n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
            for i in range(3):np.add.at(normal,faces[:,i],n)
            norm=np.linalg.norm(normal,axis=1);need((norm>0).all(),"invalid normals");normal/=norm[:,None]
            attrs={"POSITION":add(verts.astype("<f4"),5126,"VEC3",34962,True),"NORMAL":add(normal.astype("<f4"),5126,"VEC3",34962)}
            inds=add(faces.astype("<u4").ravel(),5125,"SCALAR",34963)
            for i in range(3):
                attrs["JOINTS_"+str(i)]=add(ids[:,4*i:4*i+4].astype("<u2"),5123,"VEC4",34962)
                attrs["WEIGHTS_"+str(i)]=add(weights[:,4*i:4*i+4].astype("<f4"),5126,"VEC4",34962)
            ib=add(inv.transpose(0,2,1).astype("<f4").reshape(-1,16),5126,"MAT4")
            time=add(times,5126,"SCALAR",bounds=True)
            nodes=[]
            for i,n in enumerate(names):
                node={"name":n,"translation":local[i,:3,3].tolist(),"rotation":Rotation.from_matrix(local[i,:3,:3]).as_quat().tolist()}
                children=[k for k,p in enumerate(parent) if p==i]
                if children:node["children"]=children
                nodes.append(node)
            nodes.append({"name":"adult_skin","mesh":0,"skin":0})
            samplers=[];channels=[]
            for n in actions[1]:
                i=ix[n];q=np.array([Rotation.from_matrix(lp[i,:3,:3]).as_quat() for lp,mat in frames])
                for j in range(1,len(q)):
                    if np.dot(q[j-1],q[j])<0:q[j]*=-1
                a=add(q.astype("<f4"),5126,"VEC4")
                channels.append({"sampler":len(samplers),"target":{"node":i,"path":"rotation"}});samplers.append({"input":time,"output":a,"interpolation":"LINEAR"})
            doc={"asset":{"version":"2.0","generator":"Oneirifact R239 full donor skin weights"},"scene":0,"scenes":[{"nodes":[parent.index(-1),len(nodes)-1]}],"nodes":nodes,"meshes":[{"primitives":[{"attributes":attrs,"indices":inds,"material":0}]}],"materials":[{"doubleSided":True,"pbrMetallicRoughness":{"baseColorFactor":[.65,.72,.76,1],"metallicFactor":0,"roughnessFactor":.9}}],"skins":[{"joints":list(range(len(bones))),"skeleton":parent.index(-1),"inverseBindMatrices":ib}],"animations":[{"name":"Diagnostic coordinated motion","samplers":samplers,"channels":channels}],"buffers":[{"byteLength":len(data)}],"bufferViews":views,"accessors":acc}
            js=json.dumps(doc,separators=(",",":")).encode();js+=b" "*(-len(js)%4);data.extend(b"\0"*(-len(data)%4))
            glb=struct.pack("<4sII",b"glTF",2,28+len(js)+len(data))+struct.pack("<I4s",len(js),b"JSON")+js+struct.pack("<I4s",len(data),b"BIN\0")+data
            (out/(name+"-animated.glb")).write_bytes(glb)
            # Re-read actual transport independently, reconstruct from GLB hierarchy,
            # rotation tracks, inverse binds, and all packed weights.
            dd,bb=readglb(glb);pa=dd["meshes"][0]["primitives"][0]["attributes"]
            vi=accessor(dd,bb,pa["POSITION"]);jj=np.concatenate([accessor(dd,bb,pa["JOINTS_"+str(i)]) for i in range(3)],axis=1)
            ww2=np.concatenate([accessor(dd,bb,pa["WEIGHTS_"+str(i)]) for i in range(3)],axis=1);ib2=accessor(dd,bb,dd["skins"][0]["inverseBindMatrices"]).reshape(-1,4,4).transpose(0,2,1)
            need(np.array_equal(jj,ids) and np.max(abs(ww2.sum(1)-1))<2e-7 and np.sum(ww2>0)==np.sum(full>0),"packed weight retention")
            angles={c["target"]["node"]:accessor(dd,bb,dd["animations"][0]["samplers"][c["sampler"]]["output"]) for c in dd["animations"][0]["channels"]}
            errs=[];hh=np.column_stack((vi,np.ones(len(vi))))
            for k in range(3):
                mats=[]
                for i,node in enumerate(dd["nodes"][:-1]):
                    mat=np.eye(4);mat[:3,:3]=Rotation.from_quat(angles[i][k] if i in angles else node["rotation"]).as_matrix();mat[:3,3]=node["translation"]
                    mats.append(mat if parent[i]<0 else mats[parent[i]]@mat)
                tr=np.array(mats)@ib2
                result=np.einsum("vi,vijk,vk->vj",ww2,tr[jj],hh)[:,:3]
                err=float(np.max(np.linalg.norm(result-cpu[k],axis=1)));need(err<2e-6,"GLB numeric pose replay");errs.append(err)
            # Independent native consumer compares these world coordinates, not
            # a static screenshot or exporter metadata.
            np.savez_compressed(out/(name+"-cpu-reference.npz"),frames=np.array(cpu),faces=faces,times=times)
            (out/(name+"-source-spec.json")).write_bytes(z.read(name+"-spec.json"));(out/(name+"-rig.json")).write_bytes(z.read(name+"-rig.json"))
            reports.append({"id":name,"vertices":len(verts),"triangles":len(faces),"bones":len(bones),"max_influences":int(counts.max()),"vertices_over_four":int(np.sum(counts>4)),"positive_influences":int(np.sum(counts)),"top4_discarded_max":float(lost.max()),"top4_pose_max_error_m":max(error),"full_glb_replay_max_m":max(errs),"animation_channels":len(channels),"glb_sha256":sha(glb),"status":"PASS_FULL_WEIGHT_TRANSPORT_CPU"})
        report={"source_archive_sha256":SOURCE,"rig_archive_sha256":RIG,"variants":reports,"scope":"Actual adult exterior donor mesh and refitted rig, full weight glTF 3 sets, diagnostic motion. Internal anatomy, physiological axes, collision, tissue mechanics and native Foundry not qualified."}
        (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
        print("R239_FULL_WEIGHT_ANIMATION",json.dumps(report),flush=True)
if __name__=="__main__":main(*(Path(x) for x in sys.argv[1:]))
