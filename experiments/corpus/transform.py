"""Import an openly licensed GLB, fit a coarse primitive and deform a copy.
Standalone experiment: no private Foundry engine, no claim of scan origin.
"""
import bpy
from mathutils import Vector
import hashlib,json,math,struct,sys
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,m):
    if not ok:raise RuntimeError(m)
def bounds(points):
    return [min(p[i] for p in points) for i in range(3)],[max(p[i] for p in points) for i in range(3)]
def main():
    src,out,asset=sys.argv[sys.argv.index("--")+1:]
    src=Path(src);out=Path(out)
    require(asset in ("Avocado","Lantern","WaterBottle"),"unadmitted asset")
    require(tuple(bpy.app.version[:3])==(5,2,4),"Blender version")
    raw=src.read_bytes()
    require(20<len(raw)<=20<<20 and struct.unpack_from("<4sII",raw)==(b"glTF",2,len(raw)),"GLB header/budget")
    n,k=struct.unpack_from("<I4s",raw,12)
    require(k==b"JSON" and 20+n<=len(raw),"GLB JSON")
    doc=json.loads(raw[20:20+n])
    require(not any("uri" in x for key in ("buffers","images") for x in doc.get(key,[])),"external references")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(src))
    scene=bpy.context.scene
    objects=[o for o in scene.objects if o.type=="MESH"]
    require(0<len(objects)<=100 and sum(len(o.data.vertices) for o in objects)<=500000,"mesh budget")
    # Preserve the imported scene separately; only derived copies are transformed.
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/"imported.blend"))
    points=[o.matrix_world@v.co for o in objects for v in o.data.vertices]
    lo,hi=bounds(points);size=[b-a for a,b in zip(lo,hi)]
    center=Vector([(a+b)/2 for a,b in zip(lo,hi)])
    scale=max(size);require(scale>1e-9,"degenerate source")
    normalized=[(p-center)/scale for p in points]
    half=[v/(2*scale) for v in size]
    axis=max(range(3),key=lambda i:size[i]);radial=[i for i in range(3) if i!=axis]
    def box(p):
        q=[abs(p[i])-half[i] for i in range(3)]
        return abs(min(max(q),0)+math.sqrt(sum(max(x,0)**2 for x in q)))
    def cylinder(p):
        a=math.hypot(*(p[i] for i in radial))-sum(half[i] for i in radial)/2
        b=abs(p[axis])-half[axis]
        return abs(min(max(a,b),0)+math.hypot(max(a,0),max(b,0)))
    # An explicit coarse baseline, vertex-weighted and one-way; not full inverse CAD.
    scores={k:math.sqrt(sum(fn(p)**2 for p in normalized)/len(normalized)) for k,fn in (("box",box),("cylinder",cylinder))}
    best=min(scores,key=scores.get)
    candidate={"schema":"external-primitive-proposal/v1","kind":best,"source_center":list(center),"source_dimensions":size,"axis":axis,"normalized_rmse":scores,"admission":"COARSE_ONLY" if scores[best]<.05 else "REJECTED","limitations":"vertex-weighted one-way residual, no topology or semantic feature recovery"}
    (out/"primitive-proposal.json").write_text(json.dumps(candidate,indent=2)+"\n")
    # Flatten copies into normalized world coordinates. Keep mesh materials and UVs.
    originals=[];derived=[];changed=0
    for o in objects:
        for variant,target in (("original",originals),("deformed",derived)):
            obj=bpy.data.objects.new(variant+"-"+o.name,o.data.copy())
            scene.collection.objects.link(obj)
            for v in obj.data.vertices:
                p=(o.matrix_world@v.co-center)/scale
                if variant=="deformed":
                    z=p[2];theta=1.1*z
                    x,y=p.x,p.y
                    p.x=(math.cos(theta)*x-math.sin(theta)*y)*(1+.5*z)
                    p.y=(math.sin(theta)*x+math.cos(theta)*y)*(1+.5*z)
                    p.z*=1.3
                    changed+=1
                v.co=p
            obj.data.update();target.append(obj)
    for o in list(scene.objects):
        if o not in originals and o not in derived:bpy.data.objects.remove(o,do_unlink=True)
    require(changed==len(points),"vertex count mismatch")
    # Export each geometry set independently with unchanged UV/material data.
    for name,group in (("normalized",originals),("deformed",derived)):
        bpy.ops.object.select_all(action="DESELECT")
        for o in group:o.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(out/(name+".glb")),export_format="GLB",use_selection=True)
    # Render side by side with same camera and lights, including original textures.
    for group,offset in ((originals,-.7),(derived,.7)):
        for o in group:o.location.x=offset
    scene.world=bpy.data.worlds.new("studio");scene.world.use_nodes=True
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value=.5
    for pos,power,size in (((-3,-4,5),650,4),((3,1,4),750,3)):
        d=bpy.data.lights.new("softbox","AREA");d.energy=power;d.size=size
        o=bpy.data.objects.new("softbox",d);scene.collection.objects.link(o);o.location=pos;o.rotation_euler=(-o.location).to_track_quat("-Z","Y").to_euler()
    d=bpy.data.cameras.new("camera");o=bpy.data.objects.new("camera",d);scene.collection.objects.link(o)
    o.location=(2,-5,2);o.rotation_euler=(-o.location).to_track_quat("-Z","Y").to_euler()
    d.type="ORTHO";d.ortho_scale=3.2;scene.camera=o
    scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=24;scene.cycles.seed=199
    scene.render.resolution_x=840;scene.render.resolution_y=480;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG";scene.render.filepath=str(out/"comparison.png")
    bpy.ops.render.render(write_still=True)
    scene.render.filepath="//comparison.png";bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/"comparison.blend"))
    receipt={"schema":"public-external-mesh-study/v1","asset":asset,"license":"CC0-1.0","source_sha256":sha(src),"vertices":len(points),"mesh_objects":len(objects),"deformed_vertices_processed":changed,"transform":"normalized world coordinates, twist 1.1*z, taper 1+0.5*z, z scale 1.3","primitive":candidate,"files":{p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()}}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt))
if __name__=="__main__":main()
