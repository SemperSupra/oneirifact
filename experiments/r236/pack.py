"""Build a bounded shared exterior basis and numerical witnesses from pinned sources."""
import hashlib,json,sys,tempfile,zipfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"r235"))
import shared as s
r=s.r;m=s.m
REF="025145c2af4dc0c0d8936e764b88dd03a06a9e389197cadf97eb9b1d634d54fc"
def main(archive,folder,ref,out):
    assert hashlib.sha256(ref.read_bytes()).hexdigest()==REF
    out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as td,zipfile.ZipFile(ref) as z:
        inp=Path(td);v,f,targets,pins,rig=r.source(archive,inp)
        regions,breast=r.region_load(folder,r.lock)
        female,male=s.bases(v,targets,folder,json.loads(s.PIN.read_text()))
        cols=[v]
        for sex in (female,male):
            for stage in ("young","old"):cols.extend(sex[stage])
        cols.extend(targets[n] for n,h in m.REGION)
        cols.extend(regions[k] for k in r.lock["regional"])
        data=np.stack(cols).astype("<f4");assert data.shape==(32,19158,3)
        sk=rig["default.mhskel"];bones=sk["bones"];ordered=[];pending=set(bones)
        while pending:
            ready=sorted(n for n in pending if bones[n]["parent"] is None or bones[n]["parent"] in ordered)
            assert ready;ordered+=ready;pending.difference_update(ready)
        ix={n:i for i,n in enumerate(ordered)};weights=[[] for _ in range(13380)]
        for n,rows in rig["default_weights.mhw"]["weights"].items():
            for i,w in rows:
                if i<13380 and w>0:weights[i].append([ix[n],w])
        for row in weights:
            total=sum(w for _,w in row);assert total>0
            for x in row:x[1]/=total
        meta={"schema":"oneirifact.shared-browser-basis/v1","vertex_count":19158,"visible":13380,"triangles":len(f),"basis_count":32,"regional_keys":list(r.lock["regional"]),"bones":[{"id":n,"parent":-1 if bones[n]["parent"] is None else ix[bones[n]["parent"]],"head":sk["joints"][bones[n]["head"]],"flex":n in ("spine05","spine04","spine03","spine02","spine01")} for n in ordered],"weights":weights}
        (out/"basis.bin").write_bytes(data.tobytes());(out/"faces.bin").write_bytes(f.astype("<u4").tobytes());(out/"rig.json").write_text(json.dumps(meta,separators=(",",":")))
        for name in ("LICENSE.md","LICENSE.ASSETS.md"):(out/name).write_bytes((inp/name).read_bytes())
        receipt=json.loads(z.read("receipt.json"));refs=[]
        for row in receipt["variants"]:
            name=row["id"];spec=json.loads(z.read(name+"-spec.json"))
            q=s.shape(spec,v,targets,female,male,regions);pv,_=m.pose(q,spec["common"],rig)
            refs.append({"id":name,"spec":spec,"positions":pv.astype("<f4").ravel().tolist()})
        # Exercise every common regional control at each endpoint against Python.
        for mix in (0,1):
            for k in regions:
                spec=s.spec(m.profile(),mix,**{k:.6})
                q=s.shape(spec,v,targets,female,male,regions);pv,_=m.pose(q,spec["common"],rig)
                refs.append({"id":str(mix)+"-"+k,"spec":spec,"positions":pv.astype("<f4").ravel().tolist()})
        (out/"witness.json").write_text(json.dumps(refs,separators=(",",":")))
        print("R236_SHARED_BASIS",data.nbytes,len(refs),len(f),len(ordered),flush=True)
if __name__=="__main__":main(*(Path(x) for x in sys.argv[1:]))
