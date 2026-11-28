"""Export exact CC0 R232 shape basis and sparse skin inputs for browser computation."""
import hashlib,json,sys,zipfile,tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"r232"))
import morphology as m
PIN="98f119556087dddfce98028501fe459b61c746f0094cf0e09c6b7f0dc7461e49"
def main(archive,out):
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==PIN
    out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z,tempfile.TemporaryDirectory() as td:
        inp=Path(td); names=[n for n in z.namelist() if n.startswith("source/") and not n.endswith("/")]
        for n in names:
            p=Path(n);assert len(p.parts)==2 and p.name not in (".","..")
            assert z.getinfo(n).file_size<=16<<20
            (inp/p.name).write_bytes(z.read(n))
        v,f,targets,pins,rig=m.load(inp)
        cols=[v,sum((targets[n] for n,h in m.ADULT["female"]),np.zeros_like(v))/3,sum((targets[n] for n,h in m.OLD),np.zeros_like(v))/3]
        for stage in ("young","old"):
            for k in ((1,0),(1,1),(0,0)):cols.append(targets[m.MACRO[stage][k][0]])
        cols.extend(targets[n] for n,h in m.REGION)
        data=np.stack(cols).astype("<f4")
        assert data.shape==(13,19158,3)
        sk=rig["default.mhskel"];bones=sk["bones"]
        ordered=[];pending=set(bones)
        while pending:
            ready=sorted(n for n in pending if bones[n]["parent"] is None or bones[n]["parent"] in ordered)
            assert ready;ordered+=ready;pending.difference_update(ready)
        ix={n:i for i,n in enumerate(ordered)}
        weights=[[] for _ in range(13380)]
        for n,rows in rig["default_weights.mhw"]["weights"].items():
            for i,w in rows:
                if i<13380 and w>0:weights[i].append([ix[n],w])
        for row in weights:
            s=sum(w for _,w in row);assert s>0
            for x in row:x[1]/=s
        meta={"schema":"oneirifact.adult-morphology-browser/v1","vertex_count":19158,"visible":13380,"triangles":len(f),"basis_count":13,"bones":[{"id":n,"parent":-1 if bones[n]["parent"] is None else ix[bones[n]["parent"]],"head":sk["joints"][bones[n]["head"]],"flex":n in ("spine05","spine04","spine03","spine02","spine01")} for n in ordered],"weights":weights,"source_archive_sha256":PIN}
        (out/"basis.bin").write_bytes(data.tobytes());(out/"faces.bin").write_bytes(f.astype("<u4").tobytes())
        (out/"rig.json").write_text(json.dumps(meta,separators=(",",":")))
        for name in ("LICENSE.md","LICENSE.ASSETS.md"):(out/name).write_bytes((inp/name).read_bytes())
        # Compare actual browser kernel against independent existing Python case coordinates.
        refs=[]
        for tag in ("neutral","athletic","older-athletic","tall-athletic","flexion"):
            spec=json.loads(z.read(tag+"-spec.json"));q=m.shape(spec,v,targets);pv,_=m.pose(q,spec,rig)
            refs.append({"id":tag,"spec":spec,"positions":pv.astype("<f4").ravel().tolist()})
        (out/"witness.json").write_text(json.dumps(refs,separators=(",",":")))
        print("BROWSER_BASIS_READY",data.nbytes,len(f),len(ordered),len(weights),flush=True)
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
