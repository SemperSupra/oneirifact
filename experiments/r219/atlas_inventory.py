"""Catalog actual official BodyParts3D 4.0 element meshes against FMA mapping.
Preserve original archive and mappings. Counts are catalog coverage, not anatomical completeness.
"""
import sys,json,hashlib,zipfile,re,csv,io
from pathlib import Path
from collections import defaultdict
import numpy as np
from PIL import Image,ImageDraw,ImageFont
PATTERNS={"bones":r"(^| )(bone|femur|tibia|fibula|humerus|radius|ulna|rib|vertebra|sternum|scapula|clavicle|patella|phalanx|metacarpal|metatarsal)( |$)","muscles":r"muscle|musculus","tendons":r"tendon|aponeurosis","ligaments":r"ligament","cartilage":r"cartilage|meniscus|intervertebral disc","skin":r"(^| )skin( |$)|dermis|epidermis","arteries":r"artery|arterial|aorta","veins":r"vein|venous|vena cava","nerves":r"nerve|spinal cord|plexus","lymphatics":r"lymphatic|lymph node","digestive":r"stomach|esophagus|intestine|colon|rectum|liver|pancreas|gallbladder","respiratory":r"lung|trachea|bronchus|larynx|diaphragm","urinary":r"kidney|ureter|urethra|urinary bladder","reproductive_male":r"testis|testicle|epididymis|ductus deferens|vas deferens|seminal vesicle|prostate|penis|scrotum","reproductive_female":r"uterus|ovary|ovarian|fallopian|uterine tube|vagina|vulva|clitoris|labium|labia","sensory_oral":r"eye|cornea|retina|cochlea|tongue|tooth|teeth|gingiva","endocrine":r"thyroid|pituitary|adrenal|parathyroid|pineal","fascia":r"fascia"}
def sha(b):return hashlib.sha256(b).hexdigest()
def readtext(p):
    return p.read_text(encoding="utf-8-sig")
def run(inp,out):
    out.mkdir(parents=True,exist_ok=False);z=zipfile.ZipFile(inp/"geometry.zip")
    index={}
    for i in z.infolist():
        name=Path(i.filename).stem.upper()
        if i.filename.lower().endswith(".obj"):
            assert name not in index,"duplicate element"
            assert i.file_size<64*1024*1024
            index[name]=i
    assert len(index)>1000
    cat=defaultdict(set);concepts=defaultdict(set);coverage={}
    for row in csv.reader(io.StringIO(readtext(inp/"isa_element_parts.txt")),delimiter="\t"):
        if len(row)!=3 or not row[0].startswith("FMA"):continue
        fma,name,element=row
        if element.upper() not in index:continue
        for family,p in PATTERNS.items():
            if re.search(p,name,re.I):
                cat[family].add(element.upper());concepts[family].add(fma)
        coverage[element.upper()].add((fma,name)) if element.upper() in coverage else coverage.setdefault(element.upper(),{(fma,name)})
    inventory=[]
    for element,i in sorted(index.items()):
        raw=z.read(i)
        v=0;f=0
        for l in raw.splitlines():
            if l.startswith(b"v "):v+=1
            elif l.startswith(b"f "):f+=1
        assert v>0 and f>0,"empty element "+element
        inventory.append({"id":element,"bytes":len(raw),"sha256":sha(raw),"vertices":v,"faces":f,"mapped_concepts":sorted(coverage.get(element,set()))})
    report={"source":"Official DBCLS BodyParts3D 4.0 IS-A 99%-reduced OBJ archive","archive_sha256":sha((inp/"geometry.zip").read_bytes()),"mesh_elements":len(inventory),"named_family_coverage":{k:{"unique_mesh_elements":len(cat[k]),"matching_fma_concepts":len(concepts[k]),"element_ids":sorted(cat[k])} for k in PATTERNS},"scope":"Regex catalog screen with overlapping families, not clinical completeness or independent registration. Female anatomical availability not established by name counts. Original source coordinates retained."}
    (out/"inventory.json").write_text(json.dumps(inventory,indent=2));(out/"receipt.json").write_text(json.dumps(report,indent=2))
    import shutil
    for p in inp.iterdir():shutil.copyfile(p,out/p.name)
    im=Image.new("RGB",(1100,820),"#17212b");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",21);small=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",17)
    d.text((20,15),"BodyParts3D | actual acquired element inventory",font=font,fill="white");d.text((20,47),"Overlapping name-based categories; not a completeness certificate",font=small,fill="#b7c9d7")
    for i,(name,row) in enumerate(report["named_family_coverage"].items()):
        y=85+i*39;n=row["unique_mesh_elements"];d.text((20,y),name.replace("_"," "),font=small,fill="white");d.rectangle((280,y,280+min(n,1200)*.56,y+22),fill="#77c6ac");d.text((980,y),str(n),font=small,fill="white")
    im.save(out/"coverage.png")
    print("R219_ATLAS",json.dumps({k:v for k,v in report.items() if k!="named_family_coverage"}),json.dumps({k:v["unique_mesh_elements"] for k,v in report["named_family_coverage"].items()}))
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
