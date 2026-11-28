"""R226: leakage-free leave-one-bone-out diagnostic, not anatomical fit."""
import hashlib,io,json,re,sys,zipfile
from pathlib import Path
from collections import defaultdict
import numpy as np
CT="6ebcae2937da21450e7f536ceb92d91e96a422862e80320476e7c1d6ef08ee27"
HRA="513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542"
def checked(p,d):
    with p.open("rb") as f:assert hashlib.file_digest(f,"sha256").hexdigest()==d
    return zipfile.ZipFile(p)
def region(n):
    if not n:return None
    if "vertebra" in n or n.endswith(("sacrum","sternum")):return "axial"
    if re.search(r"(femur|tibia|fibula|patella)_[LR]$",n):return "leg_"+n[-1]
def fit(rows,scaled):
    a=np.array([r["ct"] for r in rows]);b=np.array([r["hra"] for r in rows])
    ca=a.mean(0);cb=b.mean(0);x=a-ca;y=b-cb
    rank=int(np.linalg.matrix_rank(x,tol=1e-5));target_rank=int(np.linalg.matrix_rank(y,tol=1e-5))
    if min(rank,target_rank)<2:return None
    U,S,V=np.linalg.svd(x.T@y);D=np.eye(3);D[2,2]=np.linalg.det(U@V)
    R=U@D@V;s=float(np.sum(S*np.diag(D))/np.sum(x*x)) if scaled else 1.0
    if not np.isfinite(s) or s<=0 or np.linalg.det(R)<.999:return None
    return s,R,cb-s*ca@R,rank,target_rank
def score(rows,hold,scaled):
    assert all(r["name"]!=hold["name"] for r in rows)
    t=fit(rows,scaled)
    if t is None:return {"status":"DEGENERATE","training_names":[r["name"] for r in rows]}
    s,R,p,rank,tr=t
    err=float(np.linalg.norm(s*np.array(hold["ct"])@R+p-hold["hra"])*1000)
    # Bounds extents are proxy only: no surface correspondence.
    return {"status":"CENTRE_PROXY_ONLY","error_mm":err,"scale":s,"rank":rank,"target_rank":tr,"training_names":[r["name"] for r in rows],"rotation":R.tolist(),"translation_m":p.tolist()}
def selftest():
    a=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[1,1,1]],float)
    R=np.array([[0,-1,0],[1,0,0],[0,0,1]],float)
    b=1.03*a@R+np.array([1,2,3])
    rows=[{"name":str(i),"ct":x.tolist(),"hra":y.tolist()} for i,(x,y) in enumerate(zip(a,b))]
    assert score(rows[:-1],rows[-1],True)["error_mm"]<1e-8
    assert score(rows[:-1],rows[-1],False)["error_mm"]>1
def main(inp,out):
    selftest();out.mkdir(parents=True,exist_ok=False)
    with checked(inp/"ct.zip",CT) as z,checked(inp/"female.zip",HRA) as h:
        ct=json.loads(z.read("receipt.json"))["inventory"];hra=json.loads(h.read("inventory.json"))
        # Reject duplicate matching names rather than silently choosing a target.
        dest=defaultdict(list)
        for r in hra:dest[r["source_node"]].append(r)
        rows=[]
        for r in ct:
            n=r.get("atlas_match");g=region(n)
            if g and len(dest[n])==1:
                rows.append({"name":n,"region":g,"ct_id":r["id"],"hra_id":dest[n][0]["id"],"ct":np.array(r["bounds_m"]).mean(0).tolist(),"hra":np.array(dest[n][0]["bounds_m"]).mean(0).tolist()})
        assert len(rows)==35 and len({r["name"] for r in rows})==35
        assert all(np.isfinite(r["ct"]).all() and np.isfinite(r["hra"]).all() for r in rows)
    rows.sort(key=lambda r:r["name"]);folds=[]
    for hold in rows:
        train=[r for r in rows if r["name"]!=hold["name"]]
        local=[r for r in train if r["region"]==hold["region"]]
        folds.append({"holdout":hold,"global_rigid":score(train,hold,False),"global_similarity":score(train,hold,True),"regional_rigid":score(local,hold,False),"regional_similarity":score(local,hold,True)})
    summary={}
    methods=("global_rigid","global_similarity","regional_rigid","regional_similarity")
    for g in ("axial","leg_L","leg_R"):
        sub=[f for f in folds if f["holdout"]["region"]==g]
        s={}
        for k in methods:
            e=np.array([f[k]["error_mm"] for f in sub if "error_mm" in f[k]])
            s[k]={"valid_folds":len(e),"total_folds":len(sub),"rmse_mm":float(np.sqrt(np.mean(e*e))) if len(e) else None,"max_mm":float(e.max()) if len(e) else None,"scales":[f[k]["scale"] for f in sub if "scale" in f[k]]}
        summary[g]=s
    result={"source_pins":{"CT":CT,"HRA":HRA},"folds":folds,"summary":summary,"status":"HOLD_SURFACE_JOINT_AND_REGISTRATION","scope":"Every target bone excluded from both fits. Shared donor-center proxies are not external validation or annotated anatomical landmarks; leg regional folds have only three training points. No mesh transformation, anatomical fusion or geometry admission."}
    (out/"registration.json").write_text(json.dumps(result,indent=2))
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    lines=['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="430" viewBox="0 0 960 430"><rect width="960" height="430" fill="#17232f"/><text x="20" y="35" fill="white" font-size="22">Female skeletal registration: held-out bone-centre RMSE (mm)</text>']
    mx=max(v["rmse_mm"] or 0 for s in summary.values() for v in s.values()) or 1
    for i,(g,s) in enumerate(summary.items()):
        y=70+110*i;lines.append(f'<text x="20" y="{y}" fill="white" font-size="16">{g}</text>')
        for j,(k,v) in enumerate(s.items()):
            yy=y+5+j*23;val=v["rmse_mm"]
            lines.append(f'<text x="20" y="{yy+17}" fill="#cbd5e1" font-size="13">{k}</text>')
            if val is not None:
                w=val/mx*580
                lines.append(f'<rect x="190" y="{yy+3}" width="{w}" height="15" fill="{["#8ba3b5","#8ba3b5","#d5ba7e","#d5ba7e"][j]}"/><text x="{200+w}" y="{yy+16}" fill="white" font-size="13">{val:.2f}</text>')
    lines.append('<text x="20" y="414" fill="#cbd5e1" font-size="13">Centre proxies only; neither surface fit nor joint continuity established.</text></svg>')
    (out/"registration-review.svg").write_text("".join(lines))
    print("R226_REGISTRATION",json.dumps(summary))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
