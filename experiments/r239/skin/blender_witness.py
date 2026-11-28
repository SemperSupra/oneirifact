"""Independent actual Blender glTF consumer; retain explicit hold if importer loses weights."""
import bpy,sys,json,hashlib
from pathlib import Path
import numpy as np
from mathutils import Vector
root=Path(sys.argv[sys.argv.index("--")+1])
rows=[]
for sex in ("male","female"):
    name=sex+"-athletic"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(root/(name+"-animated.glb")))
    mesh=next(x for x in bpy.context.scene.objects if x.type=="MESH")
    rig=next(x for x in bpy.context.scene.objects if x.type=="ARMATURE")
    scene=bpy.context.scene
    ref=np.load(root/(name+"-cpu-reference.npz"));frames=ref["frames"]
    actions=list(bpy.data.actions)
    assert len(actions)>=1,"animation missing"
    frame_start=min(a.frame_range[0] for a in actions);frame_end=max(a.frame_range[1] for a in actions)
    assert frame_end>frame_start,"empty action"
    measurements=[]
    for i,t in enumerate([0,.5,1]):
        frame=frame_start+(frame_end-frame_start)*t
        scene.frame_set(int(frame),subframe=frame-int(frame))
        dg=bpy.context.evaluated_depsgraph_get();ev=mesh.evaluated_get(dg);tmp=ev.to_mesh()
        actual=np.array([tuple(ev.matrix_world@v.co) for v in tmp.vertices]);ev.to_mesh_clear()
        # glTF Y-up -> Blender Z-up: x,-z,y. Compare point clouds in both
        # directions, using KDTree, because importer can split seam vertices.
        expected=frames[i][:,[0,2,1]]*np.array([1,-1,1])
        from mathutils.kdtree import KDTree
        def maxdist(a,b):
            k=KDTree(len(b))
            for j,p in enumerate(b):k.insert(Vector(p),j)
            k.balance();return max(k.find(Vector(p))[2] for p in a)
        err=max(maxdist(actual,expected),maxdist(expected,actual))
        measurements.append({"key":i,"frame":frame,"max_bidirectional_vertex_error_m":err,"evaluated_vertices":len(actual)})
    status="PASS_NATIVE_CONSUMER" if len(rig.data.bones)==163 and max(x["max_bidirectional_vertex_error_m"] for x in measurements)<.0001 else "HOLD_NATIVE_WEIGHT_OR_ANIMATION_TRANSPORT"
    rows.append({"id":name,"bones":len(rig.data.bones),"actions":len(actions),"samples":measurements,"status":status})
    # Actual surface render of imported posed mesh. Neutral clay, whole-body
    # orthographic inspection; no anatomical or photoreal material claim.
    scene.frame_set(int((frame_start+frame_end)/2))
    scene.render.engine="BLENDER_EEVEE";scene.render.resolution_x=660;scene.render.resolution_y=780;scene.render.resolution_percentage=100
    scene.world=bpy.data.worlds.new("inspection-world");scene.world.color=(.18,.18,.18)
    def look(obj,point):obj.rotation_euler=(Vector(point)-obj.location).to_track_quat("-Z","Y").to_euler()
    bpy.ops.object.camera_add(location=(2.5,-4,1.6));cam=bpy.context.object;look(cam,(0,0,.83));cam.data.type="ORTHO";cam.data.ortho_scale=2.08;scene.camera=cam
    for loc,power,size in [((2,-3,3),650,4),((-2,-1,2),420,3),((0,3,2),550,3)]:
        bpy.ops.object.light_add(type="AREA",location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape="DISK";o.data.size=size;look(o,(0,0,.9))
    scene.render.filepath=str(root/(name+"-actual-blender-pose.png"));bpy.ops.render.render(write_still=True)
(root/"blender-consumer-receipt.json").write_text(json.dumps(rows,indent=2)+"\n")
print("R239_BLENDER_CONSUMER",json.dumps(rows),flush=True)
