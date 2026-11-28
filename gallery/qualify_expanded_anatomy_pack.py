"""Qualify the exact R230 browser candidate for durable public asset custody.

This is not a native anatomical model release. No geometry is regenerated.
"""
import argparse,json,stat,zipfile,tempfile
from pathlib import Path
import anatomy_pack as p
OUTER="6dcff4d332177783b76d51be2def89b50819c9fc21686e20664da26bc3143908"
SHA="ffac8867db9951a3d721558e7aad8ae9250b00798d4bf65b8c53e3d811ec0947"
BASE="d71b9df7a88c3811e343de3d34313af718d429da0664f1f516b846d07f0c1c9c"
ASSET="anatomy-display-r231-v2.zip"
EXPECTED={"assets":60,"datasets":6,"models":37,"bytes":53773461}
def qualify(candidate,baseline,out,outer):
    out.mkdir(parents=True,exist_ok=False)
    asset=out/ASSET
    if outer:
        p.require(p.digest(candidate)==OUTER,"unexpected candidate transport archive")
        with zipfile.ZipFile(candidate) as z:
            info=z.infolist()
            p.require(len(info)==1 and info[0].filename=="anatomy-extension-candidate.zip" and 0<info[0].file_size<=64<<20 and not stat.S_ISLNK(info[0].external_attr>>16),"outer archive inventory")
            asset.write_bytes(z.read(info[0]))
    else:
        p.require(candidate.stat().st_size<=64<<20 and p.digest(candidate)==SHA,"unexpected public asset")
        asset.write_bytes(candidate.read_bytes())
    entries=p.verify(asset,SHA)
    base=p.verify(baseline,BASE)
    p.require(len(base)==47 and all(entries.get(n)==r for n,r in base.items() if n!="catalog.json"),"released baseline asset changed")
    with zipfile.ZipFile(asset) as z:
        c=p.parse(z.read("catalog.json"))
        ids=[d["id"] for d in c["datasets"]]
        p.require(ids==["male","female","ct","pineal","pelvis","digits"],"dataset identity")
        p.require(all("receipt" in d and "attribution" in d and "inventory" in d for d in c["datasets"][-2:]),"new dataset source evidence absent")
        models=sum(len(d["layers"]) for d in c["datasets"])
    actual={"assets":len(entries),"datasets":len(ids),"models":models,"bytes":sum(r["bytes"] for r in entries.values())}
    p.require(actual==EXPECTED,"candidate inventory")
    with tempfile.TemporaryDirectory(prefix="oneirifact-v2-") as td:
        p.require(p.restore(asset,SHA,Path(td)/"restore")==entries,"restore mismatch")
    report={"schema":"oneirifact.browser-display-release-receipt/v1","pack_sha256":SHA,"released_base_sha256":BASE,"source_candidate_pr":58,"source_qualified_head":"d91996a4d6a3c3e60123b46e8e736b3d9d7cd23d","source_run":46125814350,"source_artifact":15256050572,"source_outer_sha256":OUTER,"unchanged_baseline_assets":46,**actual,"status":"PASS_EXACT_DISPLAY_PACK_RESTORE","scope":"Separate historical pelvis and grouped digit references; no fusion, anatomical admission or native engine claim."}
    (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R231_DURABLE_EXPANDED_PACK",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__);a.add_argument("candidate",type=Path);a.add_argument("baseline",type=Path);a.add_argument("out",type=Path);a.add_argument("--outer",action="store_true");q=a.parse_args()
    qualify(q.candidate,q.baseline,q.out,q.outer)
