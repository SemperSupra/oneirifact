"""Restore exact qualified generic adult design browser assets, not native code."""
import argparse,json,subprocess,tempfile,zipfile
from pathlib import Path
import anatomy_pack as p
from qualify_r233_delivery import verify_design
ROOT=Path(__file__).resolve().parent
LOCK=ROOT/"adult-design-release-lock.json"
def restore(source=None,dest=None):
    lock=p.parse(LOCK.read_bytes())
    p.require(lock["schema"]=="oneirifact.adult-design-release/v1" and lock["repository"]=="SemperSupra/oneirifact","lock schema or origin")
    p.require(lock["tag"]=="anatomy-display-r233-v3" and lock["asset"]=="adult-design-r233-v1.zip" and p.HEX.fullmatch(lock["sha256"]),"lock asset")
    dest=dest or ROOT.parent/"site"/"morph"
    p.require(not dest.exists() and not dest.is_symlink(),"fresh destination required")
    with tempfile.TemporaryDirectory(prefix="oneirifact-design-") as td:
        if source is None:
            source=Path(td)/"design.zip"
            url="https://github.com/"+lock["repository"]+"/releases/download/"+lock["tag"]+"/"+lock["asset"]
            subprocess.run(["curl","--fail","--silent","--show-error","--location","--max-redirs","4","--proto","=https","--proto-redir","=https","--tlsv1.2","--connect-timeout","10","--max-time","120","--max-filesize","16777216","--output",str(source),url],check=True,timeout=130)
        p.require(source.is_file() and source.stat().st_size<=16<<20,"archive budget")
        rows=verify_design(source,lock["sha256"])
        p.require(len(rows)==lock["files"] and sum(r["bytes"] for r in rows)==lock["unpacked_bytes"],"lock inventory")
        dest.mkdir(parents=True,exist_ok=False)
        with zipfile.ZipFile(source) as z:
            for r in rows:
                q=dest/r["path"];q.parent.mkdir(parents=True,exist_ok=True)
                b=z.read(r["path"]);p.require(p.sha(b)==r["sha256"] and len(b)==r["bytes"],"asset changed");q.write_bytes(b)
        p.require({q.relative_to(dest).as_posix() for q in dest.rglob("*") if q.is_file()}=={r["path"] for r in rows},"restored inventory")
    print("DURABLE_ADULT_DESIGN_RESTORE_PASS",lock["sha256"],len(rows),flush=True)
if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__);a.add_argument("--source",type=Path);a.add_argument("--dest",type=Path);q=a.parse_args();restore(q.source,q.dest)
