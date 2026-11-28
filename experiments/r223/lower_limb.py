"""Acquire actual published female lower-limb musculoskeletal geometry.
Source rights and shared donor frame retained; no alignment to HRA implied.
"""
import sys,hashlib,zipfile,json,io,re
from pathlib import Path
from collections import Counter
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont
def sha(b):return hashlib.sha256(b).hexdigest()
def main(src,out):
    out.mkdir(parents=True,exist_ok=False)
    scene=trimesh.Scene();rows=[];pts=[]
    cols={"bone":[.85,.81,.71,1],"muscle":[.68,.29,.27,1],"cartilage":[.36,.68,.71,1],"ligament":[.85,.75,.40,1],"fat":[.79,.69,.44,1],"other":[.58,.62,.68,1]}
    with zipfile.ZipFile(src) as z:
        entries=[i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(".stl") and "__MACOSX" not in i.filename]
        assert 80<=len(entries)<=300,len(entries)
        assert sum(i.file_size for i in entries)<800<<20
        for j,i in enumerate(sorted(entries,key=lambda i:i.filename)):
            raw=z.read(i);m=trimesh.load(io.BytesIO(raw),file_type="stl",force="mesh",process=False)
            assert len(m.faces)>0 and np.isfinite(m.vertices).all()
            name=Path(i.filename).stem;parts=re.split(r"[_ -]+",name.lower())
            kind=next((x for x in ("bone","muscle","cartilage","ligament","fat") if x in parts),"other")
            side="left" if "left" in parts else "right" if "right" in parts else "midline_or_unknown"
            # Exact STL source preserved separately; mm -> metres, no shape alteration.
            m.vertices*=.001;m.merge_vertices(merge_tex=False,merge_norm=False,digits_vertex=12)
            id=f"vhf_{j:03d}";m.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name=kind,baseColorFactor=cols[kind],metallicFactor=0,roughnessFactor=.8))
            scene.add_geometry(m,node_name=id,geom_name=id)
            rows.append({"id":id,"source":i.filename,"label":name,"category":kind,"side":side,"source_sha256":sha(raw),"triangles":len(m.faces),"bounds_m":m.bounds.tolist()})
            pts.append((m.vertices[::max(1,len(m.vertices)//6000)],kind))
    assert .4<max(scene.extents)<1.8,scene.extents
    (out/"female-lower-limb-original-frame.glb").write_bytes(scene.export(file_type="glb"))
    # CT donor axis orientation is not inferred from the name: use the longest
    # bounding dimension vertically, label as projection not anatomical front.
    lo,hi=scene.bounds;axis=int(np.argmax(hi-lo));others=[x for x in range(3) if x!=axis]
    im=Image.new("RGB",(1100,850),"#17232f");d=ImageDraw.Draw(im);f=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",22);sm=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
    d.text((20,12),"Visible Human Female | published lower-limb geometry",font=f,fill="white");d.text((20,46),"Original donor frame, two projection axes; no HRA registration",font=sm,fill="#bfcbd7")
    for j,k in enumerate(others):
        cx=275+550*j;sc=min(710/(hi[axis]-lo[axis]),500/max(hi[k]-lo[k],.001))
        for p,kind in pts:
            q=np.column_stack((cx+(p[:,k]-(hi[k]+lo[k])/2)*sc,815-(p[:,axis]-lo[axis])*sc))
            for x,y in q:d.point((x,y),fill=tuple(int(c*255) for c in cols[kind][:3]))
    im.save(out/"lower-limb.png")
    counts=Counter(r["category"] for r in rows)
    (out/"ATTRIBUTION.txt").write_text("Andreassen, T.E., Hume, D.R., Hamilton, L.D., Walker, K.E., Higinbotham, S.E., Shelburne, K.B. Visible Human Female (2022), University of Denver Center for Orthopaedic Biomechanics. Dataset DOI 10.56902/COB.vh.2022.1; paper DOI 10.1038/s41597-022-01905-2. CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ . Source https://digitalcommons.du.edu/visiblehuman/1/ (Final 3D STL Models). Changes: metric unit conversion, coordinate welding, named GLB transport and diagnostic projection only. No clinical or integrated anatomy claim.\n")
    report={"source_sha256":sha(src.read_bytes()),"source_url":"https://digitalcommons.du.edu/visiblehuman/1/","meshes":len(rows),"triangles":sum(r["triangles"] for r in rows),"category_counts":dict(counts),"scope":"Original donor-specific lower limb only; categories inferred from filenames, no cross-donor registration, no clinically validated model","inventory":rows}
    (out/"receipt.json").write_text(json.dumps(report,indent=2));print("R223_LOWER_LIMB",json.dumps({k:v for k,v in report.items() if k!="inventory"}))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
