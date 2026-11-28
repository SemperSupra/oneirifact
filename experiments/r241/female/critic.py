"""Independent female orientation and penetration critic.
Compare baseline and previously containment-tuned roll to an anatomically
motivated but unqualified source-axis proxy candidate. No shrink or translation.
"""
import io,json,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"r240"/"registration"))
from ct_skin import glb,read,add,encode,xform,sha,need
PINS=["38c9d834128f18932870a799399496b1b86341a920374971af7585e676ec81c7","45b6e0650ceee40acf62ee67d227aaf6b9542a3b5af6b1dceb344f02b25e5886","f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f","f9e0e39a5591705aa73509e4239a4a9652d57fe3bdbb010b120b5366443ede8a"]
def unit(v):
    n=np.linalg.norm(v);need(n>1e-9,"degenerate vector");return v/n
def projected(v,u):return unit(v-u*np.dot(v,u))
def around(a,b,src,tgt):
    u=unit(b-a);x=projected(src,u);y=projected(tgt,u);angle=np.arctan2(np.dot(u,np.cross(x,y)),np.dot(x,y))
    R=Rotation.from_rotvec(u*angle).as_matrix();m=np.eye(4);m[:3,:3]=R;m[:3,3]=a-R@a
    need(np.max(abs(xform(np.array([a,b]),m)-np.array([a,b])))<1e-9,"endpoint change")
    return m,float(np.degrees(angle))
def surface_sample(v,f):
    tri=v[f];a=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1);need(a.sum()>0,"surface")
    rng=np.random.default_rng(24101);ids=rng.choice(len(f),320,p=a/a.sum());u=rng.random((320,2));u[u.sum(1)>1]=1-u[u.sum(1)>1]
    return ids,u
def sample(v,f,ids,u):
    t=v[f[ids]];return t[:,0]+u[:,0,None]*(t[:,1]-t[:,0])+u[:,1,None]*(t[:,2]-t[:,0])
def classify(mesh,p):
    hits=[]
    for d in ([1,.071,.023],[-.13,.039,1],[.09,1,.127]):
        _,i,_=mesh.ray.intersects_location(p,np.repeat([d],len(p),axis=0),multiple_hits=True);hits.append(np.bincount(i,minlength=len(p))%2==1)
    votes=np.array(hits).sum(0);out=votes==0;dist=[]
    for group in np.array_split(p[out],max(1,int(np.ceil(out.sum()/48)))):
        if len(group):
            _,dd,_=trimesh.proximity.closest_point(mesh,group);dist.extend((dd*1000).tolist())
    dd=np.array(dist);need(np.isfinite(dd).all(),"distance finite")
    return {"samples":len(p),"outside":int(out.sum()),"disagreement":int(((votes>0)&(votes<3)).sum()),"outside_over_5mm":int((dd>5).sum()),"outside_over_10mm":int((dd>10).sum()),"outside_max_mm":float(dd.max()) if len(dd) else 0.,"outside_distance_sum_mm":float(dd.sum()),"outside_p95_mm":float(np.quantile(dd,.95)) if len(dd) else 0.},votes
def run(base,roll,skin,ct,out):
    need([sha(x.read_bytes()) for x in (base,roll,skin,ct)]==PINS,"source archive pin");out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(base) as z,zipfile.ZipFile(roll) as rz,zipfile.ZipFile(skin) as sz,zipfile.ZipFile(ct) as cz:
        br=json.loads(z.read("receipt.json"));rr=json.loads(rz.read("receipt.json"));cr=json.loads(cz.read("receipt.json"));raw=z.read("female-athletic-ct-candidate.glb");rraw=rz.read("female-athletic-ct-roll-candidate.glb")
        need(sha(raw)==br["glb_sha256"] and sha(rraw)==rr["candidate_glb_sha256"],"GLB pin")
        d,b=glb(raw);rd,rb=glb(rraw);cpu=np.load(io.BytesIO(sz.read("female-athletic-cpu-reference.npz")));frames=cpu["frames"];faces=cpu["faces"]
        for n in ("LICENSE.md","LICENSE.ASSETS.md","ATTRIBUTION.txt"):(out/n).write_bytes(z.read(n))
    N=163;names=[x["name"] for x in d["nodes"][:N]];ix={n:i for i,n in enumerate(names)};parent={}
    for i,node in enumerate(d["nodes"]):
        for j in node.get("children",[]):need(j not in parent,"multiple parent");parent[j]=i
    a=d["animations"][0];tracks={c["target"]["node"]:read(d,b,a["samplers"][c["sampler"]]["output"]) for c in a["channels"]}
    def world(k):
        g=[]
        for i,n in enumerate(d["nodes"][:N]):
            M=np.eye(4);M[:3,:3]=Rotation.from_quat(tracks[i][k] if i in tracks else n["rotation"]).as_matrix();M[:3,3]=n["translation"];g.append(g[parent[i]]@M if i in parent else M)
        return np.array(g)
    worlds=[world(k) for k in range(3)];w=worlds[0];inv=np.linalg.inv(w)
    def j(n):return w[ix[n],:3,3]
    tside=j("upperleg01.L")-j("upperleg01.R")
    records={x["source"]:x for x in br["bones"]};groups={}
    for ni,node in enumerate(d["nodes"]):
        if not node.get("name","").startswith("CT_"):continue
        rec=records[node["name"][3:]];owner=rec["owner"];i=parent[ni];need(names[i]==owner,"owner")
        p=d["meshes"][node["mesh"]]["primitives"][0];rp=rd["meshes"][rd["nodes"][ni]["mesh"]]["primitives"][0]
        v=xform(read(d,b,p["attributes"]["POSITION"]),w[i]);rv=xform(read(rd,rb,rp["attributes"]["POSITION"]),w[i]);f=read(d,b,p["indices"]).reshape(-1,3);need(np.array_equal(f,read(rd,rb,rp["indices"]).reshape(-1,3)),"topology correspondence")
        groups.setdefault(owner,[]).append((ni,rec,p,v,rv,f))
    need(sum(map(len,groups.values()))==9,"components")
    # Source CT femoral condyle axis is a surface-fit proxy, not a clinical hinge.
    # Sacral upper patch to midpoint and spine01-to-hips are also explicit proxies.
    axes={};base_rows={x["side"]:x for x in cr["pivot_screens"]}
    hL=j("upperleg01.L");hR=j("upperleg01.R");mid=(hL+hR)/2
    sac=next(x for x in groups["root"] if "SACRUM" in x[1]["source"])
    sm=np.array(sac[1]["source_to_rig"]);sv=xform(sac[3],np.linalg.inv(sm));sup=sv[sv[:,1]>=np.quantile(sv[:,1],.85)].mean(0)
    axes["root"]=(hR,hL,xform(sup[None,:],sm)[0]-mid,j("spine01")-mid)
    for side,label in (("L","LEFT"),("R","RIGHT")):
        u=j("upperleg01."+side);k=j("lowerleg01."+side);a=j("foot."+side)
        for owner,p,q in (("upperleg01."+side,u,k),("lowerleg01."+side,k,a)):
            M=np.array(groups[owner][0][1]["source_to_rig"]);source=np.array(base_rows[label]["knee_axis_stage"])
            s=M[:3,:3]@source
            if np.dot(s,tside)<0:s=-s
            axes[owner]=(p,q,s,tside)
    results=[];views=[[],[],[]];angles={}
    meshes=[trimesh.Trimesh(vertices=f,faces=faces,process=False) for f in frames];need(all(m.is_watertight for m in meshes),"closed skin required")
    for owner,items in groups.items():
        M,angle=around(*axes[owner]);angles[owner]=angle;i=ix[owner]
        for ni,rec,p,v,rv,f in items:
            cv=xform(v,M);local=xform(cv,inv[i]);p["attributes"]["POSITION"]=add(d,b,local.astype("<f4"),5126,"VEC3",34962,True)
            # Corresponding area-weighted triangle samples chosen from baseline.
            ids,u=surface_sample(v,f)
            a0=sample(v,f,ids,u);a1=sample(rv,f,ids,u);a2=sample(cv,f,ids,u)
            need(np.max(abs(np.linalg.norm(a0-a0[0],axis=1)-np.linalg.norm(a2-a2[0],axis=1)))<1e-9,"candidate shape change")
            for k in range(3):
                T=worlds[k][i]@inv[i];row={"bone":rec["source"],"owner":owner,"frame":k}
                for col,(name,pts) in enumerate(zip(("baseline","containment_roll","source_axis_proxy"),(a0,a1,a2))):
                    q=xform(pts,T);r,votes=classify(meshes[k],q);row[name]=r
                    if k==0:views[col].append((q,votes))
                results.append(row)
    packed=encode(d,b);(out/"female-source-axis-proxy.glb").write_bytes(packed)
    summary=[]
    for k in range(3):
        rows=[r for r in results if r["frame"]==k];s={"frame":k}
        for n in ("baseline","containment_roll","source_axis_proxy"):
            s[n]={key:sum(r[n][key] for r in rows) for key in ("samples","outside","disagreement","outside_over_5mm","outside_over_10mm","outside_distance_sum_mm")}
            s[n]["outside_max_mm"]=max(r[n]["outside_max_mm"] for r in rows)
        summary.append(s)
    im=Image.new("RGB",(1440,660),"#17232d");draw=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",21)
    draw.text((18,12),"Female CT surface penetration | independent area-weighted samples | red = outside",font=font,fill="white")
    for col,points in enumerate(views):
        cx=240+480*col;cy=615;scale=305
        def project(v):return np.column_stack((cx+v[:,2]*scale,cy-v[:,1]*scale))
        xy=project(frames[0]);draw.text((18+480*col,54),("Initial fit","Containment roll","Source-axis proxy")[col],font=font,fill="white")
        for f in faces:
            if frames[0][f,1].max()<1.1:draw.polygon([tuple(xy[i]) for i in f],fill="#536b7b")
        for pts,votes in points:
            for (x,y),vote in zip(project(pts),votes):
                c="#fa7559" if vote==0 else "#ffe0ac" if vote==3 else "#f5b544";draw.ellipse((x-1,y-1,x+1,y+1),fill=c)
    im.save(out/"female-axis-penetration-comparison.png")
    receipt={"status":"HOLD_ANATOMICAL_ADMISSION","source_sha256":PINS,"source_axis_angles_deg":angles,"summary":summary,"bone_rows":results,"candidate_glb_sha256":sha(packed),"scope":"Independent new area-weighted corresponding triangle samples (not independent donors). Multi-ray parity and exact nearest-skin triangle distances for unanimous exterior points. Source condyle axis and sacral/spine landmarks are unqualified proxies, not physiological axes. No scaling or translation fit, no admission regardless of containment improvement."}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n");print("R241_FEMALE_CRITIC",json.dumps({"status":receipt["status"],"angles":angles,"summary":summary},sort_keys=True),flush=True)
if __name__=="__main__":run(*(Path(x) for x in sys.argv[1:]))
