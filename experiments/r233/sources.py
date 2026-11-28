"""Bounded source availability and female cryosection ingestion witness.
No automatic segmentation, subject inference, or raw image redistribution.
"""
import hashlib,io,json,re,sys,urllib.request,urllib.error
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
NLM="https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/PNG_format/pelvis/"
OSU="https://api.sketchfab.com/v3/models/2610b30793ed47a5baa18b2994bdee6b"
GENEVA="https://www.unige.ch/ssi/ressources/ressources-pedagogiques-ssi/modles-3d/modeles-de-clitoris-et-penis-pour-impression-3d"
def sha(b):return hashlib.sha256(b).hexdigest()
def fetch(url,cap,host):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Oneirifact educational anatomy RDT&E"}),timeout=25) as r:
        assert r.status==200 and r.geturl().startswith("https://"+host+"/")
        b=r.read(cap+1);assert 0<len(b)<=cap
        return b
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,t,attrs):
        if t=="a":self.links.extend(v for k,v in attrs if k=="href" and v)
def main(out):
    out.mkdir(parents=True,exist_ok=False)
    listing=fetch(NLM+"index.html",2<<20,"data.lhncbc.nlm.nih.gov")
    p=Links();p.feed(listing.decode("utf-8","replace"))
    names=sorted({n for n in p.links if re.fullmatch(r"avf[0-9]{4}[abc]\.png",n)})
    assert len(names)>=700
    grouped={}
    for n in names:grouped.setdefault(int(n[3:7]),set()).add(n[7])
    complete=sorted(k for k,v in grouped.items() if v=={"a","b","c"})
    assert len(complete)>=230
    # A small contiguous centre-of-index slab proves ingestibility only,
    # not that these slices contain any named target anatomy.
    centre=complete[len(complete)//2];keys=list(range(centre-1,centre+2))
    assert all(k in complete for k in keys)
    selected=[f"avf{k}{s}.png" for k in keys for s in "abc"]
    def one(n):
        b=fetch(NLM+n,8<<20,"data.lhncbc.nlm.nih.gov")
        with Image.open(io.BytesIO(b)) as im:
            assert im.format=="PNG";im.load();assert im.width>1000 and im.height>500
            return {"name":n,"sha256":sha(b),"bytes":len(b),"size":list(im.size),"mode":im.mode}
    with ThreadPoolExecutor(max_workers=3) as ex:rows=list(ex.map(one,selected))
    assert len({tuple(r["size"]) for r in rows})==1
    (out/"pelvis-file-index.json").write_text(json.dumps({"source":NLM,"listing_sha256":sha(listing),"files":names},indent=2))
    sources=[]
    for label,url,host in (("OSU MRI-derived pelvis metadata",OSU,"api.sketchfab.com"),("UNIGE educational imaging source",GENEVA,"www.unige.ch")):
        try:
            b=fetch(url,2<<20,host)
            row={"source":label,"url":url,"status":"METADATA_RETRIEVED_NOT_GEOMETRY","sha256":sha(b)}
            if url==OSU:
                j=json.loads(b);row.update({"name":j.get("name"),"license":j.get("license"),"is_downloadable":j.get("isDownloadable"),"uid":j.get("uid")})
            else:
                q=Links();q.feed(b.decode("utf-8","replace"));row["official_thingiverse_links"]=[x for x in q.links if x.startswith("https://www.thingiverse.com/")]
        except Exception as e:row={"source":label,"url":url,"status":"METADATA_ACCESS_HELD","error":type(e).__name__,"http_status":getattr(e,"code",None)}
        sources.append(row)
    report={"schema":"oneirifact.female-source-acquisition/v1","nlm":{"status":"PASS_BOUNDED_ORIGINAL_IMAGE_INGEST","source":NLM,"file_count":len(names),"complete_triplets":len(complete),"first":names[0],"last":names[-1],"sample":rows,"sample_bytes":sum(x["bytes"] for x in rows),"scope":"Actual decoded original pelvic cryosection PNGs; sample location by file index only, no labels or geometry. Source is public-domain per NLM; raw images not redistributed."},"other_candidates":sources,"next":"Anatomically annotate relevant slices and verify spacing/orientation from source metadata before segmentation. Do not assume image labels or donor correspondence."}
    (out/"receipt.json").write_text(json.dumps(report,indent=2))
    print("R233_SOURCE_ACQUISITION",json.dumps(report),flush=True)
if __name__=="__main__":main(Path(sys.argv[1]))
