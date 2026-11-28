"""Prepare exact full-weight source variants before motion binding."""
import io,json,sys,zipfile
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from gltf import parse,read,add,encode,sha,worlds
SOURCE="f40250cbed7a5758aac5ffe9bec9f9a535b282e2b0b10f5b9d75dfad316bd34f"
SHARED="025145c2af4dc0c0d8936e764b88dd03a06a9e389197cadf97eb9b1d634d54fc"
def main(source,shared,out,caseid):
    assert sha(source.read_bytes())==SOURCE and sha(shared.read_bytes())==SHARED
    out.mkdir(parents=True,exist_ok=False)
    regression=Path(__file__).with_name("development-regressions.json")
    if regression.exists():out.joinpath(regression.name).write_bytes(regression.read_bytes())
    sex="female" if caseid.startswith("female") else "male";older="older" in caseid
    target=1.55 if "155" in caseid else 1.85 if "185" in caseid else None
    shoe="stilettos" if "stiletto" in caseid else "flats"
    with zipfile.ZipFile(source) as z,zipfile.ZipFile(shared) as sz:
        raw=z.read(sex+"-athletic-animated.glb");r=json.loads(z.read("receipt.json"))
        assert sha(raw)==next(x["glb_sha256"] for x in r["variants"] if x["id"]==sex+"-athletic")
        d,b=parse(raw);attrs=d["meshes"][0]["primitives"][0]["attributes"]
        vertices=read(d,b,attrs["POSITION"]).astype(float);faces=read(d,b,d["meshes"][0]["primitives"][0]["indices"]).reshape(-1,3)
        oldweights={k:read(d,b,i) for k,i in attrs.items() if k.startswith(("JOINTS_","WEIGHTS_"))}
        names=[n["name"] for n in d["nodes"][:163]]
        for fn in ("LICENSE.md","LICENSE.ASSETS.md"):out.joinpath(fn).write_bytes(z.read(fn))
        source_spec=json.loads(z.read(sex+"-athletic-source-spec.json"))
        source_meta={"archive_sha256":SOURCE,"source_glb_sha256":sha(raw),"source_variant":sex+"-athletic","source_spec":source_spec}
        if older:
            oldraw=sz.read("male-older.glb");dr,br=parse(oldraw);p=dr["meshes"][0]["primitives"][0]
            sr=json.loads(sz.read("receipt.json"));row=next(x for x in sr["variants"] if x["id"]=="male-older")
            assert sha(oldraw)==row["model"]["sha256"]
            ov=read(dr,br,p["attributes"]["POSITION"]).astype(float);of=read(dr,br,p["indices"]).reshape(-1,3)
            assert ov.shape==vertices.shape and np.array_equal(faces,of)
            fit=json.loads(sz.read("male-older-rig.json"));assert [x["id"] for x in fit["bones"]]==names
            for i,bone in enumerate(fit["bones"]):
                M=np.array(bone["local_bind"]);d["nodes"][i]["translation"]=M[:3,3].tolist();d["nodes"][i]["rotation"]=Rotation.from_matrix(M[:3,:3]).as_quat().tolist()
            inverse=np.array([x["inverse_bind"] for x in fit["bones"]]);vertices=ov
            source_meta.update(shared_archive_sha256=SHARED,source_variant="male-older",source_morph_glb_sha256=sha(oldraw),
                               source_rig_sha256=sha(sz.read("male-older-rig.json")),source_spec=json.loads(sz.read("male-older-spec.json")))
            morphology_scope="Actual admitted nonuniform donor age/body-shape variant with helper-refitted joints; no inference of biological age or age-specific motion."
        else:
            inverse=read(d,b,d["skins"][0]["inverseBindMatrices"]).reshape(-1,4,4).transpose(0,2,1)
            morphology_scope="Uniform stature adaptation only of the exact athletic donor exterior; not all regional morphology."
        height=float(np.ptp(vertices[:,1]));scale=1. if target is None else target/height
        vertices*=scale
        for n in d["nodes"][:163]:n["translation"]=(np.array(n["translation"])*scale).tolist()
        inverse[:,:3,3]*=scale
        attrs["POSITION"]=add(d,b,vertices.astype("<f4"),target=34962,bounds=True)
        normals=np.zeros_like(vertices);tri=vertices[faces];vn=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        for k in range(3):np.add.at(normals,faces[:,k],vn)
        normals/=np.linalg.norm(normals,axis=1)[:,None];attrs["NORMAL"]=add(d,b,normals.astype("<f4"),target=34962)
        d["skins"][0]["inverseBindMatrices"]=add(d,b,inverse.transpose(0,2,1).reshape(-1,16).astype("<f4"),kind="MAT4")
        d.pop("animations",None);d["asset"]["generator"]="Oneirifact R245 exact full-weight morphology-before-motion source"
        packed=encode(d,b);out.joinpath("bound-source.glb").write_bytes(packed)
        dd,bb=parse(packed);attr=dd["meshes"][0]["primitives"][0]["attributes"]
        assert all(np.array_equal(read(dd,bb,attr[k]),v) for k,v in oldweights.items())
        W,parents=worlds(dd);names=[x["name"] for x in dd["nodes"][:163]];ix={n:i for i,n in enumerate(names)}
        ib=read(dd,bb,dd["skins"][0]["inverseBindMatrices"]).reshape(-1,4,4).transpose(0,2,1)
        assert np.max(abs(W@ib-np.eye(4)))<2e-6
        j=lambda name:W[ix[name],:3,3]
        ids=np.concatenate([read(dd,bb,attr["JOINTS_"+str(i)]) for i in range(3)],axis=1)
        weights=np.concatenate([read(dd,bb,attr["WEIGHTS_"+str(i)]) for i in range(3)],axis=1)
        feet={};foot_vertex_ids={}
        for side in ("L","R"):
            relevant=[i for i,n in enumerate(names) if n=="foot."+side or n.startswith("toe") and n.endswith("."+side)]
            mask=(np.isin(ids,relevant)*weights).sum(1)>.5
            pts=vertices[mask];assert len(pts)>100
            ankle=j("foot."+side);toeheads=np.array([j("toe"+str(k)+"-1."+side) for k in range(1,6)])
            sole_y=float(pts[:,1].min());fore=toeheads.mean(0);fore[1]=sole_y
            heel=np.array([ankle[0],sole_y,float(pts[:,2].min()+.04*np.ptp(pts[:,2]))])
            toe=np.array([fore[0],sole_y,float(pts[:,2].max()-.015*np.ptp(pts[:,2]))])
            feet[side]={"heel_from_ankle_m":(heel-ankle).tolist(),"forefoot_from_ankle_m":(fore-ankle).tolist(),"toe_from_ankle_m":(toe-ankle).tolist(),"toe_pivot_from_ankle_m":(j("toe3-1."+side)-ankle).tolist(),"width_m":float(np.ptp(pts[:,0]))}
            foot_vertex_ids[side]=np.flatnonzero(mask).tolist()
        hip=(j("upperleg01.L")+j("upperleg01.R"))/2
        morphology={"id":caseid,"source_bind_sha256":sha(packed),"source_revision":source_meta["source_variant"],"stature_m":float(np.ptp(vertices[:,1])),
                    "hip_center_m":hip.tolist(),"hips_m":{s:j("upperleg01."+s).tolist() for s in ("L","R")},
                    "knees_m":{s:j("lowerleg01."+s).tolist() for s in ("L","R")},"ankles_m":{s:j("foot."+s).tolist() for s in ("L","R")},"feet":feet,
                    "shoulder_width_m":float(np.linalg.norm(j("upperarm01.L")-j("upperarm01.R"))),
                    "landmarks_m":{"head":j("head").tolist(),"mouth":(j("jaw")+np.array([0,-.015*scale,.045*scale])).tolist(),
                                  **{"shoulder_"+s:j("upperarm01."+s).tolist() for s in ("L","R")},**{"wrist_"+s:j("wrist."+s).tolist() for s in ("L","R")}},
                    "measurement_notes":"Source helper-fitted bone heads; sole markers from weighted foot geometry, forefoot at mean first-toe head projected to minimum plantar Y; mechanical toe proxy hinge is the actual middle-toe toe3-1 joint head; mouth is jaw-relative authored proxy, not dental contact landmark."}
        case={"schema":"oneirifact.motion-source-case/v1","id":caseid,"sex_variant":sex,"shoe_profile":shoe,"source":source_meta,"morphology":morphology,
              "morphology_scope":morphology_scope,"uniform_stature_scale":scale,"foot_vertex_ids":foot_vertex_ids,
              "body_mesh_vertices":len(vertices),"body_mesh_triangles":len(faces),"original_rig_bones":len(names),"max_skin_influences":int((weights>0).sum(1).max()),
              "positive_skin_influences":int((weights>0).sum()),"omitted_layers":["anatomical skeletal meshes","organs","muscles/tendons/ligaments/cartilage","physiological soft-tissue systems"],
              "support_geometry":"Original authored rigid shoe support proxy; not fitted footwear design."}
        out.joinpath("case.json").write_text(json.dumps(case,indent=2)+"\n")
        print("R245_PREPARED",json.dumps({k:case[k] for k in ("id","body_mesh_vertices","body_mesh_triangles","original_rig_bones","max_skin_influences","positive_skin_influences","uniform_stature_scale")}),flush=True)
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4])

