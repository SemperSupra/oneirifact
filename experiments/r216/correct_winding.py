"""Correct global winding of a single closed consistently oriented candidate shell.
Original vertex bytes and triangle membership are retained; no repair of references.
"""
import sys,json,hashlib,zipfile
from pathlib import Path
from topology_oracle import measure
IDS=("3001","3002","3003","3004","3005","3020","3022")
def topology_ok(a):
    return a["vertex_connected_components"]==1 and all(a[k]==0 for k in ("open_edges","nonmanifold_edges","inconsistent_two_face_edges","degenerate_removed_for_measurement"))
def reverse(raw):
    lines=[]
    for line in raw.decode().splitlines(keepends=True):
        t=line.split()
        if t and t[0]=="f":
            assert len(t)==4
            lines.append("f "+t[1]+" "+t[3]+" "+t[2]+("\n" if line.endswith("\n") else ""))
        else:lines.append(line)
    return "".join(lines).encode()
def run(inp,out):
    assert hashlib.sha256(inp.read_bytes()).hexdigest()=="64bb52981b46a402210c200e97437edff93597733e9886332a5544dd27130bea"
    out.mkdir(parents=True,exist_ok=False);rows=[]
    with zipfile.ZipFile(inp) as z:
        for id in IDS:
            raw=z.read(id+"/candidate.obj")
            old=measure(raw)
            assert topology_ok(old) and old["signed_volume_mm3_diagnostic"]<0
            corrected=reverse(raw);new=measure(corrected)
            assert topology_ok(new) and new["signed_volume_mm3_diagnostic"]>0
            assert reverse(corrected)==raw
            assert all(old[k]==new[k] for k in old if k!="signed_volume_mm3_diagnostic")
            assert abs(old["signed_volume_mm3_diagnostic"]+new["signed_volume_mm3_diagnostic"])<1e-8
            d=out/id;d.mkdir();(d/"candidate-outward.obj").write_bytes(corrected)
            for name in ("graph.json","attribution.json","recognized-references.json"):(d/name).write_bytes(z.read(id+"/"+name))
            rows.append({"id":id,"old":old,"new":new,"original_sha256":hashlib.sha256(raw).hexdigest(),"corrected_sha256":hashlib.sha256(corrected).hexdigest(),"status":"GLOBAL_WINDING_CORRECTED_NOT_SOLID_EQUIVALENCE"})
    (out/"receipt.json").write_text(json.dumps({"scope":"Global orientation correction only; no self-intersection test or source solid equivalence; original R209 unchanged","results":rows},indent=2))
    print("WINDING_CORRECTION_PASS",len(rows))
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
