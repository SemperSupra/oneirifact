"""Clean reconstruction from a checksum-pinned official library.
No expiring action artifact is a build input. Optional baseline compares actual
published research bytes; freeze independently compared content before release.
"""
import hashlib,json,sys,zipfile,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"experiments/r215"))
from compare_ldraw import run as compare
LIB="023083918da2d3697c794fb4267975509584f3611b993095874206a803fa610f"
OLD={"basic":("15232521230","3c69e2c331af0b4035f511f0cbb3ce69d41482d0477b9c3cc8f3e2d754eab60d"),"special":("15232132427","9fa2b51c1b0a8a5e1dcbe9deb024e6e39a0bed7c111e4bc1b9abb595d0398fd8"),"geometry":("15232986038","64bb52981b46a402210c200e97437edff93597733e9886332a5544dd27130bea")}
def sha(b):return hashlib.sha256(b).hexdigest()
def run(script,*args):subprocess.run([sys.executable,str(HERE/script),*map(str,args)],check=True)
def pack(root,target):
    with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                i=zipfile.ZipInfo(p.relative_to(root).as_posix(),(1980,1,1,0,0,0))
                i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16
                z.writestr(i,p.read_bytes())
def manifest(z):
    # Compare geometry, source, and structured receipts, not font/raster preview.
    return {n:sha(z.read(n)) for n in sorted(z.namelist()) if not n.endswith(".png") and not n.endswith("/")}
def main():
    library,work,out=map(Path,sys.argv[1:4]);baseline=Path(sys.argv[4]) if len(sys.argv)>4 else None
    assert sha(library.read_bytes())==LIB,"official library changed"
    work.mkdir(parents=True,exist_ok=False)
    for family in ("basic","special"):
        run("import_parts.py",library,family,work/family)
        pack(work/family,work/(family+".zip"))
        shutil.copyfile(work/(family+".zip"),work/("github-actions-artifact-"+OLD[family][0]+".zip"))
    run("reconstruct.py",work,work/"geometry","geometry")
    pack(work/"geometry",work/"geometry.zip")
    rebuilt={};digests={}
    for name in OLD:
        path=work/(name+".zip");digests[name]=sha(path.read_bytes())
        with zipfile.ZipFile(path) as z:rebuilt[name]=manifest(z)
    lock=HERE/"content-lock.json"
    if lock.exists():
        assert json.loads(lock.read_text())==rebuilt,"independent replay content drift"
    elif baseline is None:
        raise RuntimeError("no committed content lock or independent baseline")
    if baseline is not None:
        for name,(_,digest) in OLD.items():
            path=baseline/(name+".zip");assert sha(path.read_bytes())==digest,"old artifact hash"
            with zipfile.ZipFile(path) as z:
                prev=manifest(z)
                if prev!=rebuilt[name]:
                    diff=sorted(set(prev)^set(rebuilt[name])|{k for k in prev.keys()&rebuilt[name].keys() if prev[k]!=rebuilt[name][k]})
                    raise RuntimeError(f"{name} content drift: {diff[:20]}")
    compare(work,out,digests)
    (out/"content-lock.json").write_text(json.dumps(rebuilt,indent=2,sort_keys=True)+"\n")
    (out/"rebuild-receipt.json").write_text(json.dumps({"library_sha256":LIB,"archive_digests":digests,"replayed_content_files":sum(map(len,rebuilt.values())),"old_artifact_parity":baseline is not None,"scope":"standalone reference reconstruction, not native Foundry"},indent=2))
    print("R216_CONTENT_REPLAY_PASS",sum(map(len,rebuilt.values())))
if __name__=="__main__":main()
