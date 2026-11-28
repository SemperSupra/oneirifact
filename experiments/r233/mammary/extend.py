"""Separate mammary reference inspection from an exact released atlas corpus."""
import hashlib,io,json,re,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"gallery"))
import anatomy_pack as p
from build_anatomy import compact
BASE="ffac8867db9951a3d721558e7aad8ae9250b00798d4bf65b8c53e3d811ec0947"
SOURCE="b809acdb9e7f3bc6e1935122a62726f2f760871460789bb5f196bedb710116ba"
def main(base,source,out,pack):
    original=p.restore(base,BASE,out)
    p.require(p.digest(source)==SOURCE,"source archive hash")
    with zipfile.ZipFile(source) as z:
        rec=p.parse(z.read("receipt.json"));r=rec["mammary_subset"]
        raw=z.read("female-mammary-reference.glb")
        p.require(p.sha(raw)==r["sha256"] and r["nodes"]==16 and r["triangles"]==856129 and r["transport_max_m"]==0,"source receipt")
        s=trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
        p.require(set(s.graph.nodes_geometry)=={x["id"] for x in r["source_ids"]},"source inventory")
        layers=[];inv=[];points=[];labels=[]
        def add(name,b):
            p.require(p.NAME.fullmatch(name) and not (out/name).exists(),"unsafe or existing asset")
            (out/name).write_bytes(b);return "data/"+name
        for row in sorted(r["source_ids"],key=lambda x:x["name"]):
            n=row["id"];tf,g=s.graph[n];m=s.geometry[g].copy();m.apply_transform(tf)
            p.require(len(m.faces)==row["triangles"],"triangle count")
            one=trimesh.Scene();one.add_geometry(m,node_name=n,geom_name=n);original_glb=one.export(file_type="glb")
            check=trimesh.load(io.BytesIO(original_glb),file_type="glb",force="scene",process=False)
            t,g=check.graph[n];q=check.geometry[g].copy();q.apply_transform(t)
            p.require(np.max(abs(q.vertices[q.faces]-m.vertices[m.faces]))<=2e-6,"source node transport")
            b,src,display,nodes=compact(original_glb,60000)
            key="mammary-"+row["name"].removeprefix("VH_F_").replace("_","-").lower()
            label=row["name"].removeprefix("VH_F_").replace("_"," ").replace(" L"," (left)").replace(" R"," (right)")
            layers.append({"id":key,"label":label,"file":add(key+".glb",b),"bytes":len(b),"sha256":p.sha(b),"source_triangles":src,"display_triangles":display,"nodes":nodes,"fidelity":"Reduced browser display geometry" if display!=src else "Original reference geometry"})
            inv.append({"id":n,"names":[label],"layer":key,"triangles":src})
            points.append(m.vertices[::max(1,len(m.vertices)//12000)]);labels.append(label)
        im=Image.new("RGB",(1100,830),"#17232f");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",18)
        d.text((15,12),"Female mammary reference: sixteen source structures",font=font,fill="white")
        d.text((15,39),"Isolated source meshes, independent panel scale; not whole-body registration",font=font,fill="#bccbd5")
        for i,v in enumerate(points):
            x=(i%4)*275;y=75+(i//4)*188;c=(v.max(0)+v.min(0))/2;sc= min(240/max(np.ptp(v[:,0]),.001),135/max(np.ptp(v[:,1]),.001))
            d.text((x+8,y),labels[i],font=font,fill="white")
            d.point([(x+138+(a[0]-c[0])*sc,y+100-(a[1]-c[1])*sc) for a in v],fill="#d0bb98")
        buf=io.BytesIO();im.save(buf,format="PNG")
        cat=p.parse((out/"catalog.json").read_bytes());p.require(len(cat["datasets"])==6,"base dataset")
        cat["datasets"].append({"id":"mammary","label":"Female mammary structures","source":"HRA female reference v1.10, exact R232 source subset","scope":"16 named bilateral structures. Individual reference components, no integrated breast shape or physiological deformation claim. Display derivatives may be reduced; source geometry preserved separately.","preview":add("mammary-preview.png",buf.getvalue()),"attribution":add("mammary-attribution.txt",z.read("ATTRIBUTION.txt")),"inventory":add("mammary-inventory.json",json.dumps(inv).encode()),"receipt":add("mammary-receipt.json",z.read("receipt.json")),"layers":layers,"source_archive_sha256":SOURCE})
        cat["source_pins"]["r232_mammary"]=SOURCE
        (out/"catalog.json").write_text(json.dumps(cat,sort_keys=True,indent=2)+"\n")
        entries=p.inventory(out);p.require(len(entries)==80 and all(entries[n]==v for n,v in original.items() if n!="catalog.json"),"base bytes changed")
        digest=p.pack(out,pack);p.require(p.verify(pack,digest)==entries,"pack verification")
        print("R233_MAMMARY_ISOLATION",json.dumps({"source_meshes":16,"source_triangles":sum(x["source_triangles"] for x in layers),"display_triangles":sum(x["display_triangles"] for x in layers),"assets":len(entries),"models":sum(len(x["layers"]) for x in cat["datasets"]),"datasets":len(cat["datasets"]),"bytes":sum(x["bytes"] for x in entries.values()),"sha256":digest}),flush=True)
if __name__=="__main__":main(*(Path(x) for x in sys.argv[1:]))
