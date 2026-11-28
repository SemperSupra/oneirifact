"""Held-out axial roll screen on actual R240 bone/skin registration.
Never shrink bones or move their fitted endpoints. Containment alone cannot
determine anatomical orientation; this is a bounded candidate comparison.
"""
import io,json,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"registration"))
from ct_skin import glb,read,add,encode,xform,sha,need,metrics
CT="38c9d834128f18932870a799399496b1b86341a920374971af7585e676ec81c7"
SKIN="f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f"
ANGLES=(-20,-10,0,10,20)
def around(a,b,angle):
    u=b-a;need(np.linalg.norm(u)>.03,"degenerate axis");u/=np.linalg.norm(u)
    R=Rotation.from_rotvec(u*np.radians(angle)).as_matrix();m=np.eye(4);m[:3,:3]=R;m[:3,3]=a-R@a
    need(np.max(abs(xform(np.array([a,b]),m)-np.array([a,b])))<1e-9,"endpoint changed")
    return m
def sample(v,a,b):
    u=b-a;u/=np.linalg.norm(u)
    p=(v-a)@u;lo,hi=p.min(),p.max();need(hi-lo>.01,"sampling extent")
    bands=np.minimum(11,np.floor(12*(p-lo)/(hi-lo)).astype(int));held=(bands%3)==1
    def take(mask):
        i=np.flatnonzero(mask);need(len(i)>=160,"insufficient blocked samples")
        i=i[np.lexsort((v[i,2],v[i,1],v[i,0],p[i]))];return i[np.linspace(0,len(i)-1,160,dtype=int)]
    return take(~held),take(held)
def single_out(mesh,v):
    dirs=np.repeat([[1,.071,.023]],len(v),axis=0)
    _,i,_=mesh.ray.intersects_location(v,dirs,multiple_hits=True)
    return int(np.sum(np.bincount(i,minlength=len(v))%2==0))
def run(src,skin,out):
    need(sha(src.read_bytes())==CT and sha(skin.read_bytes())==SKIN,"exact inputs");out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(src) as z,zipfile.ZipFile(skin) as sz:
        raw=z.read("female-athletic-ct-candidate.glb");prev=json.loads(z.read("receipt.json"));need(sha(raw)==prev["glb_sha256"],"GLB source pin")
        d,b=glb(raw);cpu=np.load(io.BytesIO(sz.read("female-athletic-cpu-reference.npz")));frames=cpu["frames"];faces=cpu["faces"]
        for n in ("LICENSE.md","LICENSE.ASSETS.md","ATTRIBUTION.txt"):(out/n).write_bytes(z.read(n))
    N=163;names=[x["name"] for x in d["nodes"][:N]];ix={n:i for i,n in enumerate(names)};parent={}
    for i,node in enumerate(d["nodes"]):
        for j in node.get("children",[]):need(j not in parent,"multiple parents");parent[j]=i
    a=d["animations"][0];track={c["target"]["node"]:read(d,b,a["samplers"][c["sampler"]]["output"]) for c in a["channels"]}
    def world(k):
        g=[]
        for i,n in enumerate(d["nodes"][:N]):
            m=np.eye(4);m[:3,:3]=Rotation.from_quat(track[i][k] if i in track else n["rotation"]).as_matrix();m[:3,3]=n["translation"];g.append(g[parent[i]]@m if i in parent else m)
        return np.array(g)
    worlds=[world(i) for i in range(3)];w=worlds[0];inv=np.linalg.inv(w)
    def pos(n):return w[ix[n],:3,3]
    axes={"root":(pos("upperleg01.R"),pos("upperleg01.L"))}
    for s in ("L","R"):
        axes["upperleg01."+s]=(pos("upperleg01."+s),pos("lowerleg01."+s));axes["lowerleg01."+s]=(pos("lowerleg01."+s),pos("foot."+s))
    meshes=[trimesh.Trimesh(vertices=f,faces=faces,process=False) for f in frames]
    need(all(m.is_watertight for m in meshes),"skin not watertight")
    groups={k:[] for k in axes}
    for j,n in enumerate(d["nodes"]):
        if not n.get("name","").startswith("CT_"):continue
        i=parent[j];owner=names[i];need(owner in groups,"unmapped CT attachment")
        p=d["meshes"][n["mesh"]]["primitives"][0];local=read(d,b,p["attributes"]["POSITION"]).astype(float);v=xform(local,w[i]);train,test=sample(v,*axes[owner]);need(not np.intersect1d(train,test).size,"train/test overlap")
        groups[owner].append((j,n["name"],i,p,v,train,test))
    need(sum(map(len,groups.values()))==9,"CT component inventory")
    results=[];visual=[[],[]]
    for owner,items in groups.items():
        p0,p1=axes[owner];scores=[]
        for ang in ANGLES:
            M=around(p0,p1,ang)
            score=sum(single_out(meshes[0],xform(v[t],M)) for _,_,_,_,v,t,_ in items)
            scores.append((score,abs(ang),ang))
        score,_,angle=min(scores);M=around(p0,p1,angle);rows=[]
        for j,name,i,p,v,train,test in items:
            mapped=xform(v,M);local=xform(mapped,inv[i])
            # Check distances and source topology; no independent shape scaling.
            delta=np.linalg.norm(v[:min(4096,len(v))]-v[0],axis=1)-np.linalg.norm(mapped[:min(4096,len(v))]-mapped[0],axis=1)
            need(np.max(abs(delta))<1e-9,"bone shape changed")
            p["attributes"]["POSITION"]=add(d,b,local.astype("<f4"),5126,"VEC3",34962,True)
            row={"bone":name,"heldout":[]}
            for k in (0,1,2):
                T=worlds[k][i]@inv[i];a0=xform(v[test],T);a1=xform(mapped[test],T)
                row["heldout"].append({"frame":k,"baseline":metrics(meshes[k],a0),"candidate":metrics(meshes[k],a1)})
            rows.append(row);visual[0].append((name,v[test]));visual[1].append((name,mapped[test]))
        results.append({"owner":owner,"selected_angle_deg":angle,"training_outside_by_angle":{str(a):s for s,_,a in scores},"heldout":rows})
    packed=encode(d,b);(out/"female-athletic-ct-roll-candidate.glb").write_bytes(packed)
    dd,bb=glb(packed);need(len(dd["animations"][0]["channels"])==7,"animation changed")
    summary=[]
    for k in (0,1,2):
        rows=[x["heldout"][k] for g in results for x in g["heldout"]]
        summary.append({"frame":k,"samples":sum(x["baseline"]["samples"] for x in rows),"baseline_outside":sum(x["baseline"]["all_three_outside"] for x in rows),"candidate_outside":sum(x["candidate"]["all_three_outside"] for x in rows),"baseline_disagreement":sum(x["baseline"]["disagreement"] for x in rows),"candidate_disagreement":sum(x["candidate"]["disagreement"] for x in rows)})
    im=Image.new("RGB",(1440,860),"#18242f");draw=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",22)
    draw.text((18,12),"Actual female CT registration | held-out surface points | red = outside all three rays",font=font,fill="white")
    for col,points in enumerate(visual):
        for row,(axis,label) in enumerate(((0,"Front"),(2,"Side"))):
            cx=360+720*col;cy=405+420*row;scale=355
            def project(v):return np.column_stack((cx+v[:,axis]*scale,cy-v[:,1]*scale))
            xy=project(frames[0]);draw.text((18+720*col,45+420*row),("Baseline" if col==0 else "Bounded roll candidate")+" / "+label,font=font,fill="white")
            # Crop to lower-body anatomy for leg/pelvis comparison.
            for f in faces:
                if frames[0][f,1].max()<1.:draw.polygon([tuple(xy[i]) for i in f],fill="#566e7e")
            for name,v in points:
                flags=[]
                for direction in ([1,.071,.023],[-.13,.039,1],[.09,1,.127]):
                    _,ids,_=meshes[0].ray.intersects_location(v,np.repeat([direction],len(v),axis=0),multiple_hits=True)
                    flags.append(np.bincount(ids,minlength=len(v))%2==1)
                votes=np.array(flags).sum(0)
                for (x,y),vote in zip(project(v),votes):
                    c="#ed775d" if vote==0 else "#ffe4b3" if vote==3 else "#f5b544";draw.ellipse((x-1,y-1,x+1,y+1),fill=c)
    im.save(out/"registered-roll-compare.png")
    receipt={"status":"HOLD_ANATOMICAL_ADMISSION","source_sha256":{"ct_skin":CT,"skin":SKIN},"angles_deg":ANGLES,"selection":"rest training single-ray exterior count, then smallest absolute angle; fixed spatial bands held out, three-direction diagnostic at all three animation keys","groups":results,"summary":summary,"candidate_glb_sha256":sha(packed),"scope":"Axial rotation preserves two fitted pivot endpoints, source shape and all animation channels. Cross-donor orientation, contact and anatomical landmarks remain unqualified. No scale reduction or translation optimization."}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n");print("R240_ROLL_SCREEN",json.dumps({"summary":summary,"angles":{x["owner"]:x["selected_angle_deg"] for x in results},"status":receipt["status"]}),flush=True)
if __name__=="__main__":run(*(Path(x) for x in sys.argv[1:]))
