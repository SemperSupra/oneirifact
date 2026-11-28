"""Restore the pinned, public, independently qualified browser asset release.

No GitHub credentials or temporary workflow artifacts are needed. Raw donor
source reconstruction remains a separate RDT&E workflow.
"""
import argparse,json,subprocess,tempfile
from pathlib import Path
import anatomy_pack as p
ROOT=Path(__file__).resolve().parent
LOCK=ROOT/"anatomy-release-lock.json"
MAX_DOWNLOAD=64<<20
def restore(source=None,dest=None):
    lock=p.parse(LOCK.read_bytes())
    p.require(lock["schema"]=="oneirifact.browser-display-release/v1","lock schema")
    p.require(lock["repository"]=="SemperSupra/oneirifact","lock repository")
    p.require(lock["asset"]==lock["tag"]+".zip" and p.NAME.fullmatch(lock["asset"].replace(".zip",".txt")),"lock asset")
    p.require(p.HEX.fullmatch(lock["sha256"]),"lock digest")
    dest=dest or ROOT.parent/"site"/"anatomy"/"data"
    p.require(not dest.exists() and not dest.is_symlink(),"restore destination exists")
    url="https://github.com/"+lock["repository"]+"/releases/download/"+lock["tag"]+"/"+lock["asset"]
    with tempfile.TemporaryDirectory(prefix="oneirifact-release-") as td:
        if source is None:
            source=Path(td)/"pack.zip"
            subprocess.run(["curl","--fail","--silent","--show-error","--location","--max-redirs","4","--proto","=https","--proto-redir","=https","--tlsv1.2","--connect-timeout","10","--max-time","120","--max-filesize",str(MAX_DOWNLOAD),"--output",str(source),url],check=True,timeout=130)
        p.require(source.is_file() and source.stat().st_size<=MAX_DOWNLOAD,"archive byte budget")
        entries=p.verify(source,lock["sha256"])
        p.require(len(entries)==lock["assets"] and sum(r["bytes"] for r in entries.values())==lock["unpacked_bytes"],"lock inventory mismatch")
        import zipfile
        with zipfile.ZipFile(source) as z:
            cat=p.parse(z.read("catalog.json"))
        p.require(len(cat["datasets"])==lock["datasets"] and sum(len(d["layers"]) for d in cat["datasets"])==lock["models"],"lock catalog mismatch")
        p.restore(source,lock["sha256"],dest)
    print("DURABLE_BROWSER_RESTORE_PASS",lock["tag"],lock["sha256"],len(entries),lock["models"],flush=True)
    return lock
if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__);a.add_argument("--source",type=Path);a.add_argument("--dest",type=Path);q=a.parse_args()
    restore(q.source,q.dest)
