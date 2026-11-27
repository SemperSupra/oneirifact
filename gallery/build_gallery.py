"""Build public gallery from pinned, original standalone procedural inputs."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
PROFILES=("pavilion-day","pavilion-night","pavilion-plan","pavilion-tall")
def require(ok,message):
    if not ok: raise RuntimeError(message)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_glb(path,names):
    raw=path.read_bytes()
    require(len(raw)<=64<<20 and len(raw)>20,"GLB budget")
    magic,version,length=struct.unpack_from("<4sII",raw)
    require((magic,version,length)==(b"glTF",2,len(raw)),"GLB header")
    size,kind=struct.unpack_from("<I4s",raw,12)
    require(kind==b"JSON" and 20+size<=len(raw),"GLB JSON")
    doc=json.loads(raw[20:20+size])
    actual={n.get("name") for n in doc.get("nodes",[]) if "mesh" in n}
    require(set(names)==actual,"GLB mesh identity mismatch")
    require(not any("uri" in b for b in doc.get("buffers",[])),"external GLB buffer")
def main():
    blender=Path(sys.argv[1]).resolve(strict=True)
    out=ROOT.parent/"site/gallery"
    require(not out.exists(),"gallery target already exists")
    with tempfile.TemporaryDirectory(prefix="public-gallery-") as tmp:
        temp=Path(tmp)
        for p in PROFILES:
            subprocess.run([str(blender),"--background","--factory-startup","--disable-autoexec","-t","2","--python-exit-code","1","--python",str(ROOT/"export_gallery.py"),"--",p,str(temp)],check=True,timeout=150)
            receipt=json.loads((temp/(p+".json")).read_text())
            require(receipt["engine"]=="CYCLES" and receipt["device"]=="CPU" and receipt["object_count"]==136 and receipt["resolution"]==[720,480],"native receipt")
            require(receipt["generator_sha256"]=="sha256:"+sha(ROOT/"pavilion.py") and receipt["spec_sha256"]=="sha256:"+sha(ROOT/"specs.json"),"source identity")
            require(receipt["image_sha256"]=="sha256:"+sha(temp/(p+".png")),"PNG digest")
            require(receipt["gallery"]["blend_sha256"]==sha(temp/(p+".blend")) and receipt["gallery"]["glb_sha256"]==sha(temp/(p+".glb")),"model digest")
            verify_glb(temp/(p+".glb"),receipt["gallery"]["glb_mesh_names"])
            expr="import bpy; assert bpy.context.scene.render.engine == 'CYCLES'; assert set("+repr(receipt["object_ids"])+").issubset(bpy.data.objects.keys()); print('BLEND_REOPEN_PASS')"
            subprocess.run([str(blender),"--background","--disable-autoexec",str(temp/(p+".blend")),"--python-exit-code","1","--python-expr",expr],check=True,timeout=60)
        out.mkdir()
        for p in PROFILES:
            for suffix in (".png",".blend",".glb",".json"):
                shutil.copyfile(temp/(p+suffix),out/(p+suffix))
        for name in ("pavilion.py","specs.json","export_gallery.py"):
            shutil.copyfile(ROOT/name,out/name)
    print("Public gallery: 4 actual renders, 4 reopened Blender scenes, 4 GLB mesh identity checks PASS")
if __name__=="__main__":
    main()
