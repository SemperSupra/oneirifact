"""Same-donor female CT hip/knee articulation diagnostic.
Actual source meshes, provisional surface-derived pivots, no cross-donor fusion.
Joint contact, patellar tracking and physiological axes remain unqualified.
"""
import hashlib,io,json,struct,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from PIL import Image,ImageDraw,ImageFont
PIN="6ebcae2937da21450e7f536ceb92d91e96a422862e80320476e7c1d6ef08ee27"
def need(x,msg):
    if not x:raise ValueError(msg)
def sha(x):return hashlib.sha256(x).hexdigest()
def sphere(points):
    need(len(points)>100,"patch too small")
    center=points.mean(0);q=points-center
    A=np.column_stack((2*q,np.ones(len(q))));x=np.linalg.lstsq(A,np.sum(q*q,axis=1),rcond=None)[0]
    c=x[:3]+center;radius=np.sqrt(max(0,x[3]+np.dot(x[:3],x[:3])))
    fit=least_squares(lambda p:np.linalg.norm(points-p[:3],axis=1)-p[3],np.r_[c,radius],loss="soft_l1",f_scale=.0015,max_nfev=100)
    need(fit.success and .012<fit.x[3]<.05,"invalid candidate sphere")
    return fit.x
def screen(points):
    # Independent contiguous Y tail, not random neighboring points.
    cut=np.quantile(points[:,1],.25);train=points[points[:,1]>=cut];test=points[points[:,1]<cut]
    need(len(test)>100 and len(train)>100,"empty withheld patch")
    p=sphere(train);full=sphere(points)
    def err(q,x):
        r=abs(np.linalg.norm(q-x[:3],axis=1)-x[3])*1000
        return {"rms_mm":float(np.sqrt(np.mean(r*r))),"p95_mm":float(np.quantile(r,.95)),"max_mm":float(r.max())}
    return full,{"train_vertices":len(train),"held_vertices":len(test),"split_y_m":float(cut),"train_fit_center_m":p[:3].tolist(),"train_fit_radius_m":float(p[3]),"heldout":err(test,p),"full_candidate_center_m":full[:3].tolist(),"full_radius_m":float(full[3]),"center_shift_mm":float(np.linalg.norm(p[:3]-full[:3])*1000)}
def load(z,record):
    name="source-stl/"+record["path"].split("02_Female/")[1]
    b=z.read(name);need(sha(b)==record["sha256"],"source STL digest")
    m=trimesh.load(io.BytesIO(b),file_type="stl",force="mesh",process=False);m.vertices*=.001;m.merge_vertices()
    need(len(m.faces)==record["triangles"] and np.max(abs(m.bounds-np.array(record["bounds_m"])))<1e-8,"source geometry")
    return m
def matrix(p,R=np.eye(3)):
    m=np.eye(4);m[:3,:3]=R;m[:3,3]=p;return m
def augment(raw,tracks):
    n=struct.unpack_from("<I",raw,12)[0];doc=json.loads(raw[20:20+n]);data=bytearray(raw[28+n:])
    def add(a,kind,bounds=False):
        a=np.asarray(a,dtype="<f4");data.extend(b"\0"*(-len(data)%4));off=len(data);data.extend(a.tobytes())
        vi=len(doc["bufferViews"]);doc["bufferViews"].append({"buffer":0,"byteOffset":off,"byteLength":a.nbytes})
        ai=len(doc["accessors"]);r={"bufferView":vi,"componentType":5126,"count":len(a),"type":kind}
        if bounds:r.update(min=[float(a.min())],max=[float(a.max())])
        doc["accessors"].append(r);return ai
    time=add([0,1,2],"SCALAR",True);channels=[];samplers=[]
    for name,axis,deg in tracks:
        i=next(i for i,n in enumerate(doc["nodes"]) if n.get("name")==name);node=doc["nodes"][i]
        # Joint frame is translation-only. No ambiguous matrix and TRS.
        if "matrix" in node:
            tf=np.array(node.pop("matrix")).reshape(4,4).T
            need(np.max(abs(tf[:3,:3]-np.eye(3)))<1e-9,"joint rest rotation")
            node["translation"]=tf[:3,3].tolist()
        need("scale" not in node and node.get("rotation",[0,0,0,1])==[0,0,0,1],"joint TRS")
        node["rotation"]=[0,0,0,1]
        q=Rotation.from_rotvec(np.array(axis)*np.radians(deg)).as_quat().tolist()
        out=add([[0,0,0,1],q,[0,0,0,1]],"VEC4")
        channels.append({"sampler":len(samplers),"target":{"node":i,"path":"rotation"}});samplers.append({"input":time,"output":out,"interpolation":"LINEAR"})
    doc["animations"]=[{"name":"Provisional same-donor skeletal articulation","channels":channels,"samplers":samplers}]
    doc["buffers"][0]["byteLength"]=len(data);js=json.dumps(doc,separators=(",",":")).encode();js+=b" "*(-len(js)%4);data.extend(b"\0"*(-len(data)%4))
    return struct.pack("<4sII",b"glTF",2,28+len(js)+len(data))+struct.pack("<I4s",len(js),b"JSON")+js+struct.pack("<I4s",len(data),b"BIN\0")+data
def render(out,groups,poses,pivots):
    im=Image.new("RGB",(1100,800),"#182631");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",21)
    d.text((16,12),"Actual female CT meshes | same-donor lower-limb articulation",font=font,fill="white")
    d.text((16,42),"Static pelvis, provisional hip/knee pivots; no patellar or ankle tracking",fill="#b9c8d4",font=font)
    # Oblique point surface witness. Fixed scale and projection, no mesh inference.
    for k,mode in enumerate(("rest","posed")):
        cx=275+k*550;scale=670;d.text((cx-110,82),mode.title(),font=font,fill="white")
        for name,m,segment in groups:
            v=m.vertices[::max(1,len(m.vertices)//10000)]
            if mode=="posed":v=trimesh.transform_points(v,poses[segment])
            a=v[:,0]-.45*v[:,2]
            y=v[:,1]
            color={"pelvis":"#d9c69f","thigh_L":"#8bb7ce","thigh_R":"#8bb7ce","shin_L":"#c4d2e0","shin_R":"#c4d2e0"}[segment]
            d.point([(cx+float(x)*scale,750-float(y)*scale) for x,y in zip(a,y)],fill=color)
    im.save(out/"actual-skeleton-articulation.png")
def run(src,out):
    with src.open("rb") as f:need(hashlib.file_digest(f,"sha256").hexdigest()==PIN,"archive pin")
    out.mkdir(parents=True,exist_ok=False)
    z=zipfile.ZipFile(src);r=json.loads(z.read("receipt.json"));records=r["inventory"]
    def rec(n):return next(x for x in records if x["id"].endswith("_"+n))
    raw={};groups=[];pivots={};report=[]
    # Convert original CT Z-up mm-derived metres to a common right-handed Y-up
    # stage. Center on the donor pelvis midpoint, floor from actual source feet.
    hiprows=[rec("HIP_LEFT"),rec("HIP_RIGHT")]
    center=np.mean([np.array(x["bounds_m"]).mean(0) for x in hiprows],axis=0)
    feet=[x for x in records if "/FOOT_" in x["path"]]
    floor=min(x["bounds_m"][0][2] for x in feet)
    shift=np.array([center[0],center[1],floor])
    def stage(v):return (v-shift)[:,[0,2,1]]*np.array([1,1,-1])
    def direction(v):return v[[0,2,1]]*np.array([1,1,-1])
    def add(row,seg):
        m=load(z,row);m.vertices=stage(m.vertices);groups.append((row["id"],m,seg))
    for side,short,sign in (("LEFT","L",1),("RIGHT","R",-1)):
        fm=load(z,rec("FEMUR_"+side));hm=load(z,rec("HIP_"+side));v=fm.vertices
        top=v[v[:,2]>v[:,2].max()-.065];cut=np.quantile(sign*top[:,0],.53);patch=top[sign*top[:,0]<cut]
        near=cKDTree(hm.vertices).query(patch)[0];patch=patch[near<.012]
        head,hr=screen(patch)
        bot=v[v[:,2]<v[:,2].min()+.045];mid=np.median(bot[:,0])
        c1,k1=screen(bot[bot[:,0]<mid-.004]);c2,k2=screen(bot[bot[:,0]>mid+.004])
        k=(c1[:3]+c2[:3])/2;axis=direction(c2[:3]-c1[:3]);axis/=np.linalg.norm(axis)
        hp=stage(head[:3][None,:])[0];kp=stage(k[None,:])[0]
        pivots[short]=(hp,kp,axis)
        add(rec("HIP_"+side),"pelvis");add(rec("FEMUR_"+side),"thigh_"+short)
        for n in ("TIBIA_","FIBULA_"):add(rec(n+side),"shin_"+short)
        for row in feet:
            if row["path"].split("/FOOT_")[1].startswith(side):add(row,"shin_"+short)
        report.append({"side":side,"hip_femoral_head":hr,"condyle_low_x":k1,"condyle_high_x":k2,"knee_axis_stage":axis.tolist(),"hip_to_knee_length_m":float(np.linalg.norm(hp-kp)),"hip_joint_candidate_status":"HOLD_ARTICULAR_CONTACT","knee_joint_candidate_status":"HOLD_ARTICULAR_AXIS_AND_CONTACT"})
    add(rec("SACRUM"),"pelvis")
    scene=trimesh.Scene(base_frame="world");poses={"pelvis":np.eye(4)};tracks=[]
    for short in ("L","R"):
        h,k,axis=pivots[short];parent="thigh_"+short;child="shin_"+short
        scene.graph.update(frame_from="world",frame_to=parent,matrix=matrix(h))
        scene.graph.update(frame_from=parent,frame_to=child,matrix=matrix(k-h))
        a=12 if short=="L" else -7;b=22 if short=="L" else 10
        rh=Rotation.from_rotvec(np.array([1,0,0])*np.radians(a)).as_matrix();rk=Rotation.from_rotvec(axis*np.radians(b)).as_matrix()
        poses[parent]=matrix(h,rh)@matrix(-h);poses[child]=poses[parent]@matrix(k,rk)@matrix(-k)
        tracks.extend([(parent,[1,0,0],a),(child,axis.tolist(),b)])
    scene.graph.update(frame_from="world",frame_to="pelvis",matrix=np.eye(4))
    # Store native source triangles in local joint coordinates, no decimation.
    for name,m,seg in groups:
        o=np.zeros(3) if seg=="pelvis" else pivots[seg[-1]][0 if seg.startswith("thigh") else 1]
        q=m.copy();q.vertices-=o
        q.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(baseColorFactor=[.76,.73,.65,1],metallicFactor=0,roughnessFactor=.9))
        scene.add_geometry(q,node_name=name,geom_name=name,parent_node_name=seg)
    raw=scene.export(file_type="glb");glb=augment(raw,tracks);(out/"female-ct-leg-animation.glb").write_bytes(glb)
    # Independently read bind-frame world coordinates of the actual exported GLB.
    parsed=trimesh.load(io.BytesIO(glb),file_type="glb",force="scene",process=False)
    need(set(parsed.graph.nodes_geometry)=={n for n,m,s in groups},"transport nodes")
    err=0.;rigid=0.
    posedscene=trimesh.Scene()
    for name,m,seg in groups:
        t,g=parsed.graph[name];q=parsed.geometry[g].copy();q.apply_transform(t)
        need(q.faces.shape==m.faces.shape,"triangle transport");err=max(err,float(np.max(abs(q.vertices[q.faces]-m.vertices[m.faces]))))
        posed=m.copy();posed.apply_transform(poses[seg]);e=m.edges_unique
        rigid=max(rigid,float(np.max(abs(np.linalg.norm(m.vertices[e[:,0]]-m.vertices[e[:,1]],axis=1)-np.linalg.norm(posed.vertices[e[:,0]]-posed.vertices[e[:,1]],axis=1)))))
        posedscene.add_geometry(posed,node_name=name,geom_name=name)
    need(err<2e-6 and rigid<1e-9,"geometry transport/rigidity")
    for s,(h,k,axis) in pivots.items():
        need(np.linalg.norm(trimesh.transform_points(k[None,:],poses["thigh_"+s])-trimesh.transform_points(k[None,:],poses["shin_"+s]))<1e-9,"joint disconnect")
    (out/"female-ct-leg-posed.glb").write_bytes(posedscene.export(file_type="glb"))
    # Retain patella separately in rest frame, no invented tracking rule.
    pscene=trimesh.Scene()
    for side in ("LEFT","RIGHT"):
        row=rec("PATELLA_"+side);m=load(z,row);m.vertices=stage(m.vertices);pscene.add_geometry(m,node_name=row["id"],geom_name=row["id"])
    (out/"patella-rest-only.glb").write_bytes(pscene.export(file_type="glb"))
    render(out,groups,poses,pivots);(out/"ATTRIBUTION.txt").write_bytes(z.read("ATTRIBUTION.txt")+b"\nR239: separate original CT mesh components, diagnostic local rigid joints. Patellar tracking, ankle motion and contact held.\n")
    receipt={"source_archive_sha256":PIN,"mesh_count":len(groups),"triangles":sum(len(m.faces) for n,m,s in groups),"models":{"animated":sha(glb),"posed":sha((out/"female-ct-leg-posed.glb").read_bytes()),"patella_rest":sha((out/"patella-rest-only.glb").read_bytes())},"transport_max_m":err,"rigid_edge_max_m":rigid,"animation_channels":4,"pivot_screens":report,"status":"HOLD_ANATOMICAL_JOINT_ADMISSION","scope":"Actual same-donor CT rigid lower-limb geometry and diagnostic animation. Fitted sphere patches are proxies, not proven femoral head/condyle surface identity, clinical pivots, collision-free contact or muscles/organ coupling. Patella rest-only; no ankle articulation."}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print("R239_CT_ARTICULATION",json.dumps(receipt),flush=True)
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
