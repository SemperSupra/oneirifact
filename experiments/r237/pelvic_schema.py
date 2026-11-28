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
def parse(raw,author):
    text=raw.decode("utf-8-sig")
    headers=[x.strip() for x in text.splitlines() if x.lstrip().startswith("#")]
    expected="id,x,y,z,ow,ox,oy,oz,vis,sel,lock,label,desc,associatedNodeID"
    cols=[x.split("=",1)[1].strip() for x in headers if x.lower().startswith("# columns") and "=" in x]
    if cols!=[expected]:return None,"declared_header"
    # Follow the pinned author reader's literal comma split, not a CSV dialect
    # inferred from optional free-text description columns.
    lines=[x.strip() for x in text.splitlines() if x.strip() and not x.lstrip().startswith("#")]
    rows=[[x.strip() for x in line.split(",")] for line in lines]
    if len(rows)<4 or any(len(r)!=2 for r in rows[:3]):return None,"three_metadata_rows"
    names=author.get("landmark_names",[])
    if len(names)!=len(rows)-3 or len(set(names))!=len(names):return None,"author_landmark_order_count"
    result={}
    for name,r in zip(names,rows[3:]):
        if len(r)<14 or len(r)>32:return None,"landmark_width"
        try:x,y,z=(float(r[i]) for i in (1,2,3))
        except ValueError:return None,"coordinate_parse"
        if not np.isfinite([x,y,z]).all():return None,"nonfinite"
        result[name]=np.array([y,-z,x])
    return result,"ok"
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    meta=json.loads(get(API,2<<20))
    license=meta["metadata"]["license"];license=license["id"] if isinstance(license,dict) else license
    need(license.lower()=="cc-by-4.0","license")
    f=next(f for f in meta["files"] if f["key"]=="landmarks.zip")
    need(f["checksum"]=="md5:"+MD5,"source metadata pin")
    raw=get(f["links"]["self"],4<<20);need(hashlib.md5(raw).hexdigest()==MD5 and hashlib.sha256(raw).hexdigest()==SHA,"source archive pin")
    report={"schema":"oneirifact.pelvic-paired-critic/v1","archive_sha256":SHA,"license":license,"data_order":"Declared Slicer FCSV x,y,z transformed by author getLandmarks.m to y,-z,x","scope":"Paired observer aggregate geometry only; no population anatomy model or individual records."}
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
                if p.name.lower()=="getlandmarks.m":
                    # Extract only literal semantic landmark names from the
                    # author source declaration. Never extract subject values.
                    clean="\n".join(x.split("%",1)[0] for x in s.splitlines())
                    block=re.search(r"\blandmark\s*=\s*\{(.*?)\}\s*;",clean,re.S)
                    names=re.findall(r"'([A-Za-z][A-Za-z0-9_]*)'",block.group(1)) if block else []
                    if not names:
                        pairs=re.findall(r"\blandmark\s*\{\s*(\d+)\s*\}\s*=\s*'([A-Za-z][A-Za-z0-9_]*)'\s*;",clean)
                        if pairs and sorted(int(k) for k,v in pairs)==list(range(1,len(pairs)+1)):
                            names=[v for k,v in sorted(pairs,key=lambda x:int(x[0]))]
                    source_readers[p.name]["landmark_names"]=names
                    source_readers[p.name]["landmark_declaration_lines"]=[x.strip() for x in s.splitlines() if re.search(r"\blandmark\s*(=|\{)",x,re.I)][:50]
        report["source_readers"]=source_readers
        author=source_readers.get("getLandmarks.m",{})
        need(author.get("sha256")=="2deed7b048ab7ba5511f0451b8736a8ff866cc6f69488420ca267d4005e53e82","author reader pin")
        data={1:{},2:{}};counts=Counter();fail=Counter();schema=None
        for i in z.infolist():
            p=PurePosixPath(i.filename)
            if i.is_dir() or p.suffix.lower()!=".fcsv":continue
            obs=next((j for j in (1,2) if any(re.fullmatch(r"observer[_ -]?"+str(j),x,re.I) for x in p.parts)),None)
            if obs is None:continue
            counts[obs]+=1
            b=z.read(i);a,reason=parse(b,author)
            if a is None:
                fail[reason]+=1
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
            if list(a)!=list(b):continue
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
