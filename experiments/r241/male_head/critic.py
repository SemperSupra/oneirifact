"""Actual male femoral-head source patch diagnostic, common blocked holdout.
Do not substitute a sphere for bone geometry or infer clinical joint centers.
"""
import io,json,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"male"))
from register import ATLAS,IDS,sha,need,sphere,unit
def run(atlas,out):
    need(sha(atlas.read_bytes())==ATLAS,"source archive pin");out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(atlas) as z:
        inv={x["id"]:x for x in json.loads(z.read("inventory.json"))};r=json.loads(z.read("receipt.json"))
        raw=z.read("layers/skeletal.glb");need(sha(raw)==r["files"]["layers/skeletal.glb"]["sha256"],"source layer pin")
        scene=trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
        def source(role):
            ident,label=IDS[role];row=inv[ident];need(label in [x[1].lower() for x in row["concepts"]],"source concept")
            m,g=scene.graph[ident];q=scene.geometry[g].copy();q.apply_transform(m)
            need(len(q.faces)==row["triangles"],"source topology");return q.vertices
        h={s:source("hip."+s) for s in ("L","R")};f={s:source("femur."+s) for s in ("L","R")}
        (out/"ATTRIBUTION.txt").write_bytes(z.read("ATTRIBUTION.txt"))
    im=Image.new("RGB",(1200,650),"#182631");draw=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",21)
    draw.text((18,12),"Male femoral-head patch comparison | actual atlas points",font=font,fill="white")
    draw.text((18,42),"Grey: broad source | cyan: selected training | orange: fixed held-out",font=font,fill="#c9d4df")
    rows=[]
    for col,s in enumerate(("L","R")):
        v=f[s];other="R" if s=="L" else "L"
        # Anatomically motivated medial direction from opposite femur, not fitted
        # to containment or a synthetic target head. Select actual proximal patch.
        shaft=v[(v[:,1]>np.quantile(v[:,1],.25))&(v[:,1]<np.quantile(v[:,1],.75))].mean(0)
        o=f[other];other_shaft=o[(o[:,1]>np.quantile(o[:,1],.25))&(o[:,1]<np.quantile(o[:,1],.75))].mean(0)
        medial=other_shaft-shaft;medial[1]=0;medial=unit(medial)
        prox=v[v[:,1]>=v[:,1].max()-.085];dist=cKDTree(h[s]).query(prox)[0];broad=prox[dist<=np.quantile(dist,.65)]
        # Predeclared narrower superior-medial region and closest opposing hip
        # vertices; proximity is a proxy, not proven articular surface labels.
        p=prox[prox[:,1]>=v[:,1].max()-.065];proj=(p-shaft)@medial;p=p[proj>=np.quantile(proj,.5)]
        near=cKDTree(h[s]).query(p)[0];contact=p[near<=np.quantile(near,.65)]
        need(len(contact)>=42,"insufficient contact patch")
        slab=float(np.quantile(contact[:,2],.3));test=contact[contact[:,2]<slab]
        train0=broad[broad[:,2]>=slab];train1=contact[contact[:,2]>=slab]
        need(len(test)>=10 and len(train0)>=30 and len(train1)>=30,"blocked sample size")
        methods={}
        for name,t in (("broad",train0),("medial_contact",train1)):
            try:
                center,radius=sphere(t);e=np.abs(np.linalg.norm(test-center,axis=1)-radius)*1000
                methods[name]={"status":"FIT_CANDIDATE","center_m":center.tolist(),"radius_mm":radius*1000,"training_vertices":len(t),"heldout_rms_mm":float(np.sqrt(np.mean(e*e))),"heldout_max_mm":float(e.max())}
            except (ValueError,RuntimeError) as exc:
                methods[name]={"status":"HOLD_FIT","reason":str(exc),"training_vertices":len(t)}
        rows.append({"side":s,"holdout_vertices":len(test),"split_z_m":slab,"heldout_sha256":sha(np.ascontiguousarray(test).tobytes()),"methods":methods})
        cx=300+600*col;cy=350;scale=4300;mid=prox.mean(0)
        def project(q):return np.column_stack((cx+(q[:,0]-mid[0])*scale,cy-(q[:,1]-mid[1])*scale))
        draw.text((18+600*col,90),"Left" if s=="L" else "Right",font=font,fill="white")
        for data,color in ((prox,"#70818d"),(train1,"#63c7d5"),(test,"#f3aa57")):
            for x,y in project(data):draw.ellipse((x-2,y-2,x+2,y+2),fill=color)
    im.save(out/"male-head-patch-critic.png")
    receipt={"status":"HOLD_ANATOMICAL_ADMISSION","source_sha256":ATLAS,"selection":"Broad upper 85mm near hip vs upper 65mm medial half and opposing hip proximity; common contiguous Z holdout, both fits exclude same slab.","sides":rows,"scope":"Source atlas 99%-reduced geometry; actual points and sphere residual only. No clinical pivot, cartilage, anatomical or cross-donor registration acceptance. No change to prior candidate GLB."}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n");print("R241_HEAD_PATCH",json.dumps(receipt),flush=True)
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
