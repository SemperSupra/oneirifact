"""Read the original HRA united male/female reference assembly; preserve shared
donor transforms and node identities. No cross-donor registration or clinical claims.
"""
import sys,json,hashlib,zipfile,io,re
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont
from human_inverse import combine,split,sample,metrics,obj
EXPECTED={"male":"79f916b66a95a203f7534c8ecbb4a28016223a0f","female":"a52ad0fad109b6eaadadea1c7cca5d50d801d2dc"}
# Explicit observed atlas hierarchy roots, not fuzzy leaf names.
ROOTS={"skin":["skin"],"brain":["@Allen_brain"],"heart":["heart"],"lungs":["lungs"],"liver":["liver"],"kidneys":["kidney"],"spleen":["spleen"],"pancreas":["pancreas"],"intestines":["colon","small_intestine"],"gallbladder":["gallbladder","gallbladder_"],"bladder":["urinary_bladder"],"prostate":["prostate_gland"],"uterus":["uterus"],"ovaries":["ovary"],"fallopian_tubes":["fallopian_tube"]}
COLORS={"gallbladder":(115,180,115),"brain":(192,155,179),"heart":(214,78,80),"lungs":(122,174,205),"liver":(162,93,60),"kidneys":(170,105,90),"spleen":(161,121,194),"pancreas":(232,191,106),"intestines":(210,156,114),"bladder":(116,193,175),"prostate":(150,175,205),"uterus":(191,129,177),"ovaries":(228,171,190),"fallopian_tubes":(218,148,170)}
def gitblob(raw):return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def classify(names,sex):
    if any(re.search(r"landmark|extraction_site|HuBMAP|blood_vasculature",name,re.I) for name in names):return None
    prefix="VH_M_" if sex=="male" else "VH_F_"
    for k,roots in ROOTS.items():
        allowed={x[1:] if x.startswith("@") else prefix+x for x in roots}
        if any(x in allowed for x in names):return k
def node_path(scene,node):
    parents=scene.graph.transforms.parents;names=[str(node)];seen={node}
    while node in parents:
        node=parents[node]
        if node in seen:break
        names.append(str(node));seen.add(node)
    return names
def render(out,skin,organs,sex):
    im=Image.new("RGB",(1100,920),"#17212b");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",25);small=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",17)
    d.text((25,18),sex.title()+" | HRA anatomical reference assembly",font=font,fill="white")
    d.text((25,54),"Original shared donor frame; skin silhouette and actual sampled organ surfaces",font=small,fill="#b9cad8")
    sv=skin.vertices;lo=sv.min(0);hi=sv.max(0);height=hi[2]-lo[2];scale=730/height
    for i,axis in enumerate((0,1)):
        cx=260+i*460;cy=835;center=(lo[axis]+hi[axis])/2
        def project(v):return np.column_stack((cx+(v[:,axis]-center)*scale,cy-(v[:,2]-lo[2])*scale))
        # Filled exterior silhouette; draw internal surfaces over it, not an
        # occlusion or clinical cutaway proof.
        px=project(sv)
        for tri in skin.faces[::max(1,len(skin.faces)//180000)]:
            d.polygon([tuple(px[j]) for j in tri],fill="#394957")
        pts=[];colors=[]
        for k,m in organs.items():
            p=sample(m.vertices,m.faces,3000,217+i)
            pts.append(p);colors.extend([COLORS[k]]*len(p))
        if pts:
            pts=np.concatenate(pts);p=project(pts)
            for j in np.argsort(pts[:,1-axis]):
                x,y=p[j];d.ellipse((x-1.3,y-1.3,x+1.3,y+1.3),fill=colors[j])
        d.text((cx-50,855),"Front" if axis==0 else "Side",font=small,fill="white")
    for i,k in enumerate(organs):
        x=860;y=110+i*33;d.rectangle((x,y,x+18,y+18),fill=COLORS[k]);d.text((x+26,y-2),k.replace("_"," "),font=small,fill="white")
    im.save(out/"anatomy-preview.png")
def main(inp,out,sex):
    out.mkdir(parents=True,exist_ok=False);raw=(inp/"united.zip").read_bytes()
    assert gitblob(raw)==EXPECTED[sex],"HRA archive identity"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=[i for i in z.infolist() if i.filename.lower().endswith(".glb") and not i.is_dir()]
        assert len(entries)==1 and entries[0].file_size<300*1024*1024
        glb=z.read(entries[0])
    assert glb[:4]==b"glTF"
    scene=trimesh.load(io.BytesIO(glb),file_type="glb",force="scene",process=False)
    assert len(scene.geometry)>0
    inventory=[];groups={}
    # glTF metre Y-up -> metric Z-up, exact rigid rotation. Preserve source GLB.
    R=np.array([[1.,0,0,0],[0,0,-1.,0],[0,1.,0,0],[0,0,0,1.]])
    for node in scene.graph.nodes_geometry:
        matrix,geom=scene.graph[node];names=node_path(scene,node);m=scene.geometry[geom]
        if not isinstance(m,trimesh.Trimesh) or len(m.faces)==0:continue
        category=classify(names,sex)
        inventory.append({"node":str(node),"geometry":str(geom),"ancestors":names,"category":category,"triangles":len(m.faces),"transform":matrix.tolist()})
        if category:
            q=m.copy();q.apply_transform(R@matrix);groups.setdefault(category,[]).append(q)
    (out/"node-inventory.json").write_text(json.dumps(inventory,indent=2))
    print("R217_HRA_GROUPS",json.dumps({k:len(v) for k,v in groups.items()}))
    assert "skin" in groups and len(groups)>=5,"reference node classification incomplete"
    merged={k:trimesh.util.concatenate(v) for k,v in groups.items()}
    skin=merged.pop("skin");height=float(np.ptp(skin.vertices[:,2]))
    assert .8<height<2.5,"skin scale or axes unqualified"
    organs={k:m for k,m in merged.items() if k in COLORS}
    assert all(k in organs for k in ("brain","heart","lungs","liver","kidneys","bladder","intestines","gallbladder")),"essential organ groups missing"
    assert ("prostate" in organs) if sex=="male" else all(k in organs for k in ("uterus","ovaries","fallopian_tubes"))
    # Keep exact source archive, independent grouped exports, and shared frame.
    import shutil
    shutil.copyfile(inp/"united.zip",out/"HRA-united-source.zip")
    shutil.copyfile(inp/"LICENSE",out/"HRA-LICENSE.txt")
    (out/"ATTRIBUTION.txt").write_text("Human Reference Atlas / HuBMAP, CCF 3D Reference Object Library, CC BY 4.0 https://creativecommons.org/licenses/by/4.0/\nSource: https://github.com/hubmapconsortium/ccf-3d-reference-object-library/tree/f1a3a63f110e27ff0736047d52d04dba5d3087f9\nChanges: selected observed organ ancestor groups, excluded landmarks/extraction sites and vasculature, baked shared transforms, rigid Y-up to Z-up conversion, display colors, independent approximate procedural fits. Original archive unchanged. Educational research only; no clinical or individualized anatomy claim.\n")
    result=[];organ_scene=trimesh.Scene();skin_lo,skin_hi=skin.bounds
    organ_dir=out/"organs";organ_dir.mkdir()
    for k,m in organs.items():
        v=m.vertices;f=m.faces
        assert np.isfinite(v).all()
        m.visual=trimesh.visual.ColorVisuals(mesh=m,vertex_colors=np.tile([*COLORS[k],255],(len(v),1)))
        organ_scene.add_geometry(m,node_name=k,geom_name=k)
        # Metric world-frame OBJ, no inferred anatomical rescaling.
        obj(organ_dir/(k+".obj"),v,f)
        train=sample(v,f,9000,217);val=sample(v,f,12000,218);test=sample(v,f,18000,219)
        fits=[]
        for n in (1,4,12):
            pv,pf,params=combine(split(train,n),"ellipsoid");score=metrics(val,sample(pv,pf,12000,220));fits.append((score["rmse_mm"],n,pv,pf,params,score))
        _,n,pv,pf,params,score=min(fits,key=lambda x:x[0])
        obj(organ_dir/(k+"-candidate.obj"),pv,pf)
        (organ_dir/(k+"-candidate.json")).write_text(json.dumps({"kind":"experimental ellipsoid assembly, not native graph","parameters":params},indent=2))
        b=m.bounds;contained=bool(np.all(b[0]>=skin_lo-1e-5) and np.all(b[1]<=skin_hi+1e-5))
        result.append({"organ":k,"triangles":len(f),"bounds_m":b.tolist(),"aabb_inside_skin_aabb":contained,"surface_containment":"NOT_RUN","selected_ellipsoids":n,"heldout_sampled_surface":metrics(test,sample(pv,pf,18000,221))})
    # Export GLB in standard Y-up; no new anatomy, no loss of organ identity.
    organ_scene.apply_transform(np.linalg.inv(R))
    (out/"internal-organs.glb").write_bytes(organ_scene.export(file_type="glb"))
    skin_scene=trimesh.Scene(skin.copy());skin_scene.apply_transform(np.linalg.inv(R))
    (out/"skin-reference.glb").write_bytes(skin_scene.export(file_type="glb"))
    # Optional body context model with independently named organ geometry.
    combined=organ_scene.copy()
    ghost=skin.copy()
    ghost.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name="skin_context",baseColorFactor=[160,180,200,45],alphaMode="BLEND",doubleSided=True,metallicFactor=0.0,roughnessFactor=1.0))
    ghost.apply_transform(np.linalg.inv(R))
    combined.add_geometry(ghost,node_name="skin_context",geom_name="skin_context")
    (out/"body-with-organs.glb").write_bytes(combined.export(file_type="glb"))
    render(out,skin,organs,sex)
    report={"sex":sex,"source":"HRA United v1.2 CC BY 4.0","source_git_blob":EXPECTED[sex],"skin_height_m":height,"skin_triangles":len(skin.faces),"skin_watertight_diagnostic":bool(skin.is_watertight),"organs":result,"scope":"Original source shared frame, exact observed organ ancestor grouping, landmarks/extraction sites/vasculature excluded, AABB diagnostic only. No surface containment, inter-organ collision, clinical validation, MakeHuman registration, native graph or articulated runtime qualification."}
    (out/"receipt.json").write_text(json.dumps(report,indent=2));print("R217_HRA",json.dumps(report))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
