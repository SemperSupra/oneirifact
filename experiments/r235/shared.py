"""Shared adult exterior design kernel and refitted joint inventory.
Appearance blending is not anatomical sex or gender identity.
Never infer organ topology from a surface coefficient.
"""
import json,sys,tempfile,hashlib
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"r234"))
import regional as r
m=r.m
PIN=Path(__file__).with_name("male-targets.json")
def req(x,msg):
    if not x:raise ValueError(msg)
def validate(s):
    req(set(s)=={"schema","common","appearance_mix","regional","anatomical_configuration"} and s["schema"]=="oneirifact.shared-adult-morphology/v1","schema")
    m.validate(s["common"]) # legacy common numerical fields, not anatomy identity
    a=s["appearance_mix"];req(type(a) in (float,int) and np.isfinite(a) and 0<=a<=1,"appearance")
    req(set(s["regional"])==set(r.lock["regional"]),"regional inventory")
    req(all(type(x) in (int,float) and np.isfinite(x) and 0<=x<=1 for x in s["regional"].values()),"regional bounds")
    req(s["anatomical_configuration"] in ("UNSPECIFIED","male_reference","female_reference"),"explicit configuration")
    return s
def spec(common,mix,config="UNSPECIFIED",**regional):
    p={k:0. for k in r.lock["regional"]};p.update(regional)
    return validate({"schema":"oneirifact.shared-adult-morphology/v1","common":common,"appearance_mix":mix,"regional":p,"anatomical_configuration":config})
def bases(v,targets,folder,lock):
    female={};male={}
    for stage,anchors in (("young",m.ADULT["female"]),("old",m.OLD)):
        female[stage]=np.stack([sum((targets[n] for n,h in anchors),np.zeros_like(v))/3]+[targets[m.MACRO[stage][k][0]] for k in ((1,0),(1,1),(0,0))])
        arr={}
        for name,h in lock[stage]["anchors"]+lock[stage]["macro"]:
            p=folder/(name+".target");req(b"CC0" in p.read_bytes()[:1000],"source rights")
            arr[name]=m.delta(p,h)
        male[stage]=np.stack([sum((arr[n] for n,h in lock[stage]["anchors"]),np.zeros_like(v))/3]+[arr[n] for n,h in lock[stage]["macro"]])
    return female,male
def shape(s,v,targets,female,male,regions):
    validate(s);b=s["common"];age=(b["age_years"]-25)/65;t=s["appearance_mix"];mus,w=b["muscularity"],b["mass_morph"]
    c=np.array([1,mus*(1-w),mus*w,(1-mus)*(1-w)])
    q=v.copy()
    for stage,weight in (("young",1-age),("old",age)):
        q+=weight*np.einsum("i,ivc->vc",c,(1-t)*female[stage]+t*male[stage])
    for (n,h),key in zip(m.REGION,("torso_depth","torso_width","torso_length","torso_vshape")):q+=b[key]*targets[n]
    for key,d in regions.items():q+=s["regional"][key]*d
    q[:,2]-=q[:13380,2].min();q*=b["height_m"]/np.ptp(q[:13380,2])
    req(np.isfinite(q).all(),"finite coordinates")
    return q[:,[0,2,1]]*np.array([1,1,-1])
def main(archive,folder,out):
    out.mkdir(parents=True,exist_ok=False)
    lock=json.loads(PIN.read_text())
    with tempfile.TemporaryDirectory() as td:
        v,f,targets,pins,rig=r.source(archive,Path(td))
        regions,_=r.region_load(folder,r.lock)
        female,male=bases(v,targets,folder,lock)
        default=m.profile(muscularity=.85,mass_morph=.55,torso_vshape=.2)
        def gen(s):return shape(s,v,targets,female,male,regions)
        q=gen(spec(default,0,"female_reference"))
        req(np.max(np.abs(q-m.shape(default,v,targets)))<1e-12,"female legacy parity")
        # Explicit module selection cannot affect exterior compatibility in this lane.
        req(np.array_equal(q,gen(spec(default,0,"male_reference"))),"implicit organ inference")
        # Regional controls available at both exterior endpoints.
        control_rows=[]
        for label,t in (("female",0),("male",1)):
            q=gen(spec(default,t))
            for k in regions:
                q1=gen(spec(default,t,**{k:.6}));diff=np.linalg.norm(q1[:13380]-q[:13380],axis=1)
                req(diff.max()>1e-4,label+" ineffective "+k)
                control_rows.append({"endpoint":label,"field":k,"max_displacement_mm":float(diff.max()*1000)})
        strength={"shoulder":.55,"upper_arm":.45,"thigh":.55,"calf":.5,"back":.5,"pectoral":.25,"abdomen":.6}
        cases={"female-athletic":spec(default,0,"female_reference",**strength),"male-athletic":spec(default,1,"male_reference",**strength),"intermediate-appearance":spec(default,.5,"UNSPECIFIED",**strength),"male-older":spec(m.profile(age_years=65,muscularity=.85,mass_morph=.55),1,"male_reference",**strength),"male-tall":spec(m.profile(height_m=1.85,muscularity=.85,mass_morph=.55),1,"male_reference",**strength),"male-flexion":spec(m.profile(spine_flexion_deg=15,muscularity=.85,mass_morph=.55),1,"male_reference",**strength)}
        rows=[]
        for name,s in cases.items():
            q=gen(s);req(np.array_equal(q,gen(s)),"deterministic shape")
            req(abs(np.ptp(q[:13380,1])-s["common"]["height_m"])<1e-9,"metric stature")
            pv,fit=m.pose(q,s["common"],rig)
            model=m.write_model(out,name+".glb",pv,f)
            (out/(name+"-spec.json")).write_text(json.dumps(s,indent=2)+"\n")
            (out/(name+"-rig.json")).write_text(json.dumps(fit,indent=2)+"\n")
            rows.append({"id":name,"model":model,"rig_bones":len(fit["bones"]),"bounds":m.measure(q[:13380]),"anatomical_configuration":s["anatomical_configuration"],"internal_geometry_status":"NOT_GENERATED"})
        a,b=gen(cases["male-athletic"]),gen(cases["female-athletic"])
        req(float(np.max(abs(a-b)))>.01,"endpoint difference")
        # Shape-dependent joint centres are evaluated and recorded separately.
        rig_a=m.skeleton(a,rig);rig_b=m.skeleton(b,rig)
        ja,jb=rig_a[3],rig_b[3];req(set(ja)==set(jb) and len(ja)==326,"joint identity")
        movement=np.array([np.linalg.norm(ja[n]-jb[n]) for n in sorted(ja)])
        req(float(movement.max())>.001,"joint refit ineffective")
        report={"schema":"oneirifact.shared-adult-morphology-qualification/v1","variants":rows,"shared_regional_controls":control_rows,"joint_refit":{"matched_helper_joints":len(ja),"max_endpoint_displacement_mm":float(movement.max()*1000),"rms_endpoint_displacement_mm":float(np.sqrt(np.mean(movement**2))*1000)},"source_pins":{"male":lock,"female_base_archive":r.PIN,"regional":r.lock},"limits":"Adult appearance-only same-topology blending, not gender inference or reproductive topology. Existing female-specific breast controls separate; male/common chest variants and coupled actual bone/organ geometry not admitted. common.sex legacy numerical adapter tag is female only and must not be interpreted as anatomical configuration. Animation rig joint positions are not anatomical joint surfaces."}
        (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
        print("R235_SHARED_MORPHOLOGY",json.dumps({"variants":len(rows),"shared_control_tests":len(control_rows),"joint_refit":report["joint_refit"],"status":"EXTERIOR_AND_RIG_ONLY"}),flush=True)
if __name__=="__main__":main(*(Path(x) for x in sys.argv[1:]))
