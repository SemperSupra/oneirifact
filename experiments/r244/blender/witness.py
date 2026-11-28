"""Actual static source-body consumer, render and saved-scene readback."""
import hashlib,json,os,struct,sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree
out=Path(sys.argv[sys.argv.index("--")+1])
manifest=json.loads((out/"source-assembly-manifest.json").read_text())
def sha(data):return hashlib.sha256(data).hexdigest()
def parse(raw):
    magic,version,total=struct.unpack_from("<4sII",raw);assert(magic,version,total)==(b"glTF",2,len(raw))
    n,kind=struct.unpack_from("<I4s",raw,12);assert kind==b"JSON"
    doc=json.loads(raw[20:20+n]);size,kind=struct.unpack_from("<I4s",raw,20+n)
    assert kind==b"BIN\0" and 28+n+size==len(raw)
    return doc,raw[28+n:]
def accessor(doc,binary,index):
    a=doc["accessors"][index];v=doc["bufferViews"][a["bufferView"]]
    assert "sparse" not in a and "byteStride" not in v
    width={"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4,"MAT4":16}[a["type"]]
    dtype={5121:"u1",5123:"<u2",5125:"<u4",5126:"<f4"}[a["componentType"]]
    return np.frombuffer(binary,dtype=dtype,count=a["count"]*width,offset=v.get("byteOffset",0)+a.get("byteOffset",0)).reshape(-1,width).copy()
def world_positions(raw):
    doc,binary=parse(raw);assert not doc.get("animations") and not doc.get("skins")
    parents={}
    for i,n in enumerate(doc["nodes"]):
        for child in n.get("children",[]):
            assert child not in parents;parents[child]=i
    cache={}
    def world(i):
        if i in cache:return cache[i]
        n=doc["nodes"][i]
        if "matrix" in n:M=np.array(n["matrix"],float).reshape(4,4).T
        else:
            q=np.array(n.get("rotation",[0,0,0,1]),float);q/=np.linalg.norm(q);x,y,z,w=q
            R=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
            M=np.eye(4);M[:3,:3]=R@np.diag(n.get("scale",[1,1,1]));M[:3,3]=n.get("translation",[0,0,0])
        cache[i]=world(parents[i])@M if i in parents else M
        return cache[i]
    result={}
    for i,n in enumerate(doc["nodes"]):
        if "mesh" not in n:continue
        primitives=doc["meshes"][n["mesh"]]["primitives"];assert len(primitives)==1
        p=primitives[0];assert p.get("mode",4)==4
        v=accessor(doc,binary,p["attributes"]["POSITION"]);M=world(i)
        faces=accessor(doc,binary,p["indices"]).reshape(-1,3)
        result[n["name"]]=(v@M[:3,:3].T+M[:3,3],faces)
    return result
expected={}
for filename,digest in manifest["reference_glb_sha256"].items():
    raw=(out/"references"/filename).read_bytes();assert sha(raw)==digest
    got=world_positions(raw);assert not set(got)&set(expected);expected.update(got)
combined=(out/"source-body-static.glb").read_bytes();assert sha(combined)==manifest["combined_glb_sha256"]
assert len(expected)==manifest["mesh_count"]==208
records={r["id"]:r for r in manifest["meshes"]};assert set(records)==set(expected)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(out/"source-body-static.glb"))
scene=bpy.context.scene
assert not bpy.data.actions and not any(o.type=="ARMATURE" for o in scene.objects),"static reference unexpectedly animated"
assert {o.name for o in scene.objects if o.type=="MESH"}==set(expected),"actual named source object inventory"

def evaluated(obj):
    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
    v=np.empty(len(mesh.vertices)*3,dtype=np.float64);mesh.vertices.foreach_get("co",v);v=v.reshape(-1,3)
    M=np.array(ev.matrix_world);v=v@M[:3,:3].T+M[:3,3]
    nf=len(mesh.polygons);assert all(len(p.vertices)==3 for p in mesh.polygons)
    ev.to_mesh_clear();return v,nf
def distance(a,b):
    tree=KDTree(len(b))
    for i,p in enumerate(b):tree.insert(Vector(p),i)
    tree.balance();take=np.linspace(0,len(a)-1,min(2048,len(a)),dtype=int)
    return max(tree.find(Vector(a[i]))[2] for i in take)
def qualify(phase):
    assert not bpy.data.actions and not any(o.type=="ARMATURE" for o in scene.objects)
    results=[]
    for ident,(v,faces) in expected.items():
        reference=v[:,[0,2,1]]*np.array([1,-1,1])
        actual,nf=evaluated(bpy.data.objects[ident])
        assert len(actual)==len(reference) and nf==len(faces),"source geometry count "+ident
        err=max(distance(actual,reference),distance(reference,actual))
        bounds=float(np.max(np.abs(np.array([actual.min(0),actual.max(0)])-np.array([reference.min(0),reference.max(0)]))))
        assert max(err,bounds)<2e-6,"source consumer geometry drift "+ident
        results.append({"id":ident,"vertices":len(actual),"triangles":nf,"queries_per_direction":min(len(v),2048),"max_bidirectional_vertex_error_m":err,"max_bounds_error_m":bounds})
    result={"phase":phase,"objects":len(results),"triangles":sum(r["triangles"] for r in results),"worst_error_m":max(max(r["max_bidirectional_vertex_error_m"],r["max_bounds_error_m"]) for r in results),"meshes":results}
    print("R244_BLENDER_CHECK",json.dumps({k:v for k,v in result.items() if k!="meshes"}),flush=True);return result
checks=[qualify("import")]
collections={}
for group in ("skin","skeletal","hair"):
    collection=bpy.data.collections.new("Source "+group);scene.collection.children.link(collection);collections[group]=collection
for ident,row in records.items():
    obj=bpy.data.objects[ident]
    for collection in list(obj.users_collection):collection.objects.unlink(obj)
    collections[row["group"]].objects.link(obj)
    obj["source_element_id"]=ident;obj["source_labels"]="; ".join(str(c[1]) for c in row["concepts"])
    obj["source_collection"]="BodyParts3D 4.0";obj["anatomical_acceptance"]="HOLD"
    for p in obj.data.polygons:p.use_smooth=True
scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=16;scene.cycles.use_denoising=True
scene.cycles.max_bounces=4;scene.cycles.transparent_max_bounces=12
scene.render.resolution_x=600;scene.render.resolution_y=920;scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"
scene.world=bpy.data.worlds.new("Source reference studio");scene.world.use_nodes=True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value=(.025,.04,.06,1)
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value=.5
scene.view_settings.view_transform="AgX"
def mat(name,color,opacity=1):
    material=bpy.data.materials.new(name);material.use_nodes=True
    nodes=material.node_tree.nodes;nodes.clear();output=nodes.new("ShaderNodeOutputMaterial")
    surface=nodes.new("ShaderNodeBsdfPrincipled");surface.inputs["Base Color"].default_value=(*color,1);surface.inputs["Roughness"].default_value=.62
    if opacity==1:material.node_tree.links.new(surface.outputs[0],output.inputs[0])
    else:
        transparent=nodes.new("ShaderNodeBsdfTransparent");mix=nodes.new("ShaderNodeMixShader");mix.inputs[0].default_value=opacity
        material.node_tree.links.new(transparent.outputs[0],mix.inputs[1]);material.node_tree.links.new(surface.outputs[0],mix.inputs[2]);material.node_tree.links.new(mix.outputs[0],output.inputs[0])
    material.diffuse_color=(*color,opacity);return material
opaque=mat("Source skin clay",(.36,.51,.61));transparent=mat("Open source skin inspection",(.29,.56,.69),.13)
bone=mat("Skeletal layer ivory",(.82,.74,.57));hair=mat("Source hair",(.12,.09,.06))
for ident,row in records.items():
    obj=bpy.data.objects[ident];obj.data.materials.clear()
    obj.data.materials.append({"skin":opaque,"skeletal":bone,"hair":hair}[row["group"]])
points=expected["FJ2810"][0];points=points[:,[0,2,1]]*np.array([1,-1,1])
lo,hi=points.min(0),points.max(0);center=(lo+hi)/2;height=hi[2]-lo[2]
def look(obj,point):obj.rotation_euler=(Vector(point)-obj.location).to_track_quat("-Z","Y").to_euler()
bpy.ops.object.camera_add(location=center+np.array([1.3,-5,.35]))
camera=bpy.context.object;camera.name="Static source review";camera.data.type="ORTHO";camera.data.ortho_scale=max(height*1.12,(hi[0]-lo[0])*920/600*1.15);look(camera,center);scene.camera=camera
for relative,power,size in [((2.3,-3.5,2.5),600,3.5),((-2.6,-1.2,1.3),420,3),((1,3,1.8),650,3)]:
    bpy.ops.object.light_add(type="AREA",location=center+np.array(relative));obj=bpy.context.object
    obj.data.energy=power;obj.data.shape="DISK";obj.data.size=size;look(obj,center)
def render(name,skin_visible,bones_visible,hair_visible,skin_material):
    for ident,row in records.items():
        obj=bpy.data.objects[ident];obj.hide_render=not {"skin":skin_visible,"skeletal":bones_visible,"hair":hair_visible}[row["group"]]
    obj=bpy.data.objects["FJ2810"];obj.data.materials.clear();obj.data.materials.append(skin_material)
    scene.render.filepath=str(out/name);bpy.ops.render.render(write_still=True)
render("source-skin.png",True,False,True,opaque)
render("source-skeletal-layer.png",False,True,False,opaque)
render("source-skin-skeletal-overlay.png",True,True,False,transparent)
for ident,row in records.items():bpy.data.objects[ident].hide_set(row["group"]=="hair")
blend=out/"source-body-static.blend";bpy.ops.wm.save_as_mainfile(filepath=str(blend),compress=True)
assert blend.exists() and blend.stat().st_size>10000
bpy.ops.wm.open_mainfile(filepath=str(blend));scene=bpy.context.scene
checks.append(qualify("saved-reopened"))
receipt={"status":"PASS_STATIC_BLENDER_CONSUMER","anatomical_acceptance":"HOLD","closed_envelope":"NOT_QUALIFIED_OPEN_SOURCE_SKIN","rig_or_animation":"NOT_PRESENT","single_biological_donor":"NOT_ESTABLISHED",
 "blender_version":bpy.app.version_string,"source_head_sha":os.environ.get("SOURCE_HEAD_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),
 "combined_glb_sha256":manifest["combined_glb_sha256"],"checks":checks,
 "scope":"Static unchanged source geometry. Import and saved-scene reopen compare full inventory/triangle counts/bounds and up to2048queryvertices per direction per named mesh against full source point clouds. Source skin remains open; no containment, anatomical completeness, joint behavior, rig or native Oneirifact qualification. Materials/lighting and visibility only.",
 "files":{}}
for path in sorted(out.rglob("*")):
    if path.is_file() and path.name!="blender-consumer-receipt.json":
        receipt["files"][path.relative_to(out).as_posix()]={"bytes":path.stat().st_size,"sha256":sha(path.read_bytes())}
(out/"blender-consumer-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
print("R244_BLENDER_COMPLETE",json.dumps({"status":receipt["status"],"objects":manifest["mesh_count"],"worst_error_m":max(c["worst_error_m"] for c in checks),"blend_bytes":blend.stat().st_size}),flush=True)
