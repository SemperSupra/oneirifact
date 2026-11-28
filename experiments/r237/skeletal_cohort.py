"""Bounded official skeletal cohort acquisition and schema qualification.
No subject-level measurements or source meshes are retained as public artifacts.
"""
import hashlib,json,subprocess,sys,urllib.request
from pathlib import Path
API="https://zenodo.org/api/records/23592083"
MD5="9cf9c127a29bf23e4f4ce14f6a418f50"
V1_MD5="4e6786008d423ea797e1af4987dd2cdf"
CAP=600_000_000
def need(q,msg):
    if not q:raise ValueError(msg)
def run(out,scratch):
    out.mkdir(parents=True,exist_ok=False)
    report={"schema":"oneirifact.skeletal-cohort-intake/v1","source":API,"scope":"Rights, exact lower-extremity/torso MAT archive and schema only. No subject records, trained model, clinical or anatomical admission."}
    try:
        with urllib.request.urlopen(API,timeout=30) as response:
            need(response.status==200 and urllib.parse.urlparse(response.geturl()).hostname=="zenodo.org","metadata origin")
            raw=response.read((2<<20)+1);need(len(raw)<=2<<20,"metadata size")
        meta=json.loads(raw);md=meta["metadata"];lic=md.get("license",{})
        rights=lic.get("id","") if isinstance(lic,dict) else str(lic)
        report.update({"metadata_sha256":hashlib.sha256(raw).hexdigest(),"title":md.get("title"),"license":rights,"access_right":md.get("access_right"),"rights":md.get("rights"),"files":[{"key":f["key"],"size":f["size"],"checksum":f["checksum"]} for f in meta["files"]]})
        expected=MD5
        # Resolve earlier version separately. Never infer v2 rights from a mirror
        # or simply from an open-access flag. Identical bytes from an expressly
        # licensed version may be used under that version's license.
        if rights.lower() not in ("cc-by-4.0","cc0-1.0","cc-by-3.0"):
            v1="https://zenodo.org/api/records/22833546"
            with urllib.request.urlopen(v1,timeout=30) as response:
                need(response.status==200 and urllib.parse.urlparse(response.geturl()).hostname=="zenodo.org","v1 metadata origin")
                old_raw=response.read((2<<20)+1);need(len(old_raw)<=2<<20,"v1 metadata size")
            old=json.loads(old_raw);old_md=old["metadata"];old_lic=old_md.get("license",{})
            old_rights=old_lic.get("id","") if isinstance(old_lic,dict) else str(old_lic)
            report["earlier_version"]={"source":v1,"metadata_sha256":hashlib.sha256(old_raw).hexdigest(),"license":old_rights,"rights":old_md.get("rights"),"files":[{"key":f["key"],"size":f["size"],"checksum":f["checksum"]} for f in old["files"]]}
            if old_rights.lower() not in ("cc-by-4.0","cc0-1.0","cc-by-3.0"):
                report["status"]="HOLD_RIGHTS";return
            old_file=next((f for f in old["files"] if f["key"]=="NM_LEXT.mat" and f["checksum"]=="md5:"+V1_MD5),None)
            if old_file is None:
                report["status"]="HOLD_VERSION_IDENTITY";return
            meta=old;expected=V1_MD5;report["admitted_source"]=v1;report["admitted_license"]=old_rights;report["version_note"]="Earlier version admitted independently; not byte-identical to v2."
        else:
            report["admitted_source"]=API;report["admitted_license"]=rights
        f=next(f for f in meta["files"] if f["key"]=="NM_LEXT.mat")
        need(f["checksum"]=="md5:"+expected and 0<f["size"]<=CAP,"source pin/budget")
        url=f["links"]["self"];need(url.startswith("https://zenodo.org/"),"source origin")
        path=scratch/"NM_LEXT.mat"
        subprocess.run(["curl","--fail","--silent","--show-error","--location","--max-redirs","3","--proto","=https","--proto-redir","=https","--connect-timeout","15","--max-time","220","--max-filesize",str(CAP),url,"-o",str(path)],check=True,timeout=235)
        need(path.stat().st_size==f["size"],"source length")
        with path.open("rb") as b:need(hashlib.file_digest(b,"md5").hexdigest()==expected,"source MD5")
        with path.open("rb") as b:report["archive_sha256"]=hashlib.file_digest(b,"sha256").hexdigest()
        report["download_bytes"]=path.stat().st_size;report["source_md5"]=expected
        import h5py
        if h5py.is_hdf5(path):
            with h5py.File(path,"r") as h:
                rows=[]
                # Only declared top-level structure metadata. Never publish
                # identifiers, individual vertex arrays or metadata values.
                for key in ("NM_LEXT","Faces","Metadata"):
                    if key not in h:continue
                    v=h[key]
                    row={"field":key,"type":type(v).__name__}
                    if isinstance(v,h5py.Dataset):row.update(shape=list(v.shape),dtype=str(v.dtype))
                    else:
                        row["child_count"]=len(v)
                        row["child_type_counts"]={kind:sum(type(v[k]).__name__==kind for k in v) for kind in ("Dataset","Group")}
                    rows.append(row)
                report.update({"format":"MATLAB HDF5","top_level_count":len(h),"declared_fields":rows})
        else:
            from scipy.io import whosmat
            report.update({"format":"MATLAB non-HDF5","declared_fields":[{"field":name,"shape":list(shape),"class":typ} for name,shape,typ in whosmat(path) if name in ("NM_LEXT","Faces","Metadata")]})
        report["status"]="PASS_EXACT_SOURCE_SCHEMA" if report["declared_fields"] else "HOLD_SCHEMA"
    except Exception as e:
        report.update({"status":"HOLD_ACQUISITION_OR_SCHEMA","error":type(e).__name__})
    finally:
        (out/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
        print("R237_SKELETAL_COHORT",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
