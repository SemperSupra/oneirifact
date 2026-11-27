"""Generate a local-only layered anatomy viewer from the qualified atlas artifact.
No anatomical geometry generated, no changes to source, no public deployment.
"""
import sys,hashlib,json,zipfile,io,urllib.parse
from pathlib import Path
import trimesh
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"gallery"))
from build_inspector import vendor,tree,esc,CSP
PINS={"male":"980678a8639ef26849a9c0ace5dfece3807dd535ff68664058092b52e863c01a","female":"8125975af5baea4c9b98f2eebd95221448189244325dfbdd0909c64caa83106c"}
def sha(b):return hashlib.sha256(b).hexdigest()
CSS="""html{color-scheme:light dark;font:16px system-ui,sans-serif}body{margin:0;background:Canvas;color:CanvasText}main{max-width:84rem;margin:auto;padding:clamp(12px,3vw,26px)}h1{font-size:clamp(1.5rem,4vw,2.2rem);margin:.2rem 0}p{line-height:1.5}.layout{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:20px}model-viewer{width:100%;height:clamp(350px,64vh,700px);background:#25333f;border-radius:8px}model-viewer:not(:defined){visibility:hidden}label{display:block;font-weight:600}select,button{font:inherit;min-height:44px;padding:8px;margin:4px 0}select{width:100%}.controls{display:flex;flex-wrap:wrap;gap:8px}.notice{padding:12px;border:1px solid #8888;border-radius:8px}details{margin:.4rem 0;overflow-wrap:anywhere}.json-value{font:.9rem monospace;overflow-wrap:anywhere}a{color:LinkText}.facts{display:flex;gap:12px;flex-wrap:wrap}img{max-width:100%;height:auto}@media(max-width:680px){.layout{grid-template-columns:minmax(0,1fr)}model-viewer{height:clamp(340px,54vh,520px)}}"""
JS="""'use strict';
const m=document.getElementById('viewer'),sel=document.getElementById('layer'),status=document.getElementById('status'),download=document.getElementById('download'),heading=document.getElementById('selected');
const map=JSON.parse(document.getElementById('models').textContent);
let active=sel.value;
function update(){
 active=sel.value;
 const row=map[active];
 status.textContent='Loading '+row.label+'…';status.dataset.state='pending';
 heading.textContent=row.label;
 download.href=row.file;
 m.src=row.file;
}
function ready(){if(m.loaded&&m.src===map[active].file){status.textContent=map[active].label+' loaded';status.dataset.state='loaded';status.dataset.layer=active;}}
m.addEventListener('load',ready);
m.addEventListener('error',()=>{status.textContent='Unable to load this model. Original downloads and preview remain available.';status.dataset.state='error';});
sel.addEventListener('change',update);
function view(theta){m.cameraOrbit=theta+'deg 80deg auto';m.cameraTarget='auto auto auto';m.jumpCameraToGoal();}
document.getElementById('front').addEventListener('click',()=>view(0));
document.getElementById('side').addEventListener('click',()=>view(90));
document.getElementById('reset').addEventListener('click',()=>{m.cameraOrbit='auto auto auto';m.cameraTarget='auto auto auto';m.fieldOfView='auto';m.jumpCameraToGoal();});
if(m.loaded)ready();
"""
def run(inp,out,sex):
    assert sha(inp.read_bytes())==PINS[sex]
    out.mkdir(parents=True,exist_ok=False);vendor(out)
    (out/"viewer.css").write_text(CSS);(out/"viewer.js").write_text(JS)
    with zipfile.ZipFile(inp) as z:
        receipt=json.loads(z.read("receipt.json"));assert receipt["sex"]==sex
        models={}
        for k,label,file in (("combined","Translucent body and organs","body-with-organs.glb"),("organs","Internal organs only","internal-organs.glb"),("skin","External skin reference","skin-reference.glb")):
            data=z.read(file);assert data[:4]==b"glTF";(out/file).write_bytes(data);models[k]={"label":label,"file":file,"sha256":sha(data)}
        orig=trimesh.load(io.BytesIO(z.read("internal-organs.glb")),file_type="glb",force="scene",process=False)
        expected={o["organ"] for o in receipt["organs"]}
        assert set(orig.graph.nodes_geometry)==expected
        d=out/"organs";d.mkdir()
        for name in sorted(expected):
            matrix,geom=orig.graph[name];m=orig.geometry[geom].copy();q=trimesh.Scene();q.add_geometry(m,node_name=name,geom_name=name,transform=matrix)
            data=q.export(file_type="glb");path="organs/"+name+".glb";(out/path).write_bytes(data)
            check=trimesh.load(io.BytesIO(data),file_type="glb",force="scene",process=False)
            assert len(check.graph.nodes_geometry)==1
            mat2,g2=check.graph[next(iter(check.graph.nodes_geometry))]
            assert len(check.geometry[g2].faces)==len(m.faces)
            models[name]={"label":name.replace("_"," ").title(),"file":path,"sha256":sha(data)}
        for name in ("receipt.json","ATTRIBUTION.txt","HRA-LICENSE.txt","anatomy-preview.png"):(out/name).write_bytes(z.read(name))
    # JSON data is static generated from allowlisted names and paths; no executable markup.
    data=esc(json.dumps(models,separators=(",",":")))
    # script type application/json does not decode HTML entities: write only safe JSON.
    j=json.dumps(models,separators=(",",":")).replace("<","\\u003c")
    opts="".join('<option value="'+esc(k)+'"'+(' selected' if k=="combined" else '')+'>'+esc(v["label"])+'</option>' for k,v in models.items())
    page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'+esc(CSP)+'"><title>'+sex.title()+' anatomy inspector</title><link rel="stylesheet" href="viewer.css"><script type="module" src="model-viewer.min.js"></script><script defer src="viewer.js"></script></head><body><main><h1>'+sex.title()+' anatomy inspector</h1><p class="notice">Actual Human Reference Atlas educational geometry, original shared donor frame. Not registered to the separate MakeHuman bodies; not a medical simulator or native Oneirifact output.</p><div class="layout"><section><model-viewer id="viewer" src="body-with-organs.glb" camera-controls touch-action="pan-y" alt="Educational adult anatomy reference" poster="anatomy-preview.png" loading="eager"></model-viewer><p id="status" role="status" data-state="pending">Loading…</p></section><section><label for="layer">Anatomical layer or organ</label><select id="layer">'+opts+'</select><h2 id="selected">Translucent body and organs</h2><div class="controls"><button id="front">Front</button><button id="side">Side</button><button id="reset">Reset</button></div><p><a id="download" href="body-with-organs.glb" download>Download selected GLB</a></p><p><a href="anatomy-preview.png">Full-size reference image</a> · <a href="ATTRIBUTION.txt">Attribution</a> · <a href="HRA-LICENSE.txt">CC BY 4.0</a></p><details><summary>Model receipt</summary>'+tree(receipt)+'</details></section></div><script id="models" type="application/json">'+j+'</script></main></body></html>'
    (out/"index.html").write_text(page)
    (out/"viewer-receipt.json").write_text(json.dumps({"sex":sex,"source_sha256":PINS[sex],"models":models,"scope":"Reference transport and isolate; no anatomical registration"},indent=2))
    print("R218_VIEWER_BUILD",sex,len(models))
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
