"""Correct broad condylar fitting defect using same-donor opposing surfaces.
Fixed candidate selection and contiguous withheld contact patch; compare
all methods on the exact same held-out points. Not clinical contact mechanics.
"""
import hashlib,json,sys,zipfile
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from scipy.optimize import least_squares
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"ct"))
import leg
def fit(x):
    m=x.mean(0);q=x-m;A=np.column_stack((2*q,np.ones(len(q))))
    p=np.linalg.lstsq(A,np.sum(q*q,axis=1),rcond=None)[0];c=p[:-1]+m
    rad=np.sqrt(max(0,p[-1]+np.dot(p[:-1],p[:-1])))
    r=least_squares(lambda a:np.linalg.norm(x-a[:-1],axis=1)-a[-1],np.r_[c,rad],loss="soft_l1",f_scale=.0015,max_nfev=100)
    leg.need(r.success and np.isfinite(r.x).all(),"solver")
    return r.x
def measure(m,test):
    d=abs(np.linalg.norm(test-m[:-1],axis=1)-m[-1])*1000
    return {"rms_mm":float(np.sqrt(np.mean(d*d))),"p95_mm":float(np.quantile(d,.95)),"max_mm":float(d.max()),"radius_mm":float(m[-1]*1000),"radius_domain":bool(.012<m[-1]<.05),"fit_center_m":m[:-1].tolist()}
def run(src,out):
    with src.open("rb") as f:leg.need(hashlib.file_digest(f,"sha256").hexdigest()==leg.PIN,"source digest")
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    with zipfile.ZipFile(src) as z:
        r=json.loads(z.read("receipt.json"));records=r["inventory"]
        for side in ("LEFT","RIGHT"):
            def get(n):return leg.load(z,next(x for x in records if x["id"].endswith(n+"_"+side)))
            fem=get("FEMUR");tib=get("TIBIA");v=fem.vertices
            bot=v[v[:,2]<v[:,2].min()+.045];mid=np.median(bot[:,0]);dist=cKDTree(tib.vertices).query(bot)[0]
            for label,sel in (("low_x",bot[:,0]<mid-.004),("high_x",bot[:,0]>mid+.004)):
                # Predetermined 8mm nearest opposing-vertex distance; not
                # cartilage contact, segmentation of articular surfaces or
                # a signed distance field. Same fixed withheld patch for all.
                p=bot[sel&(dist<.008)];cut=np.quantile(p[:,1],.25)
                a=p[p[:,1]>=cut];b=p[p[:,1]<cut];broad=bot[sel&(bot[:,1]>=cut)]
                leg.need(len(a)>100 and len(b)>100 and np.max(b[:,1])<cut and np.min(broad[:,1])>=cut,"spatial leakage")
                methods={"broad_sphere":measure(fit(broad),b),"contact_sphere":measure(fit(a),b),"fixed_transverse_cylinder":measure(fit(a[:,1:]),b[:,1:])}
                leg.need(methods["broad_sphere"]["radius_domain"] and methods["contact_sphere"]["radius_domain"],"sphere radius")
                rows.append({"side":side,"condyle":label,"broad_training":len(broad),"contact_training":len(a),"heldout":len(b),"split_y_m":float(cut),"heldout_vertices_sha256":hashlib.sha256(b.astype("<f8").tobytes()).hexdigest(),"methods":methods})
    improved=sum(r["methods"]["contact_sphere"]["rms_mm"]<r["methods"]["broad_sphere"]["rms_mm"] for r in rows)
    result={"schema":"oneirifact.ct-condyle-contact-screen/v1","source_sha256":leg.PIN,"fixed_contact_distance_m":.008,"heldout_common":True,"contact_sphere_improved":improved,"condyles":rows,"status":"HOLD_ANATOMICAL_JOINT_ADMISSION","scope":"Same-donor opposing vertex proximity and constrained patch selection; not cartilage contact, full condyle geometry, rolling/sliding or physiological knee axis. No admission or retrospective selection on held-out results. Need independent joint surface labels, joint kinematics, contact and additional donors."}
    (out/"receipt.json").write_text(json.dumps(result,indent=2)+"\n")
    print("R239_CONTACT_SCREEN",json.dumps(result),flush=True)
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
