"""Public-source rights/access and paired female pelvic landmark critic.
Aggregate geometry metrics only; do not publish individual records or raw archives.
"""
import csv,hashlib,io,json,re,statistics,urllib.request,urllib.error,zipfile,sys
from pathlib import Path,PurePosixPath
import numpy as np
API="https://zenodo.org/api/records/7809039"
MD5="7c48dd931e25ca258503bb297df137fa"
def fetch(url,limit,hosts):
    req=urllib.request.Request(url,headers={"User-Agent":"Oneirifact anatomy research (public-source qualification)"})
    with urllib.request.urlopen(req,timeout=25) as r:
        host=urllib.parse.urlparse(r.geturl()).hostname
        if host not in hosts:raise ValueError("unexpected origin")
        b=r.read(limit+1)
        if len(b)>limit:raise ValueError("byte budget")
        return b
def probe(url,hosts):
    try:
        b=fetch(url,4<<20,hosts)
        return {"url":url,"status":"PUBLIC_METADATA_RETRIEVED","sha256":hashlib.sha256(b).hexdigest(),"bytes":len(b),"scope":"Metadata only. No geometry or file-level license inferred."}
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError) as e:
        return {"url":url,"status":"ACCESS_HELD","http_status":getattr(e,"code",None),"error":type(e).__name__}
def fcsv(b):
    # FCSV and documented legacy N,X,Z,Y exports. Accept explicit column
    # headers and standard comment records; never guess a missing coordinate.
    text=b.decode("utf-8-sig");lines=[l.strip() for l in text.splitlines() if l.strip()]
    header=[l for l in lines if l.startswith("#")]
    body=[l for l in lines if not l.startswith("#")]
    if not body:raise ValueError("empty_fcsv")
    delimiter=next((x for x in (",",";","\t") if x in body[0]),None)
    fields=list(csv.reader(body,delimiter=delimiter)) if delimiter else [l.split() for l in body]
    if not fields or len(fields[0])<4:raise ValueError("fcsv_width")
    first=[x.strip().lower() for x in fields[0]]
    axes=[1,2,3];key=0
    # If actual x/y/z column names are supplied, preserve that declared order.
    if all(x in first for x in ("x","y","z")):
        axes=[first.index(x) for x in ("x","y","z")]
        key=next((first.index(x) for x in ("n","id","label","landmark","name") if x in first),0)
        fields=fields[1:]
    rows={}
    for row in fields:
        if not row or all(not x.strip() for x in row):continue
        if len(row)<=max([key]+axes):raise ValueError("fcsv_width")
        k=row[key].strip()
        try:q=np.array([float(row[i].strip()) for i in axes])
        except ValueError:raise ValueError("fcsv_coordinate_non_numeric") from None
        if not k or k in rows:raise ValueError("fcsv_duplicate_or_empty_label")
        if not np.isfinite(q).all():raise ValueError("fcsv_nonfinite")
        rows[k]=q
    if not rows:raise ValueError("empty_fcsv")
    return rows,header
def main(out):
    out.mkdir(parents=True,exist_ok=False)
    report={"schema":"oneirifact.female-source-critic/v1","sources":[]}
    for n in (5027460,5027449,5027467):
        report["sources"].append(probe("https://www.thingiverse.com/thing:"+str(n),{"www.thingiverse.com","thingiverse.com"}))
    report["sources"].append(probe("https://api.sketchfab.com/v3/models/2610b30793ed47a5baa18b2994bdee6b/download",{"api.sketchfab.com"}))
    # Zenodo is an independent critic, not a new individual body geometry source.
    try:
        raw=fetch(API,2<<20,{"zenodo.org","www.zenodo.org"})
        meta=json.loads(raw);lic=meta["metadata"].get("license") or {}
        license_id=lic.get("id","") if isinstance(lic,dict) else str(lic)
        info={"source":API,"metadata_sha256":hashlib.sha256(raw).hexdigest(),"license":license_id,"status":"METADATA_ONLY"}
        report["landmark_critic"]=info
        if license_id.lower() not in {"cc-by-4.0","cc0-1.0","cc-by-3.0"}:
            info["status"]="RIGHTS_HELD"
        else:
            f=next(x for x in meta["files"] if x["key"]=="landmarks.zip")
            assert f["checksum"]=="md5:"+MD5
            b=fetch(f["links"]["self"],4<<20,{"zenodo.org","www.zenodo.org"})
            assert hashlib.md5(b).hexdigest()==MD5
            info["archive_sha256"]=hashlib.sha256(b).hexdigest()
            data={1:{},2:{}};headers={1:set(),2:set()};parse_failures={};fcsv_count=0
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                infos=z.infolist();assert len(infos)<=1000 and sum(i.file_size for i in infos)<=32<<20
                assert z.testzip() is None
                for i in infos:
                    if i.is_dir():continue
                    p=PurePosixPath(i.filename);assert not p.is_absolute() and ".." not in p.parts
                    if p.suffix.lower()!=".fcsv":continue
                    obs=next((j for j in (1,2) if any(re.fullmatch(r"observer[_ -]?"+str(j),x,re.I) for x in p.parts)),None)
                    if obs is None:continue
                    fcsv_count+=1
                    try:rows,head=fcsv(z.read(i))
                    except (ValueError,UnicodeError) as e:
                        key=str(e) if isinstance(e,ValueError) and str(e) in {"empty_fcsv","fcsv_width","fcsv_coordinate_non_numeric","fcsv_duplicate_or_empty_label","fcsv_nonfinite"} else type(e).__name__
                        parse_failures[key]=parse_failures.get(key,0)+1
                        continue
                    assert p.stem not in data[obs]
                    data[obs][p.stem]=rows;headers[obs].update(head)
            shared=sorted(set(data[1])&set(data[2]))
            info.update({"fcsv_files_seen":fcsv_count,"parse_failures":parse_failures,"observer_counts":[len(data[1]),len(data[2])],"matching_case_names":len(shared),"coordinate_header_examples":[sorted(x for x in headers[j] if "coordinate" in x.lower())[:3] for j in (1,2)]})
            # Compare complete paired row identifiers only. Avoid treating
            # missing or differently labelled records as matched landmarks.
            per=[];points=0;counts=[]
            for k in shared:
                a,c=data[1][k],data[2][k]
                if not a or set(a)!=set(c):continue
                d=[np.linalg.norm(a[n]-c[n]) for n in sorted(a)]
                per.append(float(np.sqrt(np.mean(np.square(d)))))
                counts.append(len(d));points+=len(d)
            info.update({"complete_matching_cases":len(per),"matching_landmarks":points,"landmark_counts":sorted(set(counts))})
            if per and not parse_failures and len(per)==len(shared)==67:
                info.update({"status":"PASS_PAIRED_SOURCE_SCREEN","per_case_rms_coordinate_units":{"median":statistics.median(per),"p95":float(np.quantile(per,.95)),"max":max(per)},"limits":"Coordinate units/orientation require independent source confirmation; aggregate observer differences, not registration accuracy or individual subject model."})
            else:info["status"]="PAIR_IDENTITY_OR_PARSE_HELD"
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError,KeyError,AssertionError,StopIteration) as e:
        report.setdefault("landmark_critic",{"source":API}).update({"status":"ACQUISITION_OR_PARSE_HELD","error":type(e).__name__,"http_status":getattr(e,"code",None)})
    (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R234_FEMALE_SOURCE_CRITIC",json.dumps(report),flush=True)
if __name__=="__main__":main(Path(sys.argv[1]))
