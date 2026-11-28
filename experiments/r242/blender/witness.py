"""Independent Blender import, pose, save/reopen and actual geometry rendering.
The evidence is consumer transport only. Anatomy, contact and completeness remain held.
"""
import hashlib, json, os, struct, sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

out = Path(sys.argv[sys.argv.index("--")+1])
meta = json.loads((out/"input.json").read_text()); sex = meta["sex"]
raw = (out/meta["model"]).read_bytes()
assert hashlib.sha256(raw).hexdigest() == meta["glb_sha256"]
magic, version, total = struct.unpack_from("<4sII", raw)
assert (magic, version, total) == (b"glTF", 2, len(raw))
n, kind = struct.unpack_from("<I4s", raw, 12)
assert kind == b"JSON"
doc = json.loads(raw[20:20+n])
size, kind = struct.unpack_from("<I4s", raw, 20+n)
assert kind == b"BIN\0" and len(raw) == 28+n+size
binary = raw[28+n:]

def read(index):
    a=doc["accessors"][index]; view=doc["bufferViews"][a["bufferView"]]
    assert "byteStride" not in view and "sparse" not in a
    width={"SCALAR":1,"VEC3":3,"VEC4":4,"MAT4":16}[a["type"]]
    dtype={5123:"<u2",5125:"<u4",5126:"<f4"}[a["componentType"]]
    return np.frombuffer(binary,dtype=dtype,count=a["count"]*width,
        offset=view.get("byteOffset",0)+a.get("byteOffset",0)).reshape(-1,width).copy()

parents={}
for i,node in enumerate(doc["nodes"]):
    for child in node.get("children",[]):
        assert child not in parents,"multiple parent nodes"
        parents[child]=i
anim=doc["animations"][0]; tracks={}
for channel in anim["channels"]:
    assert channel["target"]["path"]=="rotation","unsupported animation target"
    sampler=anim["samplers"][channel["sampler"]]
    assert sampler.get("interpolation","LINEAR")=="LINEAR"
    times=read(sampler["input"]).ravel()
    assert np.max(np.abs(times-[0,1,2]))<1e-6,"unexpected sample times"
    tracks[channel["target"]["node"]]=read(sampler["output"])

def world_at(key):
    cache={}
    def visit(i):
        if i in cache:return cache[i]
        node=doc["nodes"][i]
        if "matrix" in node:
            M=np.array(node["matrix"],float).reshape(4,4).T
        else:
            q=tracks[i][key] if i in tracks else node.get("rotation",[0,0,0,1])
            M=np.eye(4)
            q=np.array(q,dtype=float);q/=np.linalg.norm(q);x,y,z,w=q
            R=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                        [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                        [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
            M[:3,:3]=R@np.diag(node.get("scale",[1,1,1]))
            M[:3,3]=node.get("translation",[0,0,0])
        cache[i]=visit(parents[i])@M if i in parents else M
        return cache[i]
    return [visit(i) for i in range(len(doc["nodes"]))]

def xyz_to_blender(v):return v[:,[0,2,1]]*np.array([1,-1,1])
bone_nodes=[(i,n) for i,n in enumerate(doc["nodes"]) if n.get("name","").startswith(("BP3D_","CT_"))]
assert len(bone_nodes)==9 and len(doc["skins"][0]["joints"])==163
cpu=np.load(out/(sex+"-athletic-cpu-reference.npz"));frames=cpu["frames"]
assert frames.shape==(3,13380,3)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(out/meta["model"]))
scene=bpy.context.scene
skin=next(o for o in scene.objects if o.type=="MESH" and any(m.type=="ARMATURE" for m in o.modifiers))
rig=next(o for o in scene.objects if o.type=="ARMATURE")
assert len(rig.data.bones)==163
print("R242_IMPORTED_OBJECTS",json.dumps([{"name":o.name,"type":o.type,"data":getattr(o.data,"name",None),"vertices":len(o.data.vertices) if o.type=="MESH" else None,"parent":o.parent.name if o.parent else None,"parent_type":o.parent_type,"parent_bone":o.parent_bone} for o in scene.objects]),flush=True)
assert len([o for o in scene.objects if o.type=="MESH"])==10,"mesh inventory"
skin_name=skin.name
assert all(bpy.data.objects.get(n["name"]) is not None for _,n in bone_nodes),"named bone objects"
actions=list(bpy.data.actions);assert actions,"animation missing"
start=min(a.frame_range[0] for a in actions);end=max(a.frame_range[1] for a in actions)
assert end>start

def set_key(key):
    frame=start+(end-start)*key/2
    scene.frame_set(int(frame),subframe=frame-int(frame))
    return frame

def evaluated(obj):
    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
    points=np.empty(len(mesh.vertices)*3,dtype=np.float64);mesh.vertices.foreach_get("co",points)
    points=points.reshape(-1,3);M=np.array(ev.matrix_world)
    points=points@M[:3,:3].T+M[:3,3];faces=len(mesh.polygons)
    assert all(len(p.vertices)==3 for p in mesh.polygons),"non-triangle import"
    ev.to_mesh_clear()
    return points,faces

def point_error(a,b,limit):
    # Full point-cloud index; bounded deterministic queries do not assume
    # importer index or seam ordering.
    tree=KDTree(len(b))
    for j,p in enumerate(b):tree.insert(Vector(p),j)
    tree.balance()
    take=np.linspace(0,len(a)-1,min(limit,len(a)),dtype=int)
    return max(tree.find(Vector(a[j]))[2] for j in take)

def compare(a,b,limit):
    return {"max_bidirectional_vertex_error_m":max(point_error(a,b,limit),point_error(b,a,limit)),
      "max_bounds_error_m":float(np.max(np.abs(np.array([a.min(0),a.max(0)])-np.array([b.min(0),b.max(0)])))),
      "actual_vertices":len(a),"expected_vertices":len(b),"queries_per_direction":min(limit,len(a),len(b))}

def qualify(key,phase):
    frame=set_key(key);world=world_at(key)
    actual,faces=evaluated(bpy.data.objects[skin_name])
    skincheck=compare(actual,xyz_to_blender(frames[key]),max(len(actual),len(frames[key])))
    assert faces==len(cpu["faces"]),"skin triangle count changed"
    bones=[]
    for i,node in bone_nodes:
        primitive=doc["meshes"][node["mesh"]]["primitives"][0]
        local=read(primitive["attributes"]["POSITION"])
        expected=local@world[i][:3,:3].T+world[i][:3,3]
        actual,triangles=evaluated(bpy.data.objects[node["name"]])
        check=compare(actual,xyz_to_blender(expected),4096)
        assert triangles==len(read(primitive["indices"]))//3,"bone triangles changed: "+node["name"]
        check.update(name=node["name"],triangles=triangles);bones.append(check)
    worst=max([skincheck["max_bidirectional_vertex_error_m"],skincheck["max_bounds_error_m"]]+
      [v for bone in bones for k,v in bone.items() if k in ("max_bidirectional_vertex_error_m","max_bounds_error_m")])
    row={"phase":phase,"key":key,"frame":frame,"skin":skincheck,"bones":bones,"worst_error_m":worst}
    print("R242_BLENDER_KEY",json.dumps(row),flush=True)
    assert worst<2e-6,"consumer drift exceeds 2 micrometers"
    return row

checks=[qualify(k,"import") for k in (0,1,2)]
scene.render.engine="CYCLES";scene.cycles.device="CPU"
scene.cycles.samples=12;scene.cycles.use_denoising=True;scene.cycles.max_bounces=4;scene.cycles.transparent_max_bounces=12
scene.render.resolution_x=600;scene.render.resolution_y=840;scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"
scene.world=bpy.data.worlds.new("Neutral inspection world");scene.world.use_nodes=True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value=(.025,.04,.06,1)
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value=.5
scene.view_settings.view_transform="AgX"

def material(name,color,opacity=1):
    mat=bpy.data.materials.new(name);mat.use_nodes=True;nodes=mat.node_tree.nodes;nodes.clear()
    output=nodes.new("ShaderNodeOutputMaterial");surface=nodes.new("ShaderNodeBsdfPrincipled")
    surface.inputs["Base Color"].default_value=(*color,1);surface.inputs["Roughness"].default_value=.58
    if opacity==1:mat.node_tree.links.new(surface.outputs["BSDF"],output.inputs["Surface"])
    else:
        transparent=nodes.new("ShaderNodeBsdfTransparent");mix=nodes.new("ShaderNodeMixShader");mix.inputs[0].default_value=opacity
        mat.node_tree.links.new(transparent.outputs[0],mix.inputs[1]);mat.node_tree.links.new(surface.outputs[0],mix.inputs[2]);mat.node_tree.links.new(mix.outputs[0],output.inputs[0])
    mat.diffuse_color=(*color,opacity);return mat

opaque=material("Neutral clay exterior",(.34,.49,.60));shell=material("Inspection shell transparency",(.28,.58,.72),.13)
bone_materials=[material("Pelvic bone",(.80,.66,.42)),material("Long bone",(.88,.80,.61)),
                material("Sacrum",(.71,.47,.26)),material("Fibula",(.72,.83,.85))]
for _,n in bone_nodes:
    obj=bpy.data.objects[n["name"]];name=n["name"].upper()
    choice=2 if "SACRUM" in name or "FJ3393" in name else 3 if "FIBULA" in name or "FJ3260" in name or "FJ3366" in name else 0 if "HIP_" in name or "FJ3288" in name or "FJ3152" in name else 1
    obj.data.materials.clear();obj.data.materials.append(bone_materials[choice])
    for p in obj.data.polygons:p.use_smooth=True
for p in skin.data.polygons:p.use_smooth=True

def look(obj,point):obj.rotation_euler=(Vector(point)-obj.location).to_track_quat("-Z","Y").to_euler()
bpy.ops.object.camera_add(location=(2.4,-5.5,1.75))
cam=bpy.context.object;cam.name="Review camera";cam.data.type="ORTHO";scene.camera=cam
for loc,power,size in [((2.3,-3.5,3.6),550,3.5),((-2.6,-1.2,2.4),400,3),((1,3,2.8),650,3)]:
    bpy.ops.object.light_add(type="AREA",location=loc);obj=bpy.context.object
    obj.data.energy=power;obj.data.shape="DISK";obj.data.size=size;look(obj,(0,0,.85))

def render(name,key,mat,detail=False,front=False):
    set_key(key);skin.data.materials.clear();skin.data.materials.append(mat)
    vertices,_=evaluated(skin);center=(vertices.min(0)+vertices.max(0))/2
    if detail:center=np.array([0,0,.56]);cam.data.ortho_scale=1.27
    else:cam.data.ortho_scale=max(2.12,(vertices[:,2].max()-vertices[:,2].min())*1.13,(vertices[:,0].max()-vertices[:,0].min())*840/600*1.12)
    cam.location=center+np.array([0,-5,.12] if front else [2.1,-5,1.1]);look(cam,center)
    scene.render.filepath=str(out/name);bpy.ops.render.render(write_still=True)

render(sex+"-exterior-pose.png",1,opaque)
render(sex+"-anatomy-rest.png",0,shell,detail=True,front=True)
render(sex+"-anatomy-pose.png",1,shell,detail=True)
blend=out/(sex+"-integrated-consumer.blend")
bpy.ops.wm.save_as_mainfile(filepath=str(blend),compress=True)
assert blend.exists() and blend.stat().st_size>10000
bpy.ops.wm.open_mainfile(filepath=str(blend));scene=bpy.context.scene
checks.append(qualify(1,"saved-reopened"))
receipt={"status":"PASS_INDEPENDENT_BLENDER_CONSUMER","anatomical_admission":"HOLD","inputs":meta,
 "blender_version":bpy.app.version_string,"source_commit":os.environ.get("GITHUB_SHA"),
 "source_head_commit":os.environ.get("SOURCE_HEAD_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),
 "rig_bones":163,"anatomical_meshes":9,"skin_meshes":1,"checks":checks,
 "scope":"Exact candidate geometry and full-weight skin consumed by independent Blender 5.2.4. All skin vertices and up to 4096 bone vertices per direction queried against full point-cloud indices at three keys; full bounds and triangle counts checked. Saved .blend reopened at pose. Rigid parent motion, not tissue deformation, articular contact or native Oneirifact acceptance. Render lighting/material presentation only; source GLB byte-identical.",
 "files":{}}
for p in sorted(out.iterdir()):
    if p.is_file() and p.name!="blender-consumer-receipt.json":
        receipt["files"][p.name]={"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
(out/"blender-consumer-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
print("R242_BLENDER_COMPLETE",json.dumps({"status":receipt["status"],"sex":sex,"checks":len(checks),"worst_error_m":max(c["worst_error_m"] for c in checks),"blend_bytes":blend.stat().st_size}),flush=True)
