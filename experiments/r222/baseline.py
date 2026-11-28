"""R222 reference-first baseline, no remeshing or cross-donor grafting.
Male: actual BP3D named geometry, female: current HRA native scene.
Separate source provenance, metric frames, semantic inventory and diagnostic images.
"""
import sys, json, hashlib, zipfile, io, re, struct, shutil
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont
BP_PIN="b13e23f595be27237ce69246484fd781553181d91e3ab7bda042bafb9aedd133"
BP_INNER="ac7d9ab0b3d75b4c75445f0f39e3782f309bbb321d2191f449773107ae504793"
def sha(b):return hashlib.sha256(b).hexdigest()
def cat(names):
    s=" ".join(names).lower()
    for k,p in [
        ("pregnancy_reference",r"placenta|umbilical"),("skin",r"(^|[ _])skin([ _]|$)|epidermis|dermis"),
        ("reproductive",r"testis|testicle|epididym|ductus deferens|vas deferens|seminal vesicle|prostate|penis|scrot|cavernos|spongios|glans|uterus|uterine|ovary|ovaries|fallopian|vagina|vulva|clitoris|labium|labia|mammary"),
        ("connective",r"tendon|ligament|cartilage|meniscus|fascia|aponeurosis|intervertebral"),
        ("lymphatic",r"lymph"),("vascular",r"artery|arterial|arteries|vein|veins|venous|vasculature|aorta|vena cava"),
        ("neural",r"brain|nerve|spinal cord|cerebr|cerebell|plexus|allen_brain"),
        ("muscular",r"muscle|musculus|muscular_system"),("skeletal",r"\bbone\b|skeletal_system|femur|tibia|fibula|humerus|ulna|scapula|clavicle|patella|vertebra|sternum|\brib\b|phalanx|metacarpal|metatarsal"),
        ("respiratory",r"lung|trachea|bronch|larynx|diaphragm|respiratory_system"),("digestive",r"stomach|esophagus|intestine|colon|liver|pancreas|gallbladder|digestive_system|rectum"),
        ("urinary",r"kidney|renal|ureter|urethra|bladder|urinary_system"),("endocrine",r"thyroid|pituitary|adrenal|pineal|parathyroid"),("sensory",r"eye|cornea|retina|cochlea|tongue|tooth|teeth|gingiva"),("cardiac",r"heart|atrium|ventricle|myocard"),("other",r".*")]:
        if re.search(p,s):return k
COL={"skin":[.62,.57,.52,1],"skeletal":[.87,.83,.72,1],"muscular":[.61,.22,.22,1],"connective":[.76,.73,.65,1],"vascular":[.66,.22,.28,1],"neural":[.8,.67,.36,1],"lymphatic":[.27,.67,.42,1],"reproductive":[.65,.39,.55,1],"respiratory":[.40,.63,.76,1],"digestive":[.68,.47,.31,1],"urinary":[.54,.34,.42,1],"endocrine":[.8,.63,.31,1],"sensory":[.52,.72,.72,1],"cardiac":[.65,.23,.28,1],"other":[.6,.61,.63,1],"pregnancy_reference":[.6,.43,.58,1]}
def color(k):
    return trimesh.visual.material.PBRMaterial(name=k,baseColorFactor=COL[k],metallicFactor=0,roughnessFactor=.86,doubleSided=True)
def add(scene,m,id,k,tf=None):
    # Retain actual vertices/faces; only presentation material assigned.
    m.visual=trimesh.visual.TextureVisuals(material=color(k))
    scene.add_geometry(m,node_name=id,geom_name=id,transform=tf)
def glb(out,scene):out.write_bytes(scene.export(file_type="glb"))
def raw_obj(raw):
    # Do not repair, weld or simplify reference geometry.
    v=[];f=[]
    for l in raw.decode("utf-8",errors="replace").splitlines():
        t=l.split()
        if not t:continue
        if t[0]=="v":v.append([float(x) for x in t[1:4]])
        elif t[0]=="f":
            ids=[int(x.split("/")[0]) for x in t[1:]];ids=[i-1 if i>0 else len(v)+i for i in ids]
            f.extend((ids[0],ids[j],ids[j+1]) for j in range(1,len(ids)-1))
    v=np.array(v,dtype=np.float64);f=np.array(f,dtype=np.int64)
    assert len(v)>0 and len(f)>0 and f.min()>=0 and f.max()<len(v) and np.isfinite(v).all()
    return trimesh.Trimesh(v,f,process=False)
def male(inp,out):
    raw=(inp/"atlas.zip").read_bytes();assert sha(raw)==BP_PIN
    z=zipfile.ZipFile(io.BytesIO(raw));inner=z.read("geometry.zip");assert sha(inner)==BP_INNER
    inv={x["id"]:x for x in json.loads(z.read("inventory.json"))};assert len(inv)==2234
    scene=trimesh.Scene();rows=[]
    with zipfile.ZipFile(io.BytesIO(inner)) as zz:
        paths={Path(x).stem.upper():x for x in zz.namelist() if x.lower().endswith(".obj")}
        assert set(paths)==set(inv)
        for id in sorted(paths):
            raw=zz.read(paths[id]);rec=inv[id];assert sha(raw)==rec["sha256"]
            m=raw_obj(raw);m.vertices=m.vertices[:,[0,2,1]]*np.array([.001,.001,-.001])
            concepts=rec["mapped_concepts"];names=[x[1] for x in concepts]
            k=cat(names);add(scene,m,id,k)
            rows.append({"id":id,"source_element":id,"concepts":concepts,"category":k,"vertices":len(m.vertices),"triangles":len(m.faces),"bounds_m":m.bounds.tolist(),"source_sha256":rec["sha256"]})
    for f in ("ATTRIBUTION.txt","LICENSE-source.html","LICENSE-update.html","isa_element_parts.txt","isa_parts_list_e.txt","isa_inclusion_relation_list.txt"):(out/f).write_bytes(z.read(f))
    # Source archive retained separately in previously archived R219 evidence.
    return scene,rows,{"source":"BodyParts3D 4.0 99%-reduced official data","source_archive_sha256":BP_INNER,"frame":"source millimetres Z-up to glTF metres Y-up, proper rotation; no shape fitting","source_archive":"R219 artifact 15236959584, source geometry.zip preserved separately","limitations":"Male donor atlas; reduced resolution; source anatomical coverage is incomplete."}
def ancestors(scene,node):
    p=scene.graph.transforms.parents;a=[str(node)];seen={node}
    while node in p:
        node=p[node]
        if node in seen:break
        seen.add(node);a.append(str(node))
    return a
def female(inp,out):
    p=inp/"female.glb";raw=p.read_bytes();assert raw[:4]==b"glTF" and struct.unpack_from("<I",raw,8)[0]==len(raw)
    original=trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
    scene=trimesh.Scene();rows=[];excluded=[]
    for i,node in enumerate(sorted(original.graph.nodes_geometry)):
        matrix,g=original.graph[node];m=original.geometry[g]
        if not isinstance(m,trimesh.Trimesh) or not len(m.faces):continue
        path=ancestors(original,node);names=[str(g),*path]
        if any(re.search(r"landmark|extraction.?site|HubMAP|registration.?block",n,re.I) for n in names):
            excluded.append({"node":str(node),"path":path,"reason":"annotation-like name"});continue
        k=cat(names);id="hra_"+str(i).zfill(4)+"_"+re.sub(r"[^A-Za-z0-9_.-]","_",str(node))[:80]
        q=m.copy();q.apply_transform(matrix);assert np.isfinite(q.vertices).all()
        add(scene,q,id,k)
        rows.append({"id":id,"source_node":str(node),"source_geometry":str(g),"hierarchy":path,"category":k,"vertices":len(q.vertices),"triangles":len(q.faces),"bounds_m":q.bounds.tolist(),"source_transform":matrix.tolist()})
    (out/"excluded-nodes.json").write_text(json.dumps(excluded,indent=2))
    shutil.copyfile(p,out/"original-female.glb")
    (out/"ATTRIBUTION.txt").write_text("Browne, Kristen, and Heidi Schlehlein. 2026. 3D Reference Organ Set for Female, v1.10. HuBMAP Human Reference Atlas. DOI 10.48539/HBM637.DWBM.744. CC BY 4.0 https://creativecommons.org/licenses/by/4.0/\nhttps://humanatlas.io/3d-reference-library\nSource https://cdn.humanatlas.io/digital-objects/ref-organ/united-female/v1.10/assets/3d-vh-f-united.glb\nChanges: original node world transforms baked into separate named meshes, presentation colors, annotation-like nodes excluded from working assembly; unmodified original GLB retained.\n")
    return scene,rows,{"source":"HRA female v1.10","source_sha256":sha(raw),"frame":"original metre Y-up, source node world transforms baked without geometric fitting","excluded_annotation_like_nodes":len(excluded),"limitations":"Selected organs and partial musculoskeletal system, not complete female anatomy; pregnancy reference geometry retained separately."}
def preview(out,scene,rows,sex):
    # Point depth-buffered orthographic witness from actual geometry; no synthetic anatomy.
    groups=defaultdict(list)
    for row in rows:
        m=scene.geometry[row["id"]];k=row["category"]
        if k=="pregnancy_reference":continue
        if len(m.faces)==0:continue
        t=m.vertices[m.faces];area=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1);total=area.sum()
        if total<=0:continue
        n=min(14000,max(30,int(45000*total)));rng=np.random.default_rng(222)
        tri=t[rng.choice(len(t),n,p=area/total)];u=rng.random((n,2));u[u.sum(1)>1]=1-u[u.sum(1)>1];pts=tri[:,0]+u[:,0,None]*(tri[:,1]-tri[:,0])+u[:,1,None]*(tri[:,2]-tri[:,0])
        groups[k].append(pts)
    allp=np.concatenate([p for vals in groups.values() for p in vals]);lo=allp.min(0);hi=allp.max(0);h=hi[1]-lo[1];assert .5<h<3
    im=Image.new("RGB",(1280,820),"#17232f");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",24);small=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
    d.text((15,12),sex.title()+" | reference-first anatomical baseline",font=font,fill="white")
    d.text((15,46),"Actual sampled geometry; same-scale layer views, no inferred structures",font=small,fill="#bac9d7")
    sets=[("Exterior",["skin"]),("Skeleton",["skeletal","connective"]),("Musculature",["muscular"]),("Internal systems",[k for k in groups if k not in ("skin","skeletal","connective","muscular","other")])]
    for i,(label,ks) in enumerate(sets):
        x=i*320;d.text((x+12,86),label,font=font,fill="white")
        if not any(k in groups for k in ks):d.text((x+12,350),"NOT PRESENT",font=small,fill="#e4b887");continue
        pp=[];cc=[]
        for k in ks:
            if k not in groups:continue
            a=np.concatenate(groups[k]);pp.append(a);cc.append(np.tile(np.array(COL[k][:3])*255,(len(a),1)))
        p=np.concatenate(pp);c=np.concatenate(cc);sc=min(680/h,300/max(hi[0]-lo[0],.01));center=(lo[0]+hi[0])/2
        xx=np.rint(x+160+(p[:,0]-center)*sc).astype(int);yy=np.rint(785-(p[:,1]-lo[1])*sc).astype(int)
        valid=(xx>=x)&(xx<x+320)&(yy>=120)&(yy<810);idx=np.argsort(p[valid,2]);coords=np.column_stack((xx[valid],yy[valid]))[idx];colors=c[valid][idx]
        for (a,b),co in zip(coords,colors):d.point((int(a),int(b)),fill=tuple(co.astype(int)))
    im.save(out/"baseline-preview.png")
def main(sex,inp,out):
    out.mkdir(parents=True,exist_ok=False)
    scene,rows,provenance=male(inp,out) if sex=="male" else female(inp,out)
    assert len(rows)>500
    # Preserve all named anatomy, but separate pregnancy-specific data from
    # default nonpregnant adult reference. No topology edits or approximations.
    core=trimesh.Scene();preg=trimesh.Scene();systems=defaultdict(trimesh.Scene)
    for row in rows:
        k=row["category"];id=row["id"];m=scene.geometry[id];dst=preg if k=="pregnancy_reference" else core
        dst.add_geometry(m,node_name=id,geom_name=id);systems[k].add_geometry(m,node_name=id,geom_name=id)
    glb(out/"baseline.glb",core)
    layers=out/"layers";layers.mkdir()
    for k,s in sorted(systems.items()):glb(layers/(k+".glb"),s)
    counts=Counter(r["category"] for r in rows)
    report={"sex":sex,"provenance":provenance,"named_meshes":len(rows),"default_meshes":len(core.geometry),"triangles":sum(r["triangles"] for r in rows),"category_screen":dict(counts),"units":"metres","status":"REFERENCE_BASELINE_NOT_COMPLETE_OR_NATIVE","limitations":["No mesh simplification beyond donor preprocessing; GLB float32 interchange","Category labels heuristic, original IDs retained","No verified complete anatomy, soft-tissue simulation, rig binding, or native Oneirifact generation","No cross-donor geometry grafting"],"files":{}}
    (out/"inventory.json").write_text(json.dumps(rows,indent=2))
    preview(out,scene,rows,sex)
    for f in sorted(out.rglob("*")):
        if f.is_file():report["files"][f.relative_to(out).as_posix()]={"sha256":sha(f.read_bytes()),"bytes":f.stat().st_size}
    (out/"receipt.json").write_text(json.dumps(report,indent=2));print("R222_BASELINE",json.dumps({k:v for k,v in report.items() if k!="files"}))
if __name__=="__main__":main(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]))
