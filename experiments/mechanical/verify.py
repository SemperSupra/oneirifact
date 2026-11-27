"""Independent bounded artifact checks for the conceptual bearing workcell."""
import hashlib,json,struct,sys
from pathlib import Path
import subprocess
import zlib

def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def main():
    root=Path(sys.argv[1]);blender=sys.argv[2]
    source=Path(__file__).with_name("bearing.py")
    prior=None
    for profile in ("assembled","exploded"):
        receipt=json.loads((root/(profile+".json")).read_text())
        require(receipt["source_sha256"]==hashlib.sha256(source.read_bytes()).hexdigest(),"source hash")
        require(receipt["engine"]=="CYCLES" and receipt["device"]=="CPU" and receipt["profile"]==profile,"engine/profile")
        ids=receipt["component_ids"];require(len(ids)==14 and len(set(ids))==14,"component count")
        if prior is not None:require(prior==ids,"stable component identity")
        prior=ids
        for suffix,digest in receipt["files"].items():
            path=root/(profile+suffix)
            require(path.is_file() and not path.is_symlink() and 0<path.stat().st_size<32<<20,"artifact custody")
            require(hashlib.sha256(path.read_bytes()).hexdigest()==digest,"artifact digest")
        png=(root/(profile+".png")).read_bytes()
        require(png[:8]==b"\x89PNG\r\n\x1a\n" and struct.unpack(">II",png[16:24])==(720,480),"PNG dimensions")
        i=8;payload=bytearray();end=False
        while i<len(png):
            n,k=struct.unpack_from(">I4s",png,i);part=png[i+8:i+8+n]
            require(i+12+n<=len(png) and zlib.crc32(k+part)==struct.unpack_from(">I",png,i+8+n)[0],"PNG CRC")
            if k==b"IDAT":payload.extend(part)
            i+=12+n
            if k==b"IEND":end=True;break
        require(end and i==len(png) and len(set(zlib.decompress(payload)))>32,"nontrivial raster")
        glb=(root/(profile+".glb")).read_bytes()
        require(struct.unpack_from("<4sII",glb)==(b"glTF",2,len(glb)),"GLB header")
        n,k=struct.unpack_from("<I4s",glb,12)
        require(k==b"JSON" and 20+n<=len(glb),"GLB JSON")
        doc=json.loads(glb[20:20+n]);require({n.get("name") for n in doc["nodes"] if "mesh" in n}==set(ids),"GLB names")
        expr="import bpy; assert set("+repr(ids)+").issubset(bpy.data.objects.keys()); print('NATIVE_REOPEN_PASS')"
        subprocess.run([blender,"--background","--disable-autoexec",str(root/(profile+".blend")),"--python-exit-code","1","--python-expr",expr],check=True,timeout=60)
    require((root/"assembled.png").read_bytes()!=(root/"exploded.png").read_bytes(),"distinct image output")
    print("MECHANICAL_ARTIFACT_QUALIFICATION_PASS: two real PNG, BLEND and GLB sets; 14 stable components")
if __name__=="__main__":main()
