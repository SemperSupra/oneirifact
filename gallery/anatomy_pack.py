"""Deterministic bounded archive for admitted browser display assets, not raw donor custody.
The pack can be independently restored using its exact SHA-256. No implicit release.
"""
import argparse,hashlib,json,re,stat,zipfile
from pathlib import Path
MAX_TOTAL=78<<20
MAX_FILE=64<<20
MAX_FILES=80
NAME=re.compile(r"[a-z0-9-]+\.(glb|png|svg|json|txt)")
HEX=re.compile(r"[0-9a-f]{64}")
MANIFEST="pack-manifest.json"
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def parse(b):
    def unique(pairs):
        r={}
        for k,v in pairs:
            require(k not in r,"duplicate JSON key");r[k]=v
        return r
    return json.loads(b,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError("nonfinite JSON")))
def path(p):
    require(isinstance(p,str) and p.startswith("data/") and NAME.fullmatch(p[5:]),"unsafe catalog reference")
    return p[5:]
def validate_catalog(c,entries):
    require(c["schema"]=="oneirifact.reference-viewer/v1","unexpected catalog")
    require(type(c["source_pins"]) is dict and bool(c["source_pins"]) and all(isinstance(v,str) and HEX.fullmatch(v) for v in c["source_pins"].values()),"missing source digests")
    refs={"catalog.json"}
    def link(p):
        n=path(p);require(n in entries,"missing catalog asset "+n);refs.add(n);return entries[n]
    seen=set()
    for d in c["datasets"]:
        require(d["id"] not in seen,"duplicate dataset");seen.add(d["id"])
        for k in ("preview","attribution","additional_attribution","inventory"):
            if k in d:link(d[k])
        require(bool(d["layers"]),"empty dataset")
        for m in d["layers"]:
            require(m["id"] not in seen,"duplicate model");seen.add(m["id"])
            f=link(m["file"]);require(f["sha256"]==m["sha256"] and f["bytes"]==m["bytes"],"model catalog hash or length mismatch")
    for p in c["evidence"].values():link(p)
    require(refs==set(entries),"unreferenced assets")
def manifest(entries):
    return json.dumps({"schema":"oneirifact.browser-display-pack/v1","files":[{"name":n,**entries[n]} for n in sorted(entries)]},sort_keys=True,separators=(",",":")).encode()+b"\n"
def inventory(folder):
    require(folder.is_dir() and not folder.is_symlink(),"invalid source directory")
    entries={};total=0
    for p in sorted(folder.iterdir()):
        require(p.is_file() and not p.is_symlink() and NAME.fullmatch(p.name) and p.name!=MANIFEST,"invalid asset "+p.name)
        n=p.stat().st_size;total+=n
        require(0<n<=MAX_FILE and total<=MAX_TOTAL and len(entries)<MAX_FILES,"asset budget")
        entries[p.name]={"bytes":n,"sha256":digest(p)}
    validate_catalog(parse((folder/"catalog.json").read_bytes()),entries)
    return entries
def add(z,n,b):
    i=zipfile.ZipInfo(n,date_time=(1980,1,1,0,0,0));i.create_system=3;i.external_attr=(stat.S_IFREG|0o644)<<16;i.compress_type=zipfile.ZIP_DEFLATED
    z.writestr(i,b,compresslevel=6)
def pack(folder,dest):
    entries=inventory(folder)
    with zipfile.ZipFile(dest,"x") as z:
        for n in sorted(entries):
            b=(folder/n).read_bytes()
            require(len(b)==entries[n]["bytes"] and sha(b)==entries[n]["sha256"],"asset changed")
            add(z,n,b)
        add(z,MANIFEST,manifest(entries))
    return digest(dest)
def verify(src,expected):
    require(isinstance(expected,str) and HEX.fullmatch(expected) and digest(src)==expected,"pack digest mismatch")
    with zipfile.ZipFile(src) as z:
        info=z.infolist();names=[i.filename for i in info]
        require(len(info)<=MAX_FILES+1 and len(set(names))==len(names) and MANIFEST in names,"invalid pack entries")
        require(sum(i.file_size for i in info)<=MAX_TOTAL+(1<<20),"total unpack budget")
        require(all(i.file_size<=MAX_FILE and stat.S_ISREG(i.external_attr>>16) and NAME.fullmatch(i.filename) for i in info),"invalid ZIP file")
        raw=z.read(MANIFEST);require(len(raw)<=1<<20,"manifest budget")
        doc=parse(raw);require(doc["schema"]=="oneirifact.browser-display-pack/v1","pack schema")
        entries={r["name"]:{"bytes":r["bytes"],"sha256":r["sha256"]} for r in doc["files"]}
        require(raw==manifest(entries) and set(entries)==set(names)-{MANIFEST},"manifest mismatch")
        for n,r in entries.items():
            b=z.read(n);require(len(b)==r["bytes"] and sha(b)==r["sha256"],"asset digest mismatch "+n)
        validate_catalog(parse(z.read("catalog.json")),entries)
        return entries
def restore(src,expected,dest):
    entries=verify(src,expected)
    dest.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(src) as z:
        for n,r in entries.items():
            b=z.read(n);require(sha(b)==r["sha256"] and len(b)==r["bytes"],"archive changed")
            (dest/n).write_bytes(b)
    require(inventory(dest)==entries,"restore differs")
    return entries
if __name__=="__main__":
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True)
    for command,args in (("pack",("folder","dest")),("verify",("src","sha256")),("restore",("src","sha256","dest"))):
        a=s.add_parser(command)
        for n in args:a.add_argument(n,type=str if n=="sha256" else Path)
    a=p.parse_args()
    if a.command=="pack":print(pack(a.folder,a.dest))
    elif a.command=="verify":print("PACK_VERIFIED",len(verify(a.src,a.sha256)))
    else:print("PACK_RESTORED",len(restore(a.src,a.sha256,a.dest)))
