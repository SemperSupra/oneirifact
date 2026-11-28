"""Build a static source-frame body reference without fitting or mesh repair."""
import hashlib,io,json,os,sys,zipfile
from pathlib import Path
import numpy as np
import trimesh
ATLAS="18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9"
EXTERIOR="6a02936df3e0e40616efc62315961372eddc833ded773b7b5be004cb06e4ae65"
EXPECTED={"FJ2810":("skin",102467,203382),"FJ2813":("hair of head",12464,18006),"FJ2815":("pubic hair",5523,2960)}
def sha(data):return hashlib.sha256(data).hexdigest()
def need(ok,message):
    if not ok:raise ValueError(message)
def main(atlas,exterior,out):
    need(sha(atlas.read_bytes())==ATLAS and sha(exterior.read_bytes())==EXTERIOR,"exact input archives")
    out.mkdir(parents=True,exist_ok=False);refs=out/"references";refs.mkdir()
    combined=trimesh.Scene(base_frame="source-world");records=[];source_geometry={}
    with zipfile.ZipFile(atlas) as az,zipfile.ZipFile(exterior) as ez:
        need(az.testzip() is None and ez.testzip() is None,"archive CRC")
        ar=json.loads(az.read("receipt.json"));er=json.loads(ez.read("receipt.json"))
        invraw=az.read("inventory.json");need(sha(invraw)==ar["files"]["inventory.json"]["sha256"],"inventory SHA")
        inventory={r["id"]:r for r in json.loads(invraw)}
        need(len(inventory)==2234,"full source inventory")
        selected={i:r for i,r in inventory.items() if r["category"]=="skeletal"}
        need(len(selected)==205,"frozen heuristic skeletal layer inventory")
        candidate_index={r["id"]:r for r in er["candidates"]}
        need(set(candidate_index)==set(EXPECTED),"frozen actual exterior candidate inventory")
        need(er["anatomical_acceptance"]=="HOLD","retain upstream admission")
        need(candidate_index["FJ2810"]["boundary_edges"]==1512 and candidate_index["FJ2810"]["face_components"]==100 and not candidate_index["FJ2810"]["watertight_unmodified"],"preserve open source skin evidence")
        skinbytes=ez.read("source-exterior-candidates.glb")
        need(sha(skinbytes)==er["files"]["source-exterior-candidates.glb"]["sha256"],"source exterior GLB SHA")
        bonebytes=az.read("layers/skeletal.glb")
        need(sha(bonebytes)==ar["files"]["layers/skeletal.glb"]["sha256"],"source skeletal GLB SHA")
        refs.joinpath("source-skeletal.glb").write_bytes(bonebytes);refs.joinpath("source-exterior.glb").write_bytes(skinbytes)
        for kind,raw,rows in (("skeletal",bonebytes,selected),("exterior",skinbytes,{i:inventory[i] for i in EXPECTED})):
            scene=trimesh.load(io.BytesIO(raw),file_type="glb",force="scene",process=False)
            need(set(scene.graph.nodes_geometry)==set(rows),"exact source node identity "+kind)
            for ident,row in sorted(rows.items()):
                matrix,g=scene.graph[ident];mesh=scene.geometry[g].copy()
                need(len(mesh.vertices)==row["vertices"] and len(mesh.faces)==row["triangles"],"source topology "+ident)
                points=mesh.vertices@matrix[:3,:3].T+matrix[:3,3]
                need(np.max(np.abs(np.array([points.min(0),points.max(0)])-row["bounds_m"]))<2e-6,"source bounds "+ident)
                if ident in EXPECTED:
                    label,nv,nf=EXPECTED[ident]
                    need(label in [str(c[1]).lower() for c in row["concepts"]] and (len(mesh.vertices),len(mesh.faces))==(nv,nf),"actual exterior identity "+ident)
                group="skin" if ident=="FJ2810" else "hair" if ident in EXPECTED else "skeletal"
                color={"skin":[.48,.62,.70,1],"hair":[.16,.12,.09,1],"skeletal":[.87,.81,.67,1]}[group]
                mesh.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name=group,baseColorFactor=color,metallicFactor=0,roughnessFactor=.8,doubleSided=True))
                combined.add_geometry(mesh,node_name=ident,geom_name=ident,transform=matrix)
                source_geometry[ident]=(points,mesh.faces.copy())
                records.append({"id":ident,"group":group,"concepts":row["concepts"],"vertices":len(mesh.vertices),"triangles":len(mesh.faces),"source_bounds_m":row["bounds_m"],"original_obj_sha256":row["source_sha256"],"source_layer":kind})
        for name in ("LICENSE-source.html","LICENSE-update.html"):
            out.joinpath(name).write_bytes(az.read(name))
        out.joinpath("ATTRIBUTION.txt").write_bytes(az.read("ATTRIBUTION.txt")+b"\nR244 changes: presentation material, static source-frame assembly and independent Blender consumer. Actual original geometry, IDs and source transforms retained; no fitting, hole closure, remeshing or rig. Same-source collection does not establish one biological donor.\n")
        out.joinpath("input-exterior-receipt.json").write_text(json.dumps(er,indent=2)+"\n")
    packed=combined.export(file_type="glb");out.joinpath("source-body-static.glb").write_bytes(packed)
    decoded=trimesh.load(io.BytesIO(packed),file_type="glb",force="scene",process=False)
    need(set(decoded.graph.nodes_geometry)==set(source_geometry),"combined node identity")
    worst=0.
    for ident,(expected,faces) in source_geometry.items():
        matrix,g=decoded.graph[ident];mesh=decoded.geometry[g]
        actual=mesh.vertices@matrix[:3,:3].T+matrix[:3,3]
        need(np.array_equal(mesh.faces,faces) and actual.shape==expected.shape,"full source topology preservation "+ident)
        err=float(np.max(np.linalg.norm(actual-expected,axis=1)));need(err<2e-6,"full source coordinate transport "+ident);worst=max(worst,err)
    manifest={"status":"STATIC_SOURCE_REFERENCE_ONLY","anatomical_acceptance":"HOLD","rig_or_animation":"NOT_PRESENT",
      "source_collection":"BodyParts3D 4.0 99%-reduced official collection","single_biological_donor":"NOT_ESTABLISHED",
      "input_archive_sha256":{"atlas":ATLAS,"exterior":EXTERIOR},
      "reference_glb_sha256":{"source-skeletal.glb":sha(bonebytes),"source-exterior.glb":sha(skinbytes)},
      "combined_glb_sha256":sha(packed),"meshes":records,"mesh_count":len(records),"skeletal_mesh_count":len(selected),
      "triangles":sum(r["triangles"] for r in records),"full_vertex_export_max_error_m":worst,
      "skin_topology":{"id":"FJ2810","boundary_edges":1512,"face_components":100,"watertight":False,"containment":"ABSTAIN"},
      "scope":"Static same-source coordinate assembly only. All source vertices, triangles, per-object transforms and IDs retained within float32 transport. Hair remains two separate source objects. No anatomical completeness, closed envelope, contact, rig, animation or native Oneirifact acceptance.",
      "execution_head":os.environ.get("SOURCE_HEAD_SHA")}
    out.joinpath("source-assembly-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("R244_SOURCE_ASSEMBLY",json.dumps({k:v for k,v in manifest.items() if k!="meshes"}),flush=True)
if __name__=="__main__":main(*(Path(s) for s in sys.argv[1:]))
