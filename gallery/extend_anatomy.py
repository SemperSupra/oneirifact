"""Build an isolated viewer candidate from two independently qualified research subsets.

Never fuse donors, mutate base assets, infer phalanx identities or admit anatomy.
"""
import io,json,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
import anatomy_pack as p
BASE="d71b9df7a88c3811e343de3d34313af718d429da0664f1f516b846d07f0c1c9c"
PELVIS="f4d462ab23fb4a11700c39785e2ace9e8d09f4bac424ce25451f291e64194f09"
DIGITS="9cf0e4017b4067643ed9c937652d3d0db280c918f81a1f32b8dc57b367b25d6d"
def checked(path,sha):
    p.require(p.digest(path)==sha,"input digest mismatch")
    return zipfile.ZipFile(path)
def scene(raw):
    p.require(raw[:4]==b"glTF","not GLB")
    return trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
def world(s,n):
    t,g=s.graph[n];q=s.geometry[g].copy();q.apply_transform(t)
    p.require(len(q.faces)>0 and np.isfinite(q.vertices).all(),"invalid mesh")
    return q
def write(out,n,b):
    p.require(p.NAME.fullmatch(n) and not (out/n).exists(),"invalid or existing asset")
    (out/n).write_bytes(b)
    return "data/"+n
def js(d):return (json.dumps(d,sort_keys=True,indent=2)+"\n").encode()
def model(out,key,label,raw,expected):
    s=scene(raw);nodes=set(s.graph.nodes_geometry)
    p.require(nodes==set(expected),"source node set")
    count=sum(len(world(s,n).faces) for n in nodes)
    p.require(count==sum(expected.values()) and count<=140000,"unexpected mesh or triangle budget")
    return {"id":key,"label":label,"file":write(out,key+".glb",raw),"bytes":len(raw),"sha256":p.sha(raw),"source_triangles":count,"display_triangles":count,"nodes":len(nodes),"fidelity":"Original reference subset geometry"}
def pelvis(path,out):
    with checked(path,PELVIS) as z:
        receipt=p.parse(z.read("receipt.json"));raw=z.read("historical-pelvis-reference.glb")
        p.require(receipt["frame_screen"]=="PASS_SHARED_TRIANGLE_FRAME_ONLY" and receipt["shared_anchor_count"]==receipt["shared_exact_pass_count"]==48,"frame receipt")
        p.require(receipt["subset_sha256"]==p.sha(raw) and receipt["transport_max_coordinate_error_m"]<=2e-6,"subset receipt")
        expected={r["node"]:r["triangles"] for r in receipt["recovered"]}
        p.require(len(expected)==8 and all(not r["present_in_v1_10_by_exact_node"] for r in receipt["recovered"]),"pelvis provenance")
        layer=model(out,"pelvis-historical","Recovered ischium and pubis",raw,expected)
        inv=[{"id":n,"names":[n.removeprefix("VH_F_").replace("_"," ")],"layer":layer["id"],"triangles":v} for n,v in sorted(expected.items())]
        return {"id":"pelvis","label":"Female historical pelvic reference","source":"HRA v1.5 source recovery","scope":"Eight recovered compact/spongy bone nodes; 48 shared skeletal coordinate checks passed. Separate historical subset, not fused into the current reference or clinically validated.","preview":write(out,"pelvis-preview.png",z.read("pelvis-preview.png")),"attribution":write(out,"pelvis-attribution.txt",z.read("ATTRIBUTION.txt")),"inventory":write(out,"pelvis-inventory.json",js(inv)),"receipt":write(out,"pelvis-receipt.json",z.read("receipt.json")),"layers":[layer],"source_archive_sha256":PELVIS}
def digits(path,out):
    with checked(path,DIGITS) as z:
        receipt=p.parse(z.read("receipt.json"));summary=receipt["summary"];raw=z.read("ct-digit-components.glb")
        p.require(summary["subset_sha256"]==p.sha(raw) and summary["groups"]==summary["observed_edge_components"]==20 and summary["count_match_groups"]==0,"digit receipt")
        original=scene(raw);groups=receipt["groups"]
        p.require(len(groups)==20 and all(len(r["components"])==1 and r["geometry_admission"]=="NOT_QUALIFIED" for r in groups),"unexpected group status")
        inv=[];layers=[];used=set();drift=0.
        for region in ("HAND","FOOT"):
            for side in ("LEFT","RIGHT"):
                rows=[r for r in groups if r["region"]==region and r["side"]==side]
                p.require(len(rows)==5 and {r["digit"] for r in rows}==set(range(1,6)),"digit group coverage")
                key="digit-"+region.lower()+"-"+side.lower()
                dst=trimesh.Scene();expected={}
                for r in sorted(rows,key=lambda x:x["digit"]):
                    n=r["components"][0]["id"];q=world(original,n)
                    p.require(n not in used and len(q.faces)==r["source_triangles"],"source group")
                    used.add(n);expected[n]=len(q.faces)
                    dst.add_geometry(q,node_name=n,geom_name=n)
                    inv.append({"id":r["source_id"],"names":[region.title()+" digit "+str(r["digit"])+" "+side.lower()+" — grouped mesh, individual phalanges unassigned"],"layer":key,"triangles":len(q.faces)})
                data=dst.export(file_type="glb");q=scene(data)
                for n in expected:
                    a,b=world(original,n),world(q,n)
                    p.require(a.faces.shape==b.faces.shape,"triangle count")
                    drift=max(drift,float(np.max(np.abs(a.vertices[a.faces]-b.vertices[b.faces]))))
                layers.append(model(out,key,side.title()+" "+region.lower()+" grouped digits",data,expected))
        p.require(used==set(original.graph.nodes_geometry) and sum(m["source_triangles"] for m in layers)==193768 and drift<=2e-6,"geometry conservation")
        print("DIGIT_LAYER_TRANSPORT_PASS",len(used),193768,drift,flush=True)
        return {"id":"digits","label":"Female CT grouped digits — anatomy hold","source":"BoneHub female CT, R229 connectivity diagnostic","scope":"20 original grouped digit meshes, not 56 independent phalanges. Mesh connectivity is not evidence of biological bone fusion. No segmentation, inferred identity or placement admission.","preview":write(out,"digits-preview.png",z.read("digit-components.png")),"attribution":write(out,"digits-attribution.txt",z.read("ATTRIBUTION.txt")),"inventory":write(out,"digits-inventory.json",js(inv)),"receipt":write(out,"digits-receipt.json",z.read("receipt.json")),"layers":layers,"source_archive_sha256":DIGITS}
def main(pack,pp,dd,out,archive):
    base=p.restore(pack,BASE,out)
    cat=p.parse((out/"catalog.json").read_bytes())
    p.require(len(cat["datasets"])==4 and sum(len(x["layers"]) for x in cat["datasets"])==32,"base catalog")
    cat["datasets"] += [pelvis(pp,out),digits(dd,out)]
    cat["source_pins"].update({"r228_pelvis":PELVIS,"r229_digits":DIGITS,"r229_display_pack":BASE})
    (out/"catalog.json").write_bytes(js(cat))
    entries=p.inventory(out)
    p.require(all(entries[n]==r for n,r in base.items() if n!="catalog.json"),"existing base asset changed")
    p.require(len(entries)==60 and sum(len(x["layers"]) for x in cat["datasets"])==37,"candidate inventory")
    sha=p.pack(out,archive)
    p.require(p.verify(archive,sha)==entries,"archive roundtrip")
    print("R230_EXTENSION_CANDIDATE",json.dumps({"sha256":sha,"assets":len(entries),"datasets":6,"models":37,"bytes":sum(x["bytes"] for x in entries.values()),"status":"BROWSER_CANDIDATE_NOT_DEPLOYED"}),flush=True)
if __name__=="__main__":main(*(Path(x) for x in sys.argv[1:]))
