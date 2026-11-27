"""Build static artifact viewers for the exact generated gallery inventory.
No arbitrary paths, remote user uploads, code execution, or third-party runtime requests.
"""
import base64, hashlib, html, io, json, re, tarfile, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/"site"
PROFILES=("pavilion-day","pavilion-night","pavilion-plan","pavilion-tall","bearing-assembled","bearing-exploded")
SOURCES=("pavilion.py","specs.json","export_gallery.py","bearing.py")
PACKAGES=(
    ("@google/model-viewer","4.4.0",{"dist/model-viewer.min.js":"model-viewer.min.js"}),
    ("@highlightjs/cdn-assets","11.12.0",{"highlight.min.js":"highlight.min.js","styles/github.min.css":"highlight.css","styles/github-dark.min.css":"highlight-dark.css"}),
)
CSP="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' data: blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'none'"
CSS="""html{color-scheme:light dark;font-family:system-ui,sans-serif;line-height:1.5}body{margin:0;background:Canvas;color:CanvasText}main{max-width:80rem;margin:auto;padding:clamp(1rem,4vw,2rem)}a{color:LinkText;text-underline-offset:.2em}a:focus-visible{outline:2px solid currentColor}h1{font-size:clamp(1.6rem,5vw,2.8rem);line-height:1.15}h2{font-size:1.3rem}.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,25rem),1fr));gap:1.5rem}figure{margin:0}img{max-width:100%;height:auto;border-radius:.5rem}model-viewer{width:100%;height:clamp(280px,60vw,530px);background:#283039;border-radius:.5rem}model-viewer:not(:defined){display:none}pre{overflow:auto;max-height:65vh;white-space:pre;tab-size:4;border:1px solid #8886;border-radius:.5rem;padding:1rem;font-size:.9rem}details{margin:.25rem 0 .25rem .8rem}summary{cursor:pointer;overflow-wrap:anywhere}dd{margin-left:1rem;overflow-wrap:anywhere}.files{display:flex;flex-wrap:wrap;gap:.75rem 1.3rem}.notice{border:1px solid #8888;padding:1rem;border-radius:.5rem}.json-value{white-space:pre-wrap;overflow-wrap:anywhere;font-family:monospace}.muted{font-size:.9rem}button{min-height:44px;font:inherit;padding:.5rem .9rem}"""
SCRIPT="""'use strict';
document.addEventListener('DOMContentLoaded',()=>{
  if(window.hljs){document.querySelectorAll('pre code').forEach(e=>hljs.highlightElement(e));}
  const viewer=document.querySelector('model-viewer'),status=document.getElementById('viewer-status');
  if(!viewer)return;
  viewer.addEventListener('load',()=>{status.textContent='3D model loaded. Drag to orbit; pinch or scroll to zoom.';status.dataset.state='loaded';});
  viewer.addEventListener('error',()=>{status.textContent='3D is unavailable on this device. The rendered image and original downloads remain available.';status.dataset.state='error';});
  document.getElementById('reset-view').addEventListener('click',()=>{if(typeof viewer.jumpCameraToGoal==='function'){viewer.cameraOrbit='auto auto auto';viewer.cameraTarget='auto auto auto';viewer.fieldOfView='auto';viewer.jumpCameraToGoal();}});
  if(viewer.loaded){status.textContent='3D model loaded.';status.dataset.state='loaded';}
});"""
def fetch(url,limit):
    if not url.startswith("https://registry.npmjs.org/"):raise ValueError("unexpected registry")
    with urllib.request.urlopen(url,timeout=45) as r:
        if r.status!=200 or not r.geturl().startswith("https://registry.npmjs.org/"):raise ValueError("registry response")
        b=r.read(limit+1)
    if len(b)>limit:raise ValueError("dependency budget")
    return b
def vendor(out):
    records=[]
    locked=ROOT/"gallery/viewer-dependencies.json"
    pins=json.loads(locked.read_text()) if locked.exists() else None
    for name,version,files in PACKAGES:
        meta=json.loads(fetch("https://registry.npmjs.org/"+urllib.parse.quote(name,safe="@")+"/"+version,2<<20))
        assert meta["name"]==name and meta["version"]==version
        dist=meta["dist"];raw=fetch(dist["tarball"],32<<20)
        integrity="sha512-"+base64.b64encode(hashlib.sha512(raw).digest()).decode()
        if integrity!=dist["integrity"]:raise ValueError("registry integrity mismatch")
        sha=hashlib.sha256(raw).hexdigest()
        record={"name":name,"version":version,"sha256":sha,"integrity":integrity,"license":meta.get("license"),"files":{}}
        with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as tar:
            names={m.name:m for m in tar.getmembers() if m.isfile()}
            for src,dest in files.items():
                m=names["package/"+src]
                if m.size>8<<20:raise ValueError("file budget")
                data=tar.extractfile(m).read()
                (out/dest).write_bytes(data);record["files"][dest]=hashlib.sha256(data).hexdigest()
            legal=[k for k in names if re.fullmatch(r"package/(?:LICENSE(?:\.[A-Za-z]+)?|NOTICE(?:\.[A-Za-z]+)?)",k,re.I)]
            if not legal:raise ValueError("missing license")
            for i,k in enumerate(sorted(legal)):
                dest=("model-viewer" if name.startswith("@google") else "highlight")+"-license-"+str(i)+".txt"
                data=tar.extractfile(names[k]).read();(out/dest).write_bytes(data);record["files"][dest]=hashlib.sha256(data).hexdigest()
        records.append(record)
    if pins is not None and records!=pins:raise ValueError("viewer dependency lock mismatch")
    (out/"dependencies.json").write_text(json.dumps(records,indent=2)+"\n")
    print("VIEWER_DEPENDENCY_LOCK",json.dumps(records))
def esc(x):return html.escape(str(x),quote=True)
def tree(x,label="Document",depth=0):
    if depth>32:raise ValueError("JSON depth")
    if isinstance(x,(dict,list)):
        items=x.items() if isinstance(x,dict) else enumerate(x)
        return '<details'+(' open' if depth<2 else '')+'><summary>'+esc(label)+' ('+str(len(x))+')</summary>'+''.join(tree(v,k,depth+1) for k,v in items)+'</details>'
    return '<div class="json-value">'+esc(label)+': '+esc(json.dumps(x,ensure_ascii=False))+'</div>'
def shell(title,body,model=False):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'+esc(CSP)+'"><title>'+esc(title)+' — Oneirifact</title><link rel="stylesheet" href="viewer.css"><link rel="stylesheet" href="highlight.css" media="(prefers-color-scheme: light)"><link rel="stylesheet" href="highlight-dark.css" media="(prefers-color-scheme: dark)"><script defer src="highlight.min.js"></script><script defer src="inspect.js"></script>'+('<script type="module" src="model-viewer.min.js"></script>' if model else '')+'</head><body><main><nav><a href="../index.html">Gallery</a> · <a href="index.html">All files</a></nav><h1>'+esc(title)+'</h1>'+body+'<footer><p class="muted">Local browser previews. <a href="dependencies.json.html">Viewer dependencies and licenses</a>.</p></footer></main></body></html>'
def write(out,name,title,body,model=False):
    (out/name).write_text(shell(title,body,model),encoding="utf-8")
def download(name,label=None):
    return '<a href="../gallery/'+esc(name)+'" download>'+esc(label or name)+'</a>'
def rawcode(text,lang):
    return '<pre><code class="language-'+lang+'">'+esc(text)+'</code></pre>'
def main():
    out=SITE/"inspect";out.mkdir(exist_ok=False)
    vendor(out)
    (out/"viewer.css").write_text(CSS);(out/"inspect.js").write_text(SCRIPT)
    gallery=SITE/"gallery";expected={f"{p}{ext}" for p in PROFILES for ext in (".png",".blend",".glb",".json")}|set(SOURCES)
    if {p.name for p in gallery.iterdir()}!=expected:raise ValueError("gallery inventory")
    for p in PROFILES:
        receipt=(gallery/(p+".json")).read_text()
        # Only local, self-contained, uncompressed GLB. Avoid decoder/CDN dependencies.
        import struct
        raw=(gallery/(p+".glb")).read_bytes()
        if raw[:4]!=b"glTF" or len(raw)<20:raise ValueError("GLB header")
        n,kind=struct.unpack_from("<I4s",raw,12)
        if kind!=b"JSON":raise ValueError("GLB JSON")
        doc=json.loads(raw[20:20+n])
        if doc.get("extensionsRequired") or any("uri" in i for k in ("images","buffers") for i in doc.get(k,[])):raise ValueError("external or required extension")
        body='<p class="notice">Standalone renderer qualification study, not a native Oneirifact artifact. The GLB shows exported geometry and materials; it is not a full Blender scene viewer. The original .blend remains downloadable.</p><div class="cols"><section><h2>Interactive 3D</h2><p id="viewer-status" role="status" data-state="pending">Loading 3D viewer. The rendered image is always available.</p><model-viewer src="../gallery/'+p+'.glb" alt="'+esc(p)+' interactive 3D geometry" poster="../gallery/'+p+'.png" camera-controls touch-action="pan-y" loading="eager"></model-viewer><button id="reset-view" type="button">Reset view</button></section><section><h2>Rendered image</h2><figure><a href="../gallery/'+p+'.png"><img src="../gallery/'+p+'.png" alt="'+esc(p)+' rendered image" width="720" height="480"></a><figcaption>Tap image for full resolution.</figcaption></figure></section></div><h2>Original files</h2><div class="files">'+''.join(download(p+e) for e in (".png",".glb",".blend",".json"))+'</div><h2>Render receipt</h2>'+tree(json.loads(receipt))+'<details><summary>Raw JSON</summary>'+rawcode(receipt,"json")+'</details>'
        write(out,p+".html",p.replace("-"," ").title(),body,True)
    for name in SOURCES:
        raw=(gallery/name).read_text();isjson=name.endswith(".json")
        body='<p>'+download(name,"Download original")+'</p>'+((tree(json.loads(raw))+'<details open><summary>Raw JSON</summary>'+rawcode(raw,"json")+'</details>') if isjson else rawcode(raw,"python"))
        write(out,name+".html",name,body)
    dep=(out/"dependencies.json").read_text()
    legal=''.join('<li><a href="'+esc(p.name)+'">'+esc(p.name)+'</a></li>' for p in sorted(out.glob("*-license-*.txt")))
    write(out,"dependencies.json.html","Viewer dependencies",tree(json.loads(dep))+'<ul>'+legal+'</ul>')
    body='<p>Inspect files directly on this device. No external viewer or account required. Source code is displayed, never executed.</p><h2>3D models, renders and receipts</h2><ul>'+''.join('<li><a href="'+p+'.html">'+p.replace("-"," ").title()+'</a></li>' for p in PROFILES)+'</ul><h2>Source files</h2><ul>'+''.join('<li><a href="'+n+'.html">'+n+'</a></li>' for n in SOURCES)+'</ul>'
    write(out,"index.html","Artifact inspector",body)
if __name__=="__main__":
    import urllib.parse
    main()
