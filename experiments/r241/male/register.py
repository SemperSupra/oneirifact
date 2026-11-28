"""Male atlas / full-weight athletic rig coupling candidate.
Exact named BodyParts3D components, same donor opposing surface landmarks.
Cross-donor pose candidate, NOT admitted anatomical or joint geometry.
"""
import io,json,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"r240"/"registration"))
from ct_skin import glb,read,add,encode,xform,sha,need,metrics,similarity
ATLAS="18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9"
SKIN="f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f"
IDS={"hip.L":("FJ3288","left hip bone"),"hip.R":("FJ3152","right hip bone"),"femur.L":("FJ3259","left femur"),"femur.R":("FJ3365","right femur"),"tibia.L":("FJ3282","left tibia"),"tibia.R":("FJ3387","right tibia"),"fibula.L":("FJ3260","left fibula"),"fibula.R":("FJ3366","right fibula"),"sacrum":("FJ3393","sacrum")}
def sphere(v):
    need(len(v)>=30,"insufficient proximal patch")
    mean=v.mean(0);q=v-mean
    p=np.linalg.lstsq(np.column_stack((2*q,np.ones(len(q)))),np.sum(q*q,1),rcond=None)[0]
    radius=np.sqrt(max(1e-8,p[3]+np.dot(p[:3],p[:3])))
    x=least_squares(lambda a:np.linalg.norm(v-a[:3],axis=1)-a[3],np.r_[p[:3]+mean,radius],loss="soft_l1",f_scale=.002,max_nfev=100)
    need(x.success and .008<x.x[3]<.075,"head fit outside candidate domain")
    return x.x[:3],float(x.x[3])
def unit(v):
    n=np.linalg.norm(v);need(n>1e-8,"degenerate direction");return v/n
def frame(axis,transverse):
    y=unit(axis);x=unit(transverse-y*np.dot(y,transverse));z=unit(np.cross(x,y));return np.column_stack((x,y,z))
def oriented(a,b,c,d,src_side,target_side):
    S=frame(b-a,src_side);T=frame(d-c,target_side);scale=np.linalg.norm(d-c)/np.linalg.norm(b-a)
    M=np.eye(4);M[:3,:3]=scale*T@S.T;M[:3,3]=c-M[:3,:3]@a
    need(np.linalg.det(M[:3,:3])>0 and np.max(abs(xform(np.array([a,b]),M)-np.array([c,d])))<1e-9,"frame endpoint")
    return M,float(scale)
def run(atlas,skin,out):
    need(sha(atlas.read_bytes())==ATLAS and sha(skin.read_bytes())==SKIN,"exact sources")
    out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(atlas) as z,zipfile.ZipFile(skin) as sz:
        inventory={x["id"]:x for x in json.loads(z.read("inventory.json"))};ar=json.loads(z.read("receipt.json"));raw=z.read("layers/skeletal.glb");need(sha(raw)==ar["files"]["layers/skeletal.glb"]["sha256"],"atlas layer pin")
        scene=trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
        bonesrc={}
        for role,(ident,label) in IDS.items():
            row=inventory[ident];need(label in [x[1].lower() for x in row["concepts"]],"source concept mismatch "+role)
            m,g=scene.graph[ident];q=scene.geometry[g].copy();q.apply_transform(m)
            need(len(q.faces)==row["triangles"] and np.max(abs(q.bounds-np.array(row["bounds_m"])))<2e-6,"source geometry "+role)
            bonesrc[role]=q
        (out/"ATTRIBUTION.txt").write_bytes(z.read("ATTRIBUTION.txt")+b"\nR241: nine exact named source bone elements; candidate segmentwise similarities; no clinical claim.\n")
        for n in ("LICENSE-source.html","LICENSE-update.html"):(out/n).write_bytes(z.read(n))
        raw=sz.read("male-athletic-animated.glb");sr=json.loads(sz.read("receipt.json"));need(sha(raw)==next(x["glb_sha256"] for x in sr["variants"] if x["id"]=="male-athletic"),"skin pin")
        d,b=glb(raw);fit=json.loads(sz.read("male-athletic-rig.json"));cpu=np.load(io.BytesIO(sz.read("male-athletic-cpu-reference.npz")));frames=cpu["frames"];faces=cpu["faces"]
        for n in ("LICENSE.md","LICENSE.ASSETS.md"):(out/n).write_bytes(sz.read(n))
    bones=fit["bones"];names=[x["id"] for x in bones];ix={n:i for i,n in enumerate(names)};N=len(names)
    need(N==163 and all(d["nodes"][i]["name"]==n for i,n in enumerate(names)),"rig identity")
    world=np.array([x["world_bind"] for x in bones]);inv=np.array([x["inverse_bind"] for x in bones]);parent=[-1 if x["parent"] is None else ix[x["parent"]] for x in bones]
    def j(n):return world[ix[n],:3,3]
    pivots={};diagnostics=[]
    for s in ("L","R"):
        f=bonesrc["femur."+s].vertices;h=bonesrc["hip."+s].vertices;t=bonesrc["tibia."+s].vertices
        # Select proximal points on actual femur closest to actual same-atlas hip.
        prox=f[f[:,1]>=f[:,1].max()-.085];dist=cKDTree(h).query(prox)[0];cut=np.quantile(dist,.65);patch=prox[dist<=cut]
        # Spatial holdout on sagittal coordinate, never used in sphere fit.
        ycut=np.quantile(patch[:,2],.25);train=patch[patch[:,2]>=ycut];held=patch[patch[:,2]<ycut]
        hp,rad=sphere(train);need(len(held)>=8,"no withheld proximal head")
        err=np.abs(np.linalg.norm(held-hp,axis=1)-rad)*1000
        # Knee and ankle are source-surface centroid proxies, not clinical axes.
        distal=f[f[:,1]<=f[:,1].min()+.04];nearest=cKDTree(t).query(distal)[0];patch2=distal[nearest<=np.quantile(nearest,.5)]
        kp=patch2.mean(0);ankle=t[t[:,1]<=t[:,1].min()+.015].mean(0)
        pivots[s]=(hp,kp,ankle)
        diagnostics.append({"side":s,"proximal_training":len(train),"proximal_heldout":len(held),"head_radius_mm":rad*1000,"head_heldout_rms_mm":float(np.sqrt(np.mean(err*err))),"head_heldout_max_mm":float(err.max()),"knee_proxy_vertices":len(patch2)})
    src_trans=pivots["L"][0]-pivots["R"][0];target_trans=j("upperleg01.L")-j("upperleg01.R")
    # Match bilateral hip centers; use sacrum-to-hip superior direction as source
    # and lower-spine direction as target proxy. No containment tuning.
    smean=np.mean([pivots[s][0] for s in ("L","R")],axis=0);tmean=(j("upperleg01.L")+j("upperleg01.R"))/2
    sac=bonesrc["sacrum"].vertices;sup=sac[sac[:,1]>=np.quantile(sac[:,1],.85)].mean(0)
    pm,ps=oriented(pivots["R"][0],pivots["L"][0],j("upperleg01.R"),j("upperleg01.L"),sup-smean,j("spine01")-tmean)
    transforms={"pelvis":(pm,ps,"root")}
    for s in ("L","R"):
        hp,kp,ank=pivots[s]
        M,scale=oriented(hp,kp,j("upperleg01."+s),j("lowerleg01."+s),src_trans,target_trans)
        transforms["thigh."+s]=(M,scale,"upperleg01."+s)
        M,scale=oriented(kp,ank,j("lowerleg01."+s),j("foot."+s),src_trans,target_trans)
        transforms["shin."+s]=(M,scale,"lowerleg01."+s)
    d["materials"][0]["alphaMode"]="BLEND";d["materials"][0]["doubleSided"]=False;d["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"]=[.57,.69,.78,.22]
    d["materials"].append({"name":"Male anatomical bone candidate","pbrMetallicRoughness":{"baseColorFactor":[.92,.82,.62,1],"metallicFactor":0,"roughnessFactor":.85}})
    groups=[];records=[]
    for role,(ident,label) in IDS.items():
        s=role[-1];region="pelvis" if role.startswith("hip.") or role=="sacrum" else "thigh."+s if role.startswith("femur.") else "shin."+s
        M,scale,owner=transforms[region];m=bonesrc[role];mapped=xform(m.vertices,M);local=xform(mapped,inv[ix[owner]]);f=m.faces
        e=m.edges_unique;need(np.max(abs(np.linalg.norm(mapped[e[:,0]]-mapped[e[:,1]],axis=1)-scale*np.linalg.norm(m.vertices[e[:,0]]-m.vertices[e[:,1]],axis=1)))<1e-9,"shape preservation")
        p=add(d,b,local.astype("<f4"),5126,"VEC3",34962,True);ind=add(d,b,f.astype("<u4").ravel(),5125,"SCALAR",34963)
        mi=len(d["meshes"]);d["meshes"].append({"name":ident,"primitives":[{"attributes":{"POSITION":p},"indices":ind,"material":1}]})
        ni=len(d["nodes"]);d["nodes"].append({"name":"BP3D_"+ident,"mesh":mi});d["nodes"][ix[owner]].setdefault("children",[]).append(ni)
        groups.append((role,owner,mapped,f,ni));records.append({"id":ident,"label":label,"owner":owner,"scale":scale,"triangles":len(f),"source_to_rig":M.tolist()})
    packed=encode(d,b);(out/"male-athletic-anatomical-candidate.glb").write_bytes(packed)
    dd,bb=glb(packed);a=dd["animations"][0];rot={c["target"]["node"]:read(dd,bb,a["samplers"][c["sampler"]]["output"]) for c in a["channels"]};rows=[];views=[];maxerr=0.
    for k in range(3):
        g=[]
        for i,n in enumerate(dd["nodes"][:N]):
            M=np.eye(4);M[:3,:3]=Rotation.from_quat(rot[i][k] if i in rot else n["rotation"]).as_matrix();M[:3,3]=n["translation"];g.append(M if parent[i]<0 else g[parent[i]]@M)
        skinmesh=trimesh.Trimesh(vertices=frames[k],faces=faces,process=False);need(skinmesh.is_watertight,"skin watertight");pp=[]
        for role,owner,mapped,f,ni in groups:
            i=ix[owner];p=dd["meshes"][dd["nodes"][ni]["mesh"]]["primitives"][0];v=xform(read(dd,bb,p["attributes"]["POSITION"]),g[i]);expected=xform(mapped,g[i]@inv[i]);maxerr=max(maxerr,float(np.max(np.linalg.norm(v-expected,axis=1))))
            # deterministic surface-area samples on full triangles, not index sampling
            tri=v[f];area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1);rng=np.random.default_rng(241);t=tri[rng.choice(len(tri),256,p=area/area.sum())];u=rng.random((256,2));u[u.sum(1)>1]=1-u[u.sum(1)>1];sample=t[:,0]+u[:,0,None]*(t[:,1]-t[:,0])+u[:,1,None]*(t[:,2]-t[:,0])
            rows.append({"frame":k,"role":role,**metrics(skinmesh,sample)});pp.append((role,v))
        views.append(pp)
    need(maxerr<2e-6,"bone transport")
    im=Image.new("RGB",(1200,800),"#182631");draw=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",21)
    draw.text((16,12),"Male athletic skin + nine named male atlas bones | registration candidate",font=font,fill="white")
    for col,k in enumerate((0,1)):
        for row,axis in enumerate((0,2)):
            cx=300+600*col;cy=385+400*row;scale=186
            def project(v):return np.column_stack((cx+v[:,axis]*scale,cy-v[:,1]*scale))
            xy=project(frames[k]);draw.text((16+600*col,40+400*row),("Rest" if k==0 else "Pose")+" / "+("front" if axis==0 else "side"),font=font,fill="white")
            for f in faces:draw.polygon([tuple(xy[i]) for i in f],fill="#576d7d")
            for role,v in views[k]:draw.point([tuple(q) for q in project(v[::max(1,len(v)//8000)])],fill="#f4dbac")
    im.save(out/"male-registration-witness.png")
    summary=[{"frame":k,"samples":sum(x["samples"] for x in rows if x["frame"]==k),"outside":sum(x["all_three_outside"] for x in rows if x["frame"]==k),"disagreement":sum(x["disagreement"] for x in rows if x["frame"]==k)} for k in range(3)]
    receipt={"status":"HOLD_CROSS_DONOR_ANATOMICAL_ADMISSION","input_sha256":{"atlas":ATLAS,"skin":SKIN},"bones":records,"landmark_screen":diagnostics,"ray_parity":rows,"summary":summary,"serialized_bone_max_m":maxerr,"glb_sha256":sha(packed),"scope":"Actual male atlas components, independent source head patch fit and orientation proxies; cross-donor, not clinical or qualified anatomical fit. Reduced donor resolution, knee/ankle and transverse proxy axes, no muscles/organs, contact or native acceptance."}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n");print("R241_MALE",json.dumps({"status":receipt["status"],"summary":summary,"landmark_screen":diagnostics,"mesh_count":len(records),"triangles":sum(x["triangles"] for x in records),"serialized_bone_max_m":maxerr,"glb_sha256":receipt["glb_sha256"]}),flush=True)
if __name__=="__main__":run(*(Path(x) for x in sys.argv[1:]))
