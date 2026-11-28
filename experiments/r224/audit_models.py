"""Independent checks of the exact R224 artifacts, not a clinical anatomy review."""
import sys,hashlib,json,zipfile,io,math
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image
PINS={"worklist":"2af4a629319751eb638904d3e1b232e7354d256109c26544779fd574d8e57d44","male":"cfe28cd8f51f32b32dddf090f64fba883e5406a54f507bf7e95dad66d6bb9d6f","female":"1763e99163aa20c3b5928d391314193f29f1771ed00dd5efce4eda3a9599a428"}
def sha(b):return hashlib.sha256(b).hexdigest()
def checked(p,k):
    assert sha(p.read_bytes())==PINS[k],k
    z=zipfile.ZipFile(p);assert z.testzip() is None
    return z
def mesh(raw,fmt):
    return trimesh.load(io.BytesIO(raw),file_type=fmt,force="scene",process=False).to_geometry()
def key(id):
    if id=="pineal_gland":return "pineal gland","unspecified"
    side,tail=id.split("_",1)
    if "parathyroid" in tail:return "parathyroid gland",side+" "+tail.split("_")[0]
    if tail.endswith("_duct"):
        return "duct of "+tail.removesuffix("_duct").replace("_"," ")+" gland",side
    return tail.replace("_"," "),side
def main(inp,out):
    out.mkdir(parents=True,exist_ok=False)
    with checked(inp/"worklist.zip","worklist") as z:
        work=json.loads(z.read("worklist.json"))["requirements"]
    results=[]
    for sex in ("male","female"):
        with checked(inp/(sex+".zip"),sex) as z:
            rec=json.loads(z.read("receipt.json"));assert rec["sex"]==sex and len(rec["models"])==9
            image=Image.open(io.BytesIO(z.read("model-review.png")));image.verify()
            assert image.size==(1280,860)
            for row in rec["models"]:
                id=row["id"];p=id+"/";src=json.loads(z.read(p+"source.json"))["parameters"]
                assert src==row["parameters"]
                raw=z.read(p+"model.glb");assert sha(raw)==row["mesh_sha256"]
                a=mesh(raw,"glb");b=mesh(z.read(p+"model.obj"),"obj")
                assert len(a.faces)==len(b.faces)==row["triangles"]
                # Same ordered triangle positions within floating-point export tolerance.
                maxerr=float(np.max(np.linalg.norm(a.vertices[a.faces]-b.vertices[b.faces],axis=2)))
                assert maxerr<2e-7,(id,maxerr)
                a.merge_vertices(digits_vertex=12)
                assert a.is_watertight and a.is_winding_consistent and a.volume>0
                assert abs(a.volume*1e9-row["volume_mm3"])<.01*row["volume_mm3"]
                if src["type"]=="hollow_duct":
                    assert a.euler_number==0
                    # Read vertices near the start ring, which lies in local XY.
                    # Curved sweep is tangent to Z at the start; use original
                    # generated ring order only after verifying start positions.
                    v=a.vertices*1000
                    q=v[np.abs(v[:,2])<1e-7]
                    radii=np.linalg.norm(q[:,:2],axis=1)
                    # Other ring points can approach the plane; test actual
                    # outer/inner circles with distinct radius bands.
                    inner=int(np.sum(abs(radii-src["inner_radius_mm"])<1e-5))
                    outer=int(np.sum(abs(radii-src["outer_radius_mm"])<1e-5))
                    assert inner>=48 and outer>=48,(id,inner,outer)
                    lumen={"inner_end_ring_vertices":inner,"outer_end_ring_vertices":outer,"inner_diameter_mm":src["inner_radius_mm"]*2}
                else:
                    assert a.euler_number==2
                    assert np.max(abs(a.extents*1000-np.array(src["dimensions_mm"])))<.001
                    lumen=None
                structure,side=key(id)
                matches=[w for w in work if w["sex"]==sex and w["structure"]==structure and w["laterality"]==side]
                assert len(matches)==1,(id,matches)
                w=matches[0]
                results.append({"sex":sex,"id":id,"source_worklist_status":w["status"],"source_mesh_ids":w["source_mesh_ids"],"compound_descendants":w["compound_descendants"],"transport_max_error_m":maxerr,"watertight":bool(a.is_watertight),"euler":int(a.euler_number),"lumen_end_ring_check":lumen,"admission":"HOLD_REFERENCE_RESOLUTION_AND_PLACEMENT"})
    summary={"models":len(results),"transport_and_topology_pass":len(results),"baseline_direct_matches":sum(x["source_worklist_status"]=="DIRECT_NAME_MATCH_REVIEW" for x in results),"baseline_compound_matches":sum(x["source_worklist_status"]=="COMPOUND_ANCESTOR_REVIEW" for x in results),"no_exact_name_match":sum(x["source_worklist_status"]=="NO_EXACT_NAME_MATCH" for x in results),"scope":"Independent exact package, mesh transport, topology, measured local dimensions and duct opening checks. No anatomical landmark, clinical, native or visual-expert admission; name screen only."}
    (out/"audit.json").write_text(json.dumps({"summary":summary,"results":results},indent=2))
    print("R224_INDEPENDENT_AUDIT",json.dumps(summary))
    print("R224_SOURCE_STATUS",json.dumps([{"sex":x["sex"],"id":x["id"],"status":x["source_worklist_status"]} for x in results]))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
