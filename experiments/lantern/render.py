"""Generate original editable lantern geometry and render in native CPU Cycles."""
import bpy
import bmesh
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from mathutils import Vector

root = Path(__file__).resolve().parent
out = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
out.mkdir(parents=True, exist_ok=True)
spec_bytes = (root / "designs.json").read_bytes()
spec = json.loads(spec_bytes)
assert len(spec["profiles"]) == 2

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def material(name, color, metal=0, rough=0.36, emission=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metal
    shader.inputs["Roughness"].default_value = rough
    if emission:
        shader.inputs["Emission Color"].default_value = (*color, 1)
        shader.inputs["Emission Strength"].default_value = emission
    return mat

def cylinder(name, r, depth, z, mat, bevel=0.015):
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=r, depth=depth, location=(0, 0, z))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Rounded edge", "BEVEL")
        mod.width = bevel
        mod.segments = 3
    for p in obj.data.polygons:
        p.use_smooth = len(p.vertices) == 4
    return obj

def shade(profile, outer, inner):
    n, layers = 128, 33
    vertices = []
    for wall in (0, 1):
        for j in range(layers):
            t = j / (layers - 1)
            z = .67 + .97 * t
            for i in range(n):
                a = 2 * math.pi * i / n
                radius = .45 + .20 * math.sin(math.pi * t) + .06*t
                radius += profile["amplitude"] * math.sin(profile["lobes"]*a + profile["twist"]*t*2*math.pi)
                radius -= .035 * wall
                vertices.append((radius*math.cos(a), radius*math.sin(a), z))
    def ix(w,j,i): return w*layers*n+j*n+(i%n)
    faces, mi = [], []
    for w in (0, 1):
        for j in range(layers-1):
            for i in range(n):
                f = (ix(w,j,i),ix(w,j,i+1),ix(w,j+1,i+1),ix(w,j+1,i))
                faces.append(f if w==0 else f[::-1])
                mi.append(w)
    for j in (0,layers-1):
        for i in range(n):
            f = (ix(0,j,i),ix(1,j,i),ix(1,j,i+1),ix(0,j,i+1))
            faces.append(f if j==0 else f[::-1]); mi.append(1)
    mesh = bpy.data.meshes.new("Parametric double-wall shade")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Parametric ribbed shade", mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(outer); mesh.materials.append(inner)
    for p, idx in zip(mesh.polygons, mi):
        p.material_index=idx
        p.use_smooth=True
    bm=bmesh.new();bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    assert all(e.is_manifold for e in bm.edges), "shade must be closed manifold"
    volume=abs(bm.calc_volume(signed=True))
    assert volume>0
    bm.to_mesh(mesh);bm.free();mesh.update()
    geometry=hashlib.sha256(json.dumps([vertices,faces],separators=(",",":")).encode()).hexdigest()
    return obj, {"vertices":len(vertices),"faces":len(faces),"volume_m3":volume,"geometry_sha256":geometry}

def aim(obj, point):
    obj.rotation_euler=(Vector(point)-obj.location).to_track_quat("-Z","Y").to_euler()

def area_light(name, location, power, color, size, target):
    data=bpy.data.lights.new(name,"AREA");data.energy=power;data.color=color;data.shape="DISK";data.size=size
    obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=location;aim(obj,target)

def render(profile):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.unit_settings.system="METRIC"
    scene.render.engine="CYCLES"
    scene.cycles.device="CPU"
    scene.cycles.samples=32
    scene.cycles.seed=41
    scene.cycles.use_denoising=True
    scene.render.resolution_x=640;scene.render.resolution_y=480;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG";scene.render.image_settings.color_mode="RGB"
    scene.render.threads_mode="FIXED";scene.render.threads=2
    scene.world=bpy.data.worlds.new("Studio world")
    scene.world.use_nodes=True;scene.world.node_tree.nodes["Background"].inputs[0].default_value=(.18,.21,.27,1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value=.27
    scene.view_settings.view_transform="AgX"
    outer=material("Shade exterior",profile["color"],profile["metallic"],.26)
    inner=material("Warm brushed lining",(.68,.38,.12),.65,.36)
    brass=material("Brass accents",(.61,.36,.12),.78,.28)
    dark=material("Dark ceramic base",(.035,.043,.05),.2,.33)
    glow=material("Opal light", (1,.67,.3),0,.25,3.0)
    floor=material("Studio ground",(.17,.19,.22),0,.65)
    shade_obj, metrics=shade(profile,outer,inner)
    parts=[shade_obj,cylinder("Base",.42,.14,.07,dark,.028),
           cylinder("Brass foot",.35,.05,.162,brass,.01),
           cylinder("Stem",.065,.72,.545,brass,.008),
           cylinder("Socket",.14,.17,.915,brass,.012)]
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=.23,location=(0,0,1.14))
    bulb=bpy.context.object;bulb.name="Opal bulb";bulb.scale=(.82,.82,1.35)
    bulb.data.materials.append(glow)
    for p in bulb.data.polygons:p.use_smooth=True
    parts.append(bulb)
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.007))
    ground=bpy.context.object;ground.name="Studio ground";ground.data.materials.append(floor)
    point=bpy.data.lights.new("Warm bulb illumination","POINT");point.energy=38;point.color=(1,.64,.32);point.shadow_soft_size=.13
    po=bpy.data.objects.new("Warm bulb illumination",point);bpy.context.collection.objects.link(po);po.location=(0,0,1.16)
    area_light("Key",(-3.4,-4.0,5.2),590,(1,.87,.70),3.0,(0,0,.85))
    area_light("Fill",(3.2,-1.6,3.8),350,(.65,.81,1),2.6,(0,0,.9))
    area_light("Rim",(1.1,3.0,4.0),700,(1,.82,.56),2.0,(0,0,1.0))
    camdata=bpy.data.cameras.new("Product camera");camdata.type="ORTHO";camdata.ortho_scale=2.62
    cam=bpy.data.objects.new("Product camera",camdata);bpy.context.collection.objects.link(cam);scene.camera=cam
    cam.location=(3.2,-4.6,3.05);aim(cam,(0,0,.83))
    directory=out/profile["id"];directory.mkdir()
    scene.render.filepath=str(directory/"hero.png")
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(directory/"lantern.blend"))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:obj.select_set(True)
    bpy.context.view_layer.objects.active=shade_obj
    result=bpy.ops.export_scene.gltf(filepath=str(directory/"lantern.glb"),export_format="GLB",use_selection=True)
    assert "FINISHED" in result
    started=time.monotonic();bpy.ops.render.render(write_still=True);hero_time=time.monotonic()-started
    files=["hero.png","lantern.blend","lantern.glb"]
    times={"hero":round(hero_time,3)}
    if profile["id"]=="spiral":
        cam.location=(2.3,-2.6,4.5);aim(cam,(0,0,1.06));camdata.ortho_scale=2.20
        scene.render.filepath=str(directory/"detail.png")
        started=time.monotonic();bpy.ops.render.render(write_still=True);times["detail"]=round(time.monotonic()-started,3)
        files.append("detail.png")
    receipt={"scope":"Original procedural lantern design study; not a Foundry export",
             "profile":profile,"blender":bpy.app.version_string,"renderer":"Cycles CPU",
             "source_sha256":hashlib.sha256(spec_bytes).hexdigest(),
             "shade":metrics,"product_parts":[o.name for o in parts],
             "dimensions_px":[640,480],"render_seconds":times,
             "files":{f:{"sha256":sha(directory/f),"bytes":(directory/f).stat().st_size} for f in files}}
    (directory/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print("LANTERN_RENDER",json.dumps(receipt,sort_keys=True),flush=True)

for profile in spec["profiles"]:
    assert profile["id"] in ("ripple","spiral")
    assert 3<=profile["lobes"]<=16 and .01<=profile["amplitude"]<=.1
    render(profile)
