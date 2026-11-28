"""Cross-donor female lower-limb registration candidate, same rig for skin and bones.
Exact R239 artifacts; segmentwise similarities preserve shape but do NOT establish
anatomical identity, physiological pivots, joint contact, or patient fit.
"""
import hashlib,io,json,struct,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from PIL import Image,ImageDraw,ImageFont
SKIN="f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f"
CT="f9e0e39a5591705aa73509e4239a4a9652d57fe3bdbb010b120b5366443ede8a"
def need(q,m):
    if not q:raise ValueError(m)
def sha(x):return hashlib.sha256(x).hexdigest()
def glb(raw):
    tag,ver,total=struct.unpack_from("<4sII",raw);need((tag,ver,total)==(b"glTF",2,len(raw)),"GLB")
    n,tag=struct.unpack_from("<I4s",raw,12);need(tag==b"JSON","JSON")
    s,tag=struct.unpack_from("<I4s",raw,20+n);need(tag==b"BIN\0" and 28+n+s==len(raw),"BIN")
    return json.loads(raw[20:20+n]),bytearray(raw[28+n:])
def read(d,b,i):
    a=d["accessors"][i];v=d["bufferViews"][a["bufferView"]]
    need("byteStride" not in v and "sparse" not in a,"accessor layout")
    k={"SCALAR":1,"VEC3":3,"VEC4":4,"MAT4":16}[a["type"]];dt={5123:"<u2",5125:"<u4",5126:"<f4"}[a["componentType"]]
    return np.frombuffer(b,dtype=dt,count=a["count"]*k,offset=v.get("byteOffset",0)+a.get("byteOffset",0)).copy().reshape(-1,k)
def add(d,b,a,component,kind,target=None,bounds=False):
    a=np.ascontiguousarray(a);b.extend(b"\0"*(-len(b)%4));offset=len(b);b.extend(a.tobytes())
    v={"buffer":0,"byteOffset":offset,"byteLength":a.nbytes}
    if target:v["target"]=target
    i=len(d["bufferViews"]);d["bufferViews"].append(v);j=len(d["accessors"])
    r={"bufferView":i,"componentType":component,"count":len(a),"type":kind}
    if bounds:r.update(min=a.min(0).reshape(-1).tolist(),max=a.max(0).reshape(-1).tolist())
    d["accessors"].append(r);return j
def encode(d,b):
    b.extend(b"\0"*(-len(b)%4));d["buffers"][0]["byteLength"]=len(b)
    j=json.dumps(d,separators=(",",":")).encode();j+=b" "*(-len(j)%4)
    return struct.pack("<4sII",b"glTF",2,28+len(j)+len(b))+struct.pack("<I4s",len(j),b"JSON")+j+struct.pack("<I4s",len(b),b"BIN\0")+b
def xform(v,m):return v@m[:3,:3].T+m[:3,3]
def similarity(a,b,c,d):
    u=b-a;v=d-c;su=np.linalg.norm(u);sv=np.linalg.norm(v)
    need(su>.03 and sv>.03,"invalid landmark baseline")
    R=Rotation.align_vectors([v/sv],[u/su])[0].as_matrix();M=np.eye(4);M[:3,:3]=R*sv/su;M[:3,3]=c-M[:3,:3]@a
    need(np.linalg.norm(xform(a[None,:],M)[0]-c)<1e-9 and np.linalg.norm(xform(b[None,:],M)[0]-d)<1e-9,"endpoint fit")
    return M,float(sv/su)
def metrics(mesh,points):
    # Multi-direction parity screen on deterministic sample points. Non-watertight
    # skin and inconsistent rays are explicitly diagnostic, never accepted as proof.
    hits=[]
    for vector in ([1,.071,.023],[-.13,.039,1],[.09,1,.127]):
        dirs=np.repeat(np.array(vector,float)[None,:],len(points),axis=0)
        loc,ray,tri=mesh.ray.intersects_location(points,dirs,multiple_hits=True)
        hits.append(np.bincount(ray,minlength=len(points))%2==1)
    votes=np.array(hits).sum(0)
    return {"samples":len(points),"all_three_inside":int((votes==3).sum()),"all_three_outside":int((votes==0).sum()),"disagreement":int(((votes>0)&(votes<3)).sum())}
def main(skinzip,ctzip,out):
    need(sha(skinzip.read_bytes())==SKIN and sha(ctzip.read_bytes())==CT,"archive pin")
    out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(skinzip) as z,zipfile.ZipFile(ctzip) as cz:
        raw=z.read("female-athletic-animated.glb");r=json.loads(z.read("receipt.json"));need(sha(raw)==next(x["glb_sha256"] for x in r["variants"] if x["id"]=="female-athletic"),"skin pin")
        d,b=glb(raw);fit=json.loads(z.read("female-athletic-rig.json"));cpu=np.load(io.BytesIO(z.read("female-athletic-cpu-reference.npz")));frames=cpu["frames"];faces=cpu["faces"]
        for n in ("LICENSE.md","LICENSE.ASSETS.md"):(out/n).write_bytes(z.read(n))
        ct=cz.read("female-ct-leg-animation.glb");cr=json.loads(cz.read("receipt.json"));need(sha(ct)==cr["models"]["animated"],"CT pin")
        scene=trimesh.load(io.BytesIO(ct),file_type="glb",force="scene",process=False)
        (out/"ATTRIBUTION.txt").write_bytes(cz.read("ATTRIBUTION.txt")+b"\nR240 changes: segmentwise isotropic cross-donor registration, rigidly attached to animation rig. Candidate only; no clinical claim.\n")
    bones=fit["bones"];names=[x["id"] for x in bones];ix={n:i for i,n in enumerate(names)}
    need(len(ix)==163 and all(d["nodes"][i]["name"]==n for i,n in enumerate(names)),"rig identity")
    world=np.array([x["world_bind"] for x in bones]);inv=np.array([x["inverse_bind"] for x in bones]);parents=[-1 if x["parent"] is None else ix[x["parent"]] for x in bones]
    def joint(n):return world[ix[n],:3,3]
    def cjoint(n):return np.array(scene.graph.get(n)[0])[:3,3]
    def original(suffix):
        key=next(n for n in scene.graph.nodes_geometry if n.endswith("_"+suffix))
        m,g=scene.graph[key];mesh=scene.geometry[g].copy();mesh.apply_transform(m);return key,mesh
    # The CT pivots are provisional R239 surface candidates. The ankle is a
    # distal tibial centroid proxy, not an independently qualified landmark.
    h={s:cjoint("thigh_"+s) for s in ("L","R")};k={s:cjoint("shin_"+s) for s in ("L","R")}
    pelvisM,ps=similarity(h["R"],h["L"],joint("upperleg01.R"),joint("upperleg01.L"))
    records=[];groups=[]
    def attach(suffix,owner,M,scale,region):
        name,src=original(suffix);mapped=xform(src.vertices,M);local=xform(mapped,inv[ix[owner]])
        # Preserve every triangle and isotropic edge ratios before serialization.
        f=src.faces;edge=f[:min(len(f),4096),:2];v0=np.linalg.norm(src.vertices[edge[:,0]]-src.vertices[edge[:,1]],axis=1);v1=np.linalg.norm(mapped[edge[:,0]]-mapped[edge[:,1]],axis=1)
        need(np.max(abs(v1-v0*scale))<1e-9,"nonuniform shape deformation")
        i=add(d,b,local.astype("<f4"),5126,"VEC3",34962,True);j=add(d,b,f.astype("<u4").ravel(),5125,"SCALAR",34963)
        mi=len(d["meshes"]);d["meshes"].append({"name":name,"primitives":[{"attributes":{"POSITION":i},"indices":j,"material":1}]})
        ni=len(d["nodes"]);d["nodes"].append({"name":"CT_"+name,"mesh":mi});d["nodes"][ix[owner]].setdefault("children",[]).append(ni)
        groups.append((name,owner,mapped,f,ni));records.append({"source":name,"owner":owner,"region":region,"scale":scale,"vertices":len(mapped),"triangles":len(f),"source_to_rig":M.tolist()})
    d["materials"][0]["alphaMode"]="BLEND";d["materials"][0]["doubleSided"]=False;d["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"]=[.57,.69,.78,.22]
    d["materials"].append({"name":"CT bone candidate","pbrMetallicRoughness":{"baseColorFactor":[.92,.82,.62,1],"metallicFactor":0,"roughnessFactor":.85}})
    attach("HIP_LEFT","root",pelvisM,ps,"pelvis");attach("HIP_RIGHT","root",pelvisM,ps,"pelvis");attach("SACRUM","root",pelvisM,ps,"pelvis")
    fits=[]
    for s,side in (("L","LEFT"),("R","RIGHT")):
        thigh="upperleg01."+s;shin="lowerleg01."+s;foot="foot."+s
        _,tib=original("TIBIA_"+side);v=tib.vertices
        distal=v[v[:,1]<=v[:,1].min()+.015];need(len(distal)>10,"ankle proxy samples");ankle=distal.mean(0)
        t,ts=similarity(h[s],k[s],joint(thigh),joint(shin));q,qs=similarity(k[s],ankle,joint(shin),joint(foot))
        attach("FEMUR_"+side,thigh,t,ts,"thigh");attach("TIBIA_"+side,shin,q,qs,"shin");attach("FIBULA_"+side,shin,q,qs,"shin")
        fits.append({"side":s,"global_knee_mismatch_mm":float(np.linalg.norm(xform(k[s][None,:],pelvisM)[0]-joint(shin))*1000),"global_ankle_proxy_mismatch_mm":float(np.linalg.norm(xform(ankle[None,:],pelvisM)[0]-joint(foot))*1000),"thigh_scale":ts,"shin_scale":qs,"ankle_source_proxy_m":ankle.tolist()})
    # Keep skin's original three influence sets, all animation channels and bind matrices.
    packed=encode(d,b);(out/"female-athletic-ct-candidate.glb").write_bytes(packed)
    dd,bb=glb(packed);channels=dd["animations"][0]["channels"];samplers=dd["animations"][0]["samplers"]
    rotations={c["target"]["node"]:read(dd,bb,samplers[c["sampler"]]["output"]) for c in channels}
    def globals_at(k):
        mats=[]
        for i,n in enumerate(dd["nodes"][:163]):
            m=np.eye(4);m[:3,:3]=Rotation.from_quat(rotations[i][k] if i in rotations else n["rotation"]).as_matrix();m[:3,3]=n["translation"]
            mats.append(m if parents[i]<0 else mats[parents[i]]@m)
        return np.array(mats)
    reports=[];visual=[];maxerr=0.
    for frame in (0,1,2):
        g=globals_at(frame);skin=trimesh.Trimesh(vertices=frames[frame],faces=faces,process=False);views=[]
        for name,owner,mapped,f,ni in groups:
            j=ix[owner];p=dd["meshes"][dd["nodes"][ni]["mesh"]]["primitives"][0]
            v=read(dd,bb,p["attributes"]["POSITION"]);actual=xform(v,g[j]);expected=xform(mapped,g[j]@inv[j])
            maxerr=max(maxerr,float(np.max(np.linalg.norm(actual-expected,axis=1))))
            views.append((name,actual))
            take=np.linspace(0,len(actual)-1,min(256,len(actual)),dtype=int)
            reports.append({"frame":frame,"bone":name,**metrics(skin,actual[take])})
        visual.append((frame,views))
    need(maxerr<2e-6,"serialized rigid geometry replay")
    # Draw actual projected skin triangles and actual CT vertices, four fixed
    # views in the same coordinate system. Not a synthetic human illustration.
    im=Image.new("RGB",(1440,1000),"#16212b");draw=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",22)
    draw.text((18,12),"Female athletic skin + actual CT bone candidates | cross-donor, NOT anatomically admitted",font=font,fill="white")
    for col,(frame,views) in enumerate(visual[:2]):
        for row,(axis,label) in enumerate(((0,"Front"),(2,"Side"))):
            cx=360+720*col;cy=485+480*row;scale=238
            def project(v):return np.column_stack((cx+v[:,axis]*scale,cy-v[:,1]*scale))
            xy=project(frames[frame]);draw.text((24+720*col,50+480*row),("Rest" if frame==0 else "Diagnostic pose")+" / "+label,font=font,fill="white")
            for f in faces:draw.polygon([tuple(xy[i]) for i in f],fill="#566e7e")
            for name,v in views:
                q=project(v[::max(1,len(v)//10000)]);draw.point([tuple(x) for x in q],fill="#f5d9a1" if "HIP_" in name or "SACRUM" in name else "#ffe4b3")
    im.save(out/"registered-ct-skin-witness.png")
    receipt={"status":"HOLD_CROSS_DONOR_ANATOMICAL_ADMISSION","input_sha256":{"skin":SKIN,"ct":CT},"skin_vertices":int(frames.shape[1]),"skin_watertight":bool(trimesh.Trimesh(vertices=frames[0],faces=faces,process=False).is_watertight),"bones":records,"fit":fits,"ray_parity":reports,"serialized_bone_max_error_m":maxerr,"glb_sha256":sha(packed),"scope":"Actual female CT pelvis/femur/tibia/fibula geometry carried by the same full-weight animation rig as the athletic exterior. Similarity fit is cross-donor candidate only. Hip/knee landmarks provisional; ankle centroid proxy, no cartilage, physiological limits, contact, internal tissue or native qualification. Three-direction ray parity is a containment screen, not proof."}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print("R240_CT_SKIN",json.dumps({k:v for k,v in receipt.items() if k!="bones"},sort_keys=True),flush=True)
if __name__=="__main__":main(*(Path(x) for x in sys.argv[1:]))
