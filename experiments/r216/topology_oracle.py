"""Independent indexed-mesh topology diagnostics on exact R209 source and candidates.
No repair, no forced weld tolerance, no physical or native-engine qualification.
"""
import json,hashlib,zipfile,sys
from pathlib import Path
from collections import Counter
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from PIL import Image,ImageDraw,ImageFont
IDS=("3001","3002","3003","3004","3005","3020","3022")
def measure(raw):
    vs=[];fs=[]
    for l in raw.decode().splitlines():
        t=l.split()
        if t and t[0]=="v":vs.append([float(x) for x in t[1:]])
        elif t and t[0]=="f":fs.append([int(x)-1 for x in t[1:]])
    v=np.array(vs);f=np.array(fs,dtype=np.int64)
    assert v.ndim==2 and v.shape[1]==3 and np.isfinite(v).all()
    assert f.ndim==2 and f.shape[1]==3 and f.min()>=0 and f.max()<len(v)
    # R209 OBJ stores metric coordinates at nine decimal places. Weld only
    # exact equality at those stored coordinates, not a new geometric tolerance.
    uv,idx=np.unique(v,axis=0,return_inverse=True);f=idx[f]
    repeated=(f[:,0]==f[:,1])|(f[:,1]==f[:,2])|(f[:,0]==f[:,2])
    t=uv[f];area2=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)
    deg=repeated|(area2<=1e-18)
    f=f[~deg];t=uv[f]
    used=np.unique(f);remap=np.full(len(uv),-1);remap[used]=np.arange(len(used));f=remap[f]
    # Components at shared vertex (weaker than full surface connectivity).
    directed=np.concatenate((f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]),axis=0)
    undirected=np.sort(directed,axis=1)
    edges,inverse,counts=np.unique(undirected,axis=0,return_inverse=True,return_counts=True)
    signs=np.where(directed[:,0]<directed[:,1],1,-1);w=np.bincount(inverse,weights=signs)
    adj=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(used),len(used))).tocsr()
    components=int(connected_components(adj,directed=False,return_labels=False))
    signed=float(np.einsum("ij,ij->i",t[:,0],np.cross(t[:,1],t[:,2])).sum()/6)
    return {"input_vertices":len(v),"welded_used_vertices":len(used),"triangles":len(f),"degenerate_removed_for_measurement":int(deg.sum()),"open_edges":int((counts==1).sum()),"nonmanifold_edges":int((counts>2).sum()),"inconsistent_two_face_edges":int(((counts==2)&(w!=0)).sum()),"vertex_connected_components":components,"euler":int(len(used)-len(edges)+len(f)),"signed_volume_mm3_diagnostic":signed*1e9}
def main(src,out):
    raw=src.read_bytes();assert hashlib.sha256(raw).hexdigest()=="64bb52981b46a402210c200e97437edff93597733e9886332a5544dd27130bea"
    out.mkdir(parents=True);rows=[]
    with zipfile.ZipFile(src) as z:
        for id in IDS:
            pair={k:measure(z.read(id+"/"+k+".obj")) for k in ("reference","candidate")}
            eligible=all(not a["open_edges"] and not a["nonmanifold_edges"] and not a["inconsistent_two_face_edges"] and not a["degenerate_removed_for_measurement"] for a in pair.values()) and all(pair["reference"][key]==pair["candidate"][key] for key in ("vertex_connected_components","euler"))
            rows.append({"id":id,**pair,"screen":"MATCHED_BASIC_TOPOLOGY" if eligible else "HOLD"})
    report={"scope":"exact coordinate weld, edge multiplicity/orientation, vertex connectivity and Euler only; no self-intersection or independent CAD truth; signed volume diagnostic only","results":rows}
    (out/"receipt.json").write_text(json.dumps(report,indent=2));print("R216_TOPOLOGY",json.dumps(report))
    im=Image.new("RGB",(1280,690),"#18212c");d=ImageDraw.Draw(im)
    title=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",28);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",19)
    d.text((25,20),"LDraw reconstruction | independent topology screen",font=title,fill="white")
    d.text((25,65),"Exact stored-coordinate weld; reference and candidate evaluated separately",font=font,fill="#c2d2df")
    cols=[25,145,400,650,880,1090]
    for x,t in zip(cols,["Part","Mesh","Open edges","Nonmanifold","Winding errors","Screen"]):d.text((x,115),t,font=font,fill="white")
    for i,row in enumerate(rows):
        y=155+i*65
        d.rectangle((12,y-7,1268,y+54),fill="#223343" if i%2==0 else "#1c2938")
        d.text((25,y),row["id"],font=font,fill="white")
        for k,(name,color) in enumerate((("reference","#d5ad7d"),("candidate","#78d8ab"))):
            a=row[name];yy=y+k*26
            for x,t in zip(cols[1:5],[name,a["open_edges"],a["nonmanifold_edges"],a["inconsistent_two_face_edges"]]):d.text((x,yy),str(t),font=font,fill=color)
        d.text((1090,y+12),"MATCH" if row["screen"]!="HOLD" else "HOLD",font=font,fill="#e5b879" if row["screen"]=="HOLD" else "#78d8ab")
    d.text((25,635),"A surface-distance pass is not a topology or manufacturing pass.",font=font,fill="#c2d2df");im.save(out/"topology-screen.png")
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
