"""Regional adult design controls; fixed source references are never mutated.
This is an original bounded additive exterior design experiment, not the full
MakeHuman macro runtime, tissue mechanics, or clinical anthropometry.
"""
import argparse, hashlib,json,sys,tempfile,zipfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"r232"))
import morphology as m
LOCK=Path(__file__).with_name("regional-targets.json")
PIN="98f119556087dddfce98028501fe459b61c746f0094cf0e09c6b7f0dc7461e49"
def sha(b):return hashlib.sha256(b).hexdigest()
def require(q,msg):
    if not q:raise ValueError(msg)
def source(archive,folder):
    require(sha(archive.read_bytes())==PIN,"source archive digest")
    with zipfile.ZipFile(archive) as z:
        for i in z.infolist():
            if not i.filename.startswith("source/") or i.is_dir():continue
            n=Path(i.filename);require(len(n.parts)==2 and 0<i.file_size<=16<<20,"source path/budget")
            (folder/n.name).write_bytes(z.read(i))
    return m.load(folder)
def region_load(folder,lock):
    def load(row):
        path,h=row;name=Path(path).name+".target";raw=(folder/name).read_bytes()
        require(b"CC0" in raw[:1000],"missing per-file CC0 notice")
        return m.delta(folder/name,h)
    regions={k:sum((load(r) for r in rows),np.zeros((19158,3))) for k,rows in lock["regional"].items()}
    breast={k:np.stack([load(r) for r in rows]) for k,rows in lock["breast"].items()}
    require(len(regions)==11 and all(a.shape==(4,19158,3) for a in breast.values()),"basis inventory")
    return regions,breast
def params(base,**kw):
    regional={k:0. for k in lock["regional"]};regional.update({"breast_size":.5,"breast_firmness":.5})
    regional.update(kw)
    require(set(regional)==set(lock["regional"])|{"breast_size","breast_firmness"},"unknown regional field")
    require(all(type(x) in (int,float) and np.isfinite(x) and 0<=x<=1 for x in regional.values()),"bounded adult controls")
    return {"schema":"oneirifact.adult-regional-morphology/v1","base":m.validate(base),"regional":regional}
def shape(s,v,targets,regions,breast):
    b=m.validate(s["base"]);p=s["regional"];a=(b["age_years"]-25)/65;mus,w=b["muscularity"],b["mass_morph"]
    q=v.copy()
    for stage,alpha,anchors in (("young",1-a,m.ADULT["female"]),("old",a,m.OLD)):
        q+=alpha*sum((targets[n] for n,h in anchors),np.zeros_like(v))/3
        for (mi,wi),(n,h) in m.MACRO[stage].items():
            q+=alpha*(mus if mi else 1-mus)*(w if wi else 1-w)*targets[n]
        # Relative to midpoint at fixed max-muscle/average-weight source
        # corners. These are design coordinates, not cup sizes or elasticity.
        size,firm=p["breast_size"],p["breast_firmness"]
        coeff=np.array([(1-size)*(1-firm),(1-size)*firm,size*(1-firm),size*firm])-.25
        q+=alpha*np.einsum("i,ivc->vc",coeff,breast[stage])
    for (n,h),k in zip(m.REGION,("torso_depth","torso_width","torso_length","torso_vshape")):q+=b[k]*targets[n]
    for k,d in regions.items():q+=p[k]*d
    q[:,2]-=q[:13380,2].min()
    q*=b["height_m"]/np.ptp(q[:13380,2])
    require(np.isfinite(q).all(),"nonfinite regional shape")
    return q[:,[0,2,1]]*np.array([1,1,-1])
def quality(v,f):
    t=v[f];a=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)
    e=np.linalg.norm(t[:,[1,2,0]]-t,axis=2)
    return {"degenerate_triangles":int(np.sum(a<1e-12)),"max_edge_m":float(e.max()),"surface_area_m2":float(a.sum()/2)}
def main(archive,folder,out):
    out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as td:
        v,f,targets,pins,rig=source(archive,Path(td))
        regions,breast=region_load(folder,lock)
        base=m.profile(muscularity=.85,mass_morph=.55,torso_vshape=.2)
        neutral=params(base);q0=shape(neutral,v,targets,regions,breast)
        require(np.max(abs(q0-m.shape(base,v,targets)))<1e-12,"zero regional compatibility")
        # Qualify each independent control on actual source-supported vertices.
        controls=[]
        for k in neutral["regional"]:
            s=params(base,**{k:.9 if k.startswith("breast_") else .6})
            q=shape(s,v,targets,regions,breast);d=np.linalg.norm(q[:13380]-q0[:13380],axis=1)
            require(d.max()>1e-4,"ineffective control "+k)
            controls.append({"field":k,"max_displacement_mm":float(d.max()*1000),"rms_displacement_mm":float(np.sqrt(np.mean(d*d))*1000),"vertices_moved_over_1mm":int(np.sum(d>.001))})
        high={"shoulder":.55,"upper_arm":.45,"thigh":.55,"calf":.5,"back":.5,"pectoral":.25,"abdomen":.6}
        cases={"r232-athletic":neutral,"strength-athletic":params(base,**high),"endurance-athletic":params(m.profile(muscularity=.65,mass_morph=.35,torso_vshape=.15),shoulder=.2,upper_arm=.2,thigh=.35,calf=.45,abdomen=.45),"older-strength":params(m.profile(age_years=65,muscularity=.85,mass_morph=.55,torso_vshape=.2),**high),"proportion-study":params(base,hip_width=.3,hip_depth=.2,upper_leg_length=.35,lower_leg_length=.2),"breast-size-study":params(base,breast_size=.75),"breast-shape-study":params(base,breast_firmness=.75)}
        rows=[];views=[]
        for name,s in cases.items():
            q=shape(s,v,targets,regions,breast)
            require(abs(np.ptp(q[:13380,1])-s["base"]["height_m"])<1e-10,"height")
            require(np.array_equal(q,shape(s,v,targets,regions,breast)),"nondeterministic")
            posed,fit=m.pose(q,s["base"],rig)
            stats=quality(q[:13380],f)
            require(stats["degenerate_triangles"]<=quality(q0[:13380],f)["degenerate_triangles"]+5,"excess degenerate triangles")
            model=m.write_model(out,name+".glb",posed,f)
            (out/(name+"-spec.json")).write_text(json.dumps(s,indent=2)+"\n")
            rows.append({"id":name,"spec":s,"model":model,"shape_bounds":m.measure(q[:13380]),"quality_screen":stats,"rig_bones":len(fit["bones"])})
            if not name.startswith("breast-"):views.append((name,posed,f,s["base"]))
        m.render(out,views)
        report={"schema":"oneirifact.regional-morphology-qualification/v1","base_archive_sha256":PIN,"upstream":lock["upstream"],"controls":controls,"variants":rows,"source_note":"Pinned CC0 additive regional exterior offsets. Breast size/firmness relative to fixed-condition midpoint of adult donor targets; old min-cup firmness endpoints identical upstream. No true cup size, tissue mechanics, muscle volume, internal anatomy binding, collision/self-intersection qualification or native execution."}
        (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
        (out/"regional-targets.json").write_bytes(LOCK.read_bytes())
        print("R234_REGIONAL_MORPHOLOGY",json.dumps({"controls":controls,"models":len(rows),"variants":[r["id"] for r in rows],"status":"DESIGN_GEOMETRY_WITNESS_ONLY"}),flush=True)
lock=json.loads(LOCK.read_text())
if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("archive",type=Path);a.add_argument("folder",type=Path);a.add_argument("out",type=Path);q=a.parse_args();main(q.archive,q.folder,q.out)
