"""Build original-versus-recovered LDraw comparison pages from exact R209 results.
Only converts existing mesh bytes to GLB; does not generate or qualify native geometry.
"""
import sys, json, zipfile, hashlib, struct, math, html, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"gallery"))
from build_inspector import vendor, tree, esc, rawcode, CSP
IDS=("3001","3002","3003","3004","3005","3020","3022")
def sha(b):return hashlib.sha256(b).hexdigest()
def checked(path,digest):
    raw=path.read_bytes()
    if sha(raw)!=digest:raise ValueError("source hash mismatch")
    return zipfile.ZipFile(path)
def mesh(raw):
    v=[];f=[]
    for l in raw.decode().splitlines():
        t=l.split()
        if t and t[0]=="v":
            q=[float(x) for x in t[1:]];assert len(q)==3 and all(math.isfinite(x) for x in q);v.append((q[0],q[2],-q[1]))
        elif t and t[0]=="f":
            q=[int(x)-1 for x in t[1:]];assert len(q)==3 and min(q)>=0 and max(q)<len(v);f.append(q)
    if not v or not f or len(v)>125000 or len(f)>250000:raise ValueError(f"mesh budget: {len(v)} vertices, {len(f)} triangles")
    return v,f
def glb(raw,color):
    v,f=mesh(raw);pos=[];norm=[]
    for tri in f:
        a,b,c=[v[i] for i in tri];u=[b[i]-a[i] for i in range(3)];w=[c[i]-a[i] for i in range(3)]
        n=(u[1]*w[2]-u[2]*w[1],u[2]*w[0]-u[0]*w[2],u[0]*w[1]-u[1]*w[0]);length=math.sqrt(sum(x*x for x in n))
        if length<1e-18:continue
        for p in (a,b,c):pos.extend(p);norm.extend(x/length for x in n)
    assert pos
    pb=struct.pack("<"+"f"*len(pos),*pos);nb=struct.pack("<"+"f"*len(norm),*norm);data=pb+nb
    lo=[min(pos[k::3]) for k in range(3)];hi=[max(pos[k::3]) for k in range(3)]
    doc={"asset":{"version":"2.0","generator":"Oneirifact R215 reference mesh transport; not native generation"},"scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0}],"meshes":[{"primitives":[{"attributes":{"POSITION":0,"NORMAL":1},"material":0}]}],"materials":[{"doubleSided":True,"pbrMetallicRoughness":{"baseColorFactor":color,"metallicFactor":0,"roughnessFactor":.75}}],"buffers":[{"byteLength":len(data)}],"bufferViews":[{"buffer":0,"byteOffset":0,"byteLength":len(pb),"target":34962},{"buffer":0,"byteOffset":len(pb),"byteLength":len(nb),"target":34962}],"accessors":[{"bufferView":0,"componentType":5126,"count":len(pos)//3,"type":"VEC3","min":lo,"max":hi},{"bufferView":1,"componentType":5126,"count":len(norm)//3,"type":"VEC3"}]}
    j=json.dumps(doc,separators=(",",":")).encode();j+=b" "*(-len(j)%4);data+=b"\0"*(-len(data)%4)
    binary=struct.pack("<4sII",b"glTF",2,12+8+len(j)+8+len(data))+struct.pack("<I4s",len(j),b"JSON")+j+struct.pack("<I4s",len(data),b"BIN\0")+data
    return binary,lo,hi,len(pos)//9
CSS="""html{color-scheme:light dark;font:16px system-ui,sans-serif}body{background:Canvas;color:CanvasText;margin:0}main{max-width:80rem;margin:auto;padding:clamp(12px,3vw,30px)}a{color:LinkText}h1{font-size:clamp(1.35rem,4vw,2rem)}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}model-viewer{width:100%;height:clamp(200px,40vw,460px);background:#27313a;border-radius:6px}h2{font-size:1rem}button{font:inherit;min-height:44px;margin:4px;padding:6px 10px}pre{overflow:auto;max-height:60vh;border:1px solid #8888;padding:10px}details{margin:.4rem 0;overflow-wrap:anywhere}summary{cursor:pointer}.notice{border:1px solid #8888;padding:10px;border-radius:8px}.json-value{font: .9rem monospace;overflow-wrap:anywhere}.links{display:flex;flex-wrap:wrap;gap:10px}model-viewer:not(:defined){visibility:hidden}@media(max-width:420px){.grid{gap:6px}h2{font-size:.85rem}}"""
JS="""'use strict';
const a=document.getElementById('reference'),b=document.getElementById('candidate');
if(a&&b){
 const status=document.getElementById('state');
 function ready(){if(a.loaded&&b.loaded){status.textContent='Both actual models loaded';status.dataset.state='loaded';}}
 for(const m of [a,b]){m.addEventListener('load',ready);m.addEventListener('error',()=>{status.textContent='A model could not load. Original downloads remain available.';status.dataset.state='error';});}
 function sync(src,dst){const o=src.getCameraOrbit(),t=src.getCameraTarget();dst.cameraOrbit=o.theta+'rad '+o.phi+'rad '+o.radius+'m';dst.cameraTarget=t.x+'m '+t.y+'m '+t.z+'m';dst.fieldOfView=src.getFieldOfView()+'deg';dst.jumpCameraToGoal();}
 a.addEventListener('camera-change',e=>{if(e.detail.source==='user-interaction'&&b.loaded)sync(a,b);});
 b.addEventListener('camera-change',e=>{if(e.detail.source==='user-interaction'&&a.loaded)sync(b,a);});
 function view(theta,phi){for(const m of [a,b]){m.cameraOrbit=theta+'deg '+phi+'deg '+m.dataset.radius+'m';m.cameraTarget=m.dataset.target;m.fieldOfView='35deg';m.jumpCameraToGoal();}}
 document.getElementById('top').addEventListener('click',()=>view(0,1));
 document.getElementById('bottom').addEventListener('click',()=>view(0,179));
 document.getElementById('reset').addEventListener('click',()=>view(45,65));
 ready();
}"""
def page(title,body,model=False):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'+esc(CSP)+'"><title>'+esc(title)+'</title><link rel="stylesheet" href="comparison.css">'+('<script type="module" src="model-viewer.min.js"></script><script defer src="comparison.js"></script>' if model else '')+'</head><body><main><nav><a href="index.html">All parts</a></nav><h1>'+esc(title)+'</h1>'+body+'</main></body></html>'
def run(inputs,out):
    out.mkdir(parents=True);vendor(out)
    (out/"comparison.css").write_text(CSS);(out/"comparison.js").write_text(JS)
    results=[]
    with checked(inputs/"geometry.zip","64bb52981b46a402210c200e97437edff93597733e9886332a5544dd27130bea") as z, checked(inputs/"basic.zip","3c69e2c331af0b4035f511f0cbb3ce69d41482d0477b9c3cc8f3e2d754eab60d") as basic, checked(inputs/"special.zip","9fa2b51c1b0a8a5e1dcbe9deb024e6e39a0bed7c111e4bc1b9abb595d0398fd8") as special:
        rows={x["id"]:x for x in json.loads(z.read("receipt.json"))["results"]}
        for id in IDS:
            d=out/id;d.mkdir();source=special if id=="3002" else basic
            attribution=json.loads(source.read(id+"/ATTRIBUTION.json"))
            for name,rec in attribution["files"].items():
                raw=source.read(id+"/source/"+name);assert sha(raw)==rec["sha256"];p=d/"source"/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            for name in source.namelist():
                if name.startswith(id+"/source/") and not name.endswith(".dat"):
                    p=d/name[len(id)+1:];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(source.read(name))
            (d/"attribution.json").write_bytes(source.read(id+"/ATTRIBUTION.json"))
            rawgraph=z.read(id+"/graph.json");(d/"graph.json").write_bytes(rawgraph)
            modelinfo=[]
            for label,color in [("reference",[.74,.36,.18,1]),("candidate",[.18,.66,.42,1])]:
                raw=z.read(id+"/"+label+".obj")
                if label=="reference":assert raw==source.read(id+"/part.obj") or mesh(raw)==mesh(source.read(id+"/part.obj"))
                (d/(label+".obj")).write_bytes(raw)
                g,lo,hi,n=glb(raw,color);(d/(label+".glb")).write_bytes(g);modelinfo.append({"kind":label,"triangles":n,"lo":lo,"hi":hi,"sha256":sha(g)})
            lo=[min(x["lo"][k] for x in modelinfo) for k in range(3)];hi=[max(x["hi"][k] for x in modelinfo) for k in range(3)]
            center=[(a+b)/2 for a,b in zip(lo,hi)];radius=3.3*max(b-a for a,b in zip(lo,hi));target=" ".join(str(x)+"m" for x in center)
            row=rows[id];(d/"receipt.json").write_text(json.dumps({"prior":row,"transport":modelinfo,"scope":"original R209 candidate meshes only; no native generation"},indent=2))
            def model(label,title):
                return '<section><h2>'+title+'</h2><model-viewer id="'+label+'" src="'+id+'/'+label+'.glb" camera-controls touch-action="pan-y" camera-orbit="45deg 65deg '+str(radius)+'m" camera-target="'+target+'" field-of-view="35deg" data-target="'+target+'" data-radius="'+str(radius)+'" alt="'+title+'"></model-viewer></section>'
            m=row["comparison"];body='<p class="notice">Original LDraw reference versus R209 procedural candidate. Native-shaped source, NOT generated or validated by the native Oneirifact engine. Nominal geometry only; not manufacturer fit.</p><p id="state" role="status" data-state="pending">Loading both models…</p><div class="grid">'+model("reference","Original LDraw")+model("candidate","Recovered candidate")+'</div><div><button id="reset">Reset</button><button id="top">Top</button><button id="bottom">Underside</button></div><p>Sampled surface RMSE '+format(m["sampled_symmetric_rmse_mm"],".3f")+' mm · coverage within 0.3 mm '+format(m["coverage_within_0p3mm"],".1%")+'</p><p class="links">'+''.join('<a href="'+id+'/'+x+'" download>'+x+'</a>' for x in ("reference.glb","candidate.glb","reference.obj","candidate.obj","graph.json","receipt.json","attribution.json"))+'</p><h2>Candidate Oneirifact feature graph</h2>'+tree(json.loads(rawgraph))+'<details><summary>Raw JSON</summary>'+rawcode(rawgraph.decode(),"json")+'</details><h2>LDraw attribution</h2>'+tree(attribution)
            (out/(id+".html")).write_text(page("LDraw part "+id,body,True));results.append({"id":id,"models":modelinfo,"graph_sha256":sha(rawgraph)})
    links="".join('<li><a href="'+x["id"]+'.html">Part '+x["id"]+'</a></li>' for x in results)
    (out/"index.html").write_text(page("LDraw reconstruction comparison","<p>Seven actual source/candidate pairs. Original library CC BY 4.0; per-part attribution and exact source closure included. Browser preview is not native engine qualification.</p><ul>"+links+"</ul><p>Viewer license: <a href='model-viewer-license-0.txt'>Apache 2.0</a>; dependency receipt <a href='dependencies.json'>JSON</a>.</p>"))
    (out/"comparison-receipt.json").write_text(json.dumps(results,indent=2));print("R215_COMPARISON_BUILD",len(results))
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
