"""Read the licensed paired pelvic landmark archive using its documented source format.

Publish aggregate reproducibility results and schema diagnostics only.
No individual landmarks or patient records are emitted.
"""
import csv,hashlib,io,json,re,sys,urllib.request,zipfile
from pathlib import Path,PurePosixPath
from collections import Counter
import numpy as np
API="https://zenodo.org/api/records/7809039"
MD5="7c48dd931e25ca258503bb297df137fa"
SHA="acf496381916b9c6e4b3b21fcb07d190668c5cac0270563fb4b99d0ccff1f089"
def need(x,msg):
    if not x:raise ValueError(msg)
def get(url,cap):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Oneirifact public anatomical research"}),timeout=40) as r:
        need(r.status==200 and urllib.parse.urlparse(r.geturl()).hostname in ("zenodo.org","www.zenodo.org"),"source origin")
        b=r.read(cap+1);need(len(b)<=cap,"source budget")
        return b
def diagnostics(raw):
    # Only structural descriptors; do not publish individual coordinate values.
    text=raw.decode("utf-8-sig")
    lines=[x.strip() for x in text.splitlines() if x.strip() and not x.lstrip().startswith("#")]
    widths={}
    for delimiter in (",",";","\t"," "):
        widths[repr(delimiter)]=dict(Counter(len(x.split(delimiter)) if delimiter!=" " else len(x.split()) for x in lines))
    return {"data_lines":len(lines),"widths":widths}
def parse(raw):
    text=raw.decode("utf-8-sig")
    lines=[x.strip() for x in text.splitlines() if x.strip() and not x.lstrip().startswith("#")]
    need(lines,"empty")
    # Source documents N,X,Z,Y. Support CSV, semicolon, tab or whitespace,
    # and a four-line scalar sequence only when the source reader confirms it.
    opts=[]
    for delim in (",",";","\t",None):
        rows=[x.split() if delim is None else [a.strip() for a in x.split(delim)] for x in lines]
        if rows and [x.lower() for x in rows[0]]==["n","x","z","y"]:rows=rows[1:]
        if rows and all(len(r)==4 for r in rows):
            try:
                a=np.array([[float(x) for x in r] for r in rows])
            except ValueError:continue
            if np.isfinite(a).all() and np.all(a[:,0]==np.round(a[:,0])) and len(set(a[:,0]))==len(a):
                opts.append(a)
    if not opts:return None
    need(all(np.array_equal(opts[0],a) for a in opts),"ambiguous delimiter")
    a=opts[0]
    return {int(row[0]):row[[1,3,2]] for row in a}
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    meta=json.loads(get(API,2<<20))
    license=meta["metadata"]["license"];license=license["id"] if isinstance(license,dict) else license
    need(license.lower()=="cc-by-4.0","license")
    f=next(f for f in meta["files"] if f["key"]=="landmarks.zip")
    need(f["checksum"]=="md5:"+MD5,"source metadata pin")
    raw=get(f["links"]["self"],4<<20);need(hashlib.md5(raw).hexdigest()==MD5 and hashlib.sha256(raw).hexdigest()==SHA,"source archive pin")
    report={"schema":"oneirifact.pelvic-paired-critic/v1","archive_sha256":SHA,"license":license,"data_order":"N,X,Z,Y; normalized to X,Y,Z","scope":"Paired observer aggregate geometry only; no population anatomy model or individual records."}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(z.testzip() is None and len(z.infolist())<=1000 and sum(i.file_size for i in z.infolist())<=32<<20,"archive integrity")
        source_readers={}
        for name in z.namelist():
            p=PurePosixPath(name);need(not p.is_absolute() and ".." not in p.parts,"path")
            if p.name.lower() in ("getlandmarks.m","readdata.m"):
                b=z.read(name);s=b.decode("utf-8-sig",errors="replace")
                # Record actual source parsing statements without any case values.
                lines=[line.strip() for line in s.splitlines() if re.search(r"\b(readmatrix|readtable|textscan|fscanf|sscanf|importdata|dlmread|fgetl|fgets|strsplit|split|str2double|str2num|feof)\b|line\s*[({]",line,re.I)]
                source_readers[p.name]={"sha256":hashlib.sha256(b).hexdigest(),"reader_statements":lines[:40]}
        report["source_readers"]=source_readers
        data={1:{},2:{}};counts=Counter();fail=Counter();schema=None
        for i in z.infolist():
            p=PurePosixPath(i.filename)
            if i.is_dir() or p.suffix.lower()!=".fcsv":continue
            obs=next((j for j in (1,2) if any(re.fullmatch(r"observer[_ -]?"+str(j),x,re.I) for x in p.parts)),None)
            if obs is None:continue
            counts[obs]+=1
            b=z.read(i);a=parse(b)
            if a is None:
                fail["no_documented_four_column_parse"]+=1
                if schema is None:
                    schema=diagnostics(b)
                    # FCSV declared column names are format metadata, not patient data.
                    schema["column_header"]=[x[:500] for x in b.decode("utf-8-sig").splitlines() if x.lstrip().startswith("#") and re.search(r"columns|coordinate system|version",x,re.I)][:5]
                    schema["first_numeric_row_types"]=[["numeric" if re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?",v.strip()) else "text" if v.strip() else "empty" for v in row.split(",")] for row in b.decode("utf-8-sig").splitlines() if len(row.split(",")) in (14,16)][:1]
                continue
            need(p.stem not in data[obs],"duplicate case");data[obs][p.stem]=a
        shared=set(data[1])&set(data[2]);per=[];sizes=Counter()
        for case in sorted(shared):
            a,b=data[1][case],data[2][case]
            if set(a)!=set(b):continue
            ds=np.array([np.linalg.norm(a[k]-b[k]) for k in sorted(a)])
            per.append(float(np.sqrt(np.mean(ds*ds))));sizes[len(ds)]+=1
        report.update({"observed_files":[counts[1],counts[2]],"parsed_files":[len(data[1]),len(data[2])],"parse_failures":dict(fail),"first_failed_schema":schema,"matched_cases":len(shared),"complete_cases":len(per),"landmark_count_histogram":dict(sizes)})
        if not fail and len(per)==67:
            report["status"]="PASS_PAIRED_SOURCE_SCREEN"
            report["rms_coordinate_units"]={"median":float(np.median(per)),"p95":float(np.quantile(per,.95)),"max":max(per)}
        else:report["status"]="HOLD_DOCUMENTED_SCHEMA"
    (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R237_PELVIC_SCHEMA",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":run(Path(sys.argv[1]))
