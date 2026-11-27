"""Original conceptual bearing visualization; not a dimensioned engineering design."""
import bpy
from mathutils import Vector
import hashlib
import json
import math
from pathlib import Path
import sys

def material(name,color,metal,rough):
    m=bpy.data.materials.new(name)
    m.diffuse_color=(*color,1)
    m.use_nodes=True
    bsdf=m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value=(*color,1)
    bsdf.inputs["Metallic"].default_value=metal
    bsdf.inputs["Roughness"].default_value=rough
    return m

def annulus(name,inner,outer,depth,z,mat):
    n=128
    vertices=[(r*math.cos(2*math.pi*i/n),r*math.sin(2*math.pi*i/n),z+dz)
              for dz in (-depth/2,depth/2) for r in (inner,outer) for i in range(n)]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces.extend([(i,j,n+j,n+i),(2*n+i,3*n+i,3*n+j,2*n+j),
                      (i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)])
    # Reverse all faces: above bottom face is clockwise in radius ordering?
    # Recalculate consistent outward orientation for the closed manifold.
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    import bmesh
    bm=bmesh.new();bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
    if bm.calc_volume(signed=True)<0:bmesh.ops.reverse_faces(bm,faces=bm.faces)
    bm.to_mesh(mesh);bm.free()
    obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    bevel=obj.modifiers.new("edge highlights","BEVEL");bevel.width=.045;bevel.segments=3
    obj.modifiers.new("weighted normals","WEIGHTED_NORMAL")
    return obj

def ball(name,pos,mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=20,radius=.37,location=pos)
    obj=bpy.context.object;obj.name=name;obj.data.materials.append(mat)
    for f in obj.data.polygons:f.use_smooth=True
    return obj

def light(name,pos,power,size):
    data=bpy.data.lights.new(name,"AREA");data.energy=power;data.shape="DISK";data.size=size
    obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj)
    obj.location=pos;obj.rotation_euler=(Vector((0,0,1))-obj.location).to_track_quat("-Z","Y").to_euler()

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    args=sys.argv[sys.argv.index("--")+1:]
    if len(args)!=2 or args[0] not in ("assembled","exploded"):raise SystemExit("PROFILE OUTPUT")
    profile=args[0];out=Path(args[1]).resolve(strict=True)
    if not out.is_dir() or any((out/(profile+s)).exists() for s in (".png",".blend",".glb",".json")):raise RuntimeError("output custody")
    if tuple(bpy.app.version[:3])!=(5,2,4):raise RuntimeError("pinned Blender required")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    steel=material("brushed steel",(.55,.61,.69),.85,.24)
    chrome=material("polished rolling element",(.72,.78,.82),.95,.14)
    bronze=material("bronze retainer",(.58,.29,.10),.72,.31)
    floor=material("charcoal presentation ground",(.035,.05,.07),.05,.8)
    exploded=profile=="exploded"
    # This study intentionally shows separately named component occurrences.
    # Clearances, loads, wear, tolerances and manufacturing fit are not validated.
    parts=[annulus("outer race",2.04,2.52,.66,0 if exploded else .35,steel),
           annulus("inner race",1.06,1.33,.66,1.85 if exploded else .35,steel),
           annulus("lower retainer",1.38,1.99,.09,.55 if exploded else .11,bronze),
           annulus("upper retainer",1.38,1.99,.09,2.65 if exploded else .59,bronze)]
    for i in range(10):
        angle=2*math.pi*i/10
        parts.append(ball(f"rolling element {i:02}",(1.68*math.cos(angle),1.68*math.sin(angle),1.2 if exploded else .35),chrome))
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.39))
    ground=bpy.context.object;ground.name="evaluation ground";ground.data.materials.append(floor)
    scene.world=bpy.data.worlds.new("studio");scene.world.use_nodes=True
    bg=scene.world.node_tree.nodes.get("Background");bg.inputs["Color"].default_value=(.22,.28,.38,1);bg.inputs["Strength"].default_value=.5
    light("large key",(-5,-5,7),1100,5);light("rim",(4,3,6),1250,4);light("fill",(4,-5,3),450,3)
    camera_data=bpy.data.cameras.new("study camera");camera=bpy.data.objects.new("study camera",camera_data);scene.collection.objects.link(camera)
    camera.location=(8,-10,7.4);camera.rotation_euler=(Vector((0,0,1 if exploded else .25))-camera.location).to_track_quat("-Z","Y").to_euler()
    camera_data.type="ORTHO";camera_data.ortho_scale=7.7;scene.camera=camera
    scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=32;scene.cycles.seed=197
    scene.render.resolution_x=720;scene.render.resolution_y=480;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG";scene.render.filepath=str(out/(profile+".png"))
    bpy.ops.render.render(write_still=True)
    scene.render.filepath="//"+profile+".png"
    bpy.ops.wm.save_as_mainfile(filepath=str(out/(profile+".blend")))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(out/(profile+".glb")),export_format="GLB",use_selection=True)
    receipt={"schema":"public-bearing-study/v1","profile":profile,"source_sha256":sha(Path(__file__)),"engine":"CYCLES","device":"CPU","blender":bpy.app.version_string,"resolution":[720,480],"samples":32,"seed":197,"component_ids":sorted(obj.name for obj in parts),"files":{s:sha(out/(profile+s)) for s in (".png",".blend",".glb")},"limits":"Conceptual illustration, not a validated bearing design or private product engine output"}
    (out/(profile+".json")).write_text(json.dumps(receipt,indent=2)+"\n")
    print("ACTUAL_BEARING_RENDER",json.dumps(receipt))
if __name__=="__main__":main()
