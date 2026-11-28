"""Actual barefoot aquatic Blender consumer. Observations use evaluated geometry/FK.

Authored kinematic prototypes only. Separate two-link controls preserve original
MakeHuman intermediate bones, source rest binds and every skin influence.
"""
import copy, hashlib, json, math, os, sys, time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.kdtree import KDTree

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent/"motion"))
from gltf import parse,read,add,encode,sha,worlds


OUT=Path(sys.argv[sys.argv.index("--")+1]);QUICK="--quick" in sys.argv
CASE=json.loads((OUT/"case.json").read_text());MORPH=CASE["morphology"]
AQUATIC_INPUT=json.loads((OUT/"aquatic-inputs.json").read_text())
SHOE=AQUATIC_INPUT["footwear"];MEASURED=AQUATIC_INPUT["limb_measurements"]
AQUATIC={name:json.loads((OUT/(name+"-clip.json")).read_text()) for name in ("swimming_front_crawl","bathing_seated_wash")}
CHEST_ID=MEASURED["chest_source_vertex_id"]
DOC,BIN=parse((OUT/"bound-source.glb").read_bytes());SOURCE_WORLD,PARENTS=worlds(DOC)
NAMES=[n["name"] for n in DOC["nodes"][:163]];INDEX={n:i for i,n in enumerate(NAMES)}
C=Matrix(((1,0,0,0),(0,0,-1,0),(0,1,0,0),(0,0,0,1)));CI=C.inverted()
def bv(p):return Vector((p[0],-p[2],p[1]))
def cv(p):return [float(p[0]),float(p[2]),float(-p[1])]
def quat_xyzw(q):return [float(q.x),float(q.y),float(q.z),float(q.w)]
def qmat(q):return Quaternion((q[3],q[0],q[1],q[2])).to_matrix().to_4x4()
def bm(q):return C@qmat(q)@CI
def tup(p):return tuple(float(x) for x in p)
def save_json(p,value):p.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")
def update():bpy.context.view_layer.update()
def log(tag,x):print("R246_"+tag,json.dumps(x,allow_nan=False),flush=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(OUT/"bound-source.glb"))
scene=bpy.context.scene;scene.render.fps=24
rig=next(o for o in scene.objects if o.type=="ARMATURE")
skin=next(o for o in scene.objects if o.type=="MESH" and any(m.type=="ARMATURE" for m in o.modifiers))
assert len(rig.data.bones)==163 and set(rig.data.bones.keys())==set(NAMES)
assert len(skin.data.vertices)==CASE["body_mesh_vertices"] and len(skin.data.polygons)==CASE["body_mesh_triangles"]
custom_shapes={p.custom_shape for p in rig.pose.bones if p.custom_shape}
for obj in custom_shapes:obj.hide_render=True;obj.hide_set(True)
assert {o for o in scene.objects if o.type=="MESH"}==custom_shapes|{skin}
for p in rig.pose.bones:p.rotation_mode="QUATERNION"
REST={n:rig.matrix_world@rig.data.bones[n].matrix_local for n in NAMES}
REST_INV={n:m.inverted() for n,m in REST.items()}
RIG_INV=rig.matrix_world.inverted()
def world(n):return rig.matrix_world@rig.pose.bones[n].matrix
def position(n):return world(n).translation.copy()
def pose(n,m):rig.pose.bones[n].matrix=RIG_INV@m
def evaluated(obj):
    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
    a=np.empty(len(mesh.vertices)*3);mesh.vertices.foreach_get("co",a);a=a.reshape(-1,3)
    W=np.array(ev.matrix_world);a=a@W[:3,:3].T+W[:3,3];ev.to_mesh_clear();return a
def nearest_error(a,b,limit=1024):
    def one(a,b):
        tree=KDTree(len(b))
        for i,p in enumerate(b):tree.insert(Vector(p),i)
        tree.balance();ids=np.linspace(0,len(a)-1,min(limit,len(a)),dtype=int)
        return max(tree.find(Vector(a[i]))[2] for i in ids)
    return max(one(a,b),one(b,a))
attrs=DOC["meshes"][0]["primitives"][0]["attributes"]
source_vertices=read(DOC,BIN,attrs["POSITION"])
source_indices=np.concatenate([read(DOC,BIN,attrs["JOINTS_"+str(i)]) for i in range(3)],axis=1)
source_weights=np.concatenate([read(DOC,BIN,attrs["WEIGHTS_"+str(i)]) for i in range(3)],axis=1)
inverse_bind=read(DOC,BIN,DOC["skins"][0]["inverseBindMatrices"]).reshape(-1,4,4).transpose(0,2,1)
source_blender=source_vertices[:,[0,2,1]]*np.array([1,-1,1])
rest_skin_error=nearest_error(evaluated(skin),source_blender,len(source_blender))
assert rest_skin_error<5e-6
log("IMPORT",{"case":CASE["id"],"bones":len(NAMES),"skin_vertices":len(skin.data.vertices),"rest_skin_error_m":rest_skin_error,"version":bpy.app.version_string})

def make_chain(label,a,b,c):
    data=bpy.data.armatures.new(label);obj=bpy.data.objects.new(label,data);scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.mode_set(mode="EDIT")
    first=data.edit_bones.new("proximal");first.head=a;first.tail=b
    second=data.edit_bones.new("distal");second.head=b;second.tail=c;second.parent=first;second.use_connect=True
    bpy.ops.object.mode_set(mode="OBJECT");obj.select_set(False);obj.hide_render=True;obj.show_in_front=True
    target=bpy.data.objects.new(label+" target",None);pole=bpy.data.objects.new(label+" pole",None)
    scene.collection.objects.link(target);scene.collection.objects.link(pole);target.location=c
    for empty in (target,pole):empty.empty_display_type="SPHERE";empty.empty_display_size=.018
    v=(c-a).normalized();normal=b-a-v*((b-a).dot(v))
    if normal.length<1e-6:normal=Vector((0,-1,0))
    normal.normalize();pole.location=b+normal*.7
    ik=obj.pose.bones["distal"].constraints.new("IK");ik.target=target;ik.pole_target=pole
    ik.chain_count=2;ik.use_tail=True;ik.use_stretch=False;ik.iterations=200
    for pb in obj.pose.bones:pb.ik_stretch=0
    def err(angle):
        ik.pole_angle=angle;update();return (obj.pose.bones["distal"].head-b).length
    candidates=[(-math.pi+i*math.pi/8) for i in range(16)]
    angle=min(candidates,key=err)
    for width in (math.pi/8,math.pi/64,math.pi/512):angle=min([angle+width*(i-4)/4 for i in range(9)],key=err)
    residual=err(angle)
    return {"obj":obj,"target":target,"pole":pole,"ik":ik,
            "rest":{n:data.bones[n].matrix_local.copy() for n in ("proximal","distal")},
            "calibration":{"pole_angle_rad":angle,"rest_middle_joint_error_m":residual,"method":"Bounded native IK rest-plane angle calibration; no animation fitting."}}

controls={};calibration={}
for side in ("L","R"):
    for part,joints in (("leg",("upperleg01","lowerleg01","foot")),("arm",("upperarm01","lowerarm01","wrist"))):
        points=[REST[n+"."+side].translation for n in joints]
        controls[(part,side)]=make_chain("IK "+part+" "+side,*points)
        calibration[part+"."+side]=controls[(part,side)]["calibration"]
update()

def material(name,color,rough=.55):
    m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=(*color,1)
    p=m.node_tree.nodes.get("Principled BSDF");p.inputs["Base Color"].default_value=(*color,1);p.inputs["Roughness"].default_value=rough;return m
bodymat=material("Untextured source exterior",(.21,.48,.56) if CASE["sex_variant"]=="male" else (.61,.37,.28))
skin.data.materials.clear();skin.data.materials.append(bodymat)
for p in skin.data.polygons:p.use_smooth=True

def make_mesh(name,verts,faces,mat):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);scene.collection.objects.link(obj);obj.data.materials.append(mat);return obj
def add_box(verts,faces,center,width,length,height,transform=Matrix.Identity(4)):
    start=len(verts);center=Vector(center)
    for dy in (0,height):
        for dx,dz in ((-width/2,-length/2),(width/2,-length/2),(width/2,length/2),(-width/2,length/2)):
            verts.append(tup(transform@(center+Vector((dx,dy,dz)))))
    faces.extend(tuple(start+j for j in ids) for ids in ((0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)))
    return list(range(start,start+4))
def bone_parent(obj,name,verify_bind=True):
    # Blender bone parenting references the bone tail. Preserve world rest geometry.
    obj.parent=rig;obj.parent_type="BONE";obj.parent_bone=name
    parent=REST[name]@Matrix.Translation((0,rig.data.bones[name].length,0))
    obj.matrix_parent_inverse=parent.inverted();obj.matrix_basis=Matrix.Identity(4);update()
    if verify_bind:assert np.max(np.abs(np.array(obj.matrix_world)-np.eye(4)))<2e-5,"bone parent bind mismatch"

marker_import_guards=[]
def refresh_markers():
    assert len(skin.data.vertices)==len(source_blender),"source vertex count changed"
    coords=np.empty(len(skin.data.vertices)*3);skin.data.vertices.foreach_get("co",coords)
    source_index_error=float(np.max(np.linalg.norm(coords.reshape(-1,3)-source_blender,axis=1)))
    assert source_index_error<2e-6,"source vertex order or coordinates changed"
    expected=bv(MEASURED["chest_surface_anchor_m"])
    error=(skin.data.vertices[CHEST_ID].co-expected).length
    assert error<2e-6,"actual source chest-vertex identity changed"
    marker_import_guards.append({"kind":"all_source_vertices_and_chest","source_vertex_id":CHEST_ID,"rest_local_error_m":error,"all_vertex_index_error_m":source_index_error})
def marker(side,region):
    # These are explicit original-joint FK landmarks, not claimed skin contacts.
    bone=("toe3-1." if region=="toe" else "foot.")+side
    rest=bv(MORPH["ankles_m"][side])+bv(MORPH["feet"][side][region+"_from_ankle_m"])
    return cv(world(bone)@REST_INV[bone]@rest)
refresh_markers()

intermediates=[n for n in NAMES if n.startswith(("upperleg02.","lowerleg02.","upperarm02.","lowerarm02."))]
def relative_q(name,rest=False):
    p=rig.data.bones[name].parent.name
    M=REST[p].inverted()@REST[name] if rest else world(p).inverted()@world(name)
    # Return canonical orientation so both rest and observed fields share +Y up.
    return quat_xyzw((CI@M@C).to_quaternion())
def intermediate_sample(name,rest=False):
    side=name[-1];kind=name.split(".")[0]
    a,b={"upperleg02":("upperleg01","lowerleg01"),"lowerleg02":("lowerleg01","foot"),"upperarm02":("upperarm01","lowerarm01"),"lowerarm02":("lowerarm01","wrist")}[kind]
    get=lambda n:REST[n].translation if rest else position(n)
    return {"relative_rotation_xyzw":relative_q(name,rest),"position_m":cv(get(name)),"segment_start_m":cv(get(a+"."+side)),"segment_end_m":cv(get(b+"."+side))}

def solve_control(part,side,delta,target,pole):
    chain=controls[(part,side)];chain["obj"].matrix_world=delta
    chain["target"].location=target;chain["pole"].location=pole;update()
    obj=chain["obj"]
    return {n:obj.matrix_world@obj.pose.bones[n].matrix@chain["rest"][n].inverted() for n in ("proximal","distal")}, obj.matrix_world@obj.pose.bones["distal"].tail

def solve(frame):
    rig.animation_data_clear()
    for pb in rig.pose.bones:pb.matrix_basis=Matrix.Identity(4)
    update()
    R=bm(frame["root_orientation_xyzw"])
    hip0=bv(MORPH["hip_center_m"]);hip=bv(frame["hip_center_m"])
    delta=Matrix.Translation(hip)@R@Matrix.Translation(-hip0)
    roots=[p.name for p in rig.pose.bones if p.parent is None];assert len(roots)==1
    pose(roots[0],delta@REST[roots[0]]);update()
    # Distribute authored sagittal flexion over existing spine bones, preserving translations.
    for n in ("spine05","spine04","spine03","spine02","spine01"):
        W=world(n);Q=Matrix.Rotation(frame["joint_intents"].get("spine_flexion_rad",0.)/5,4,"X")
        pose(n,Matrix.Translation(W.translation)@Q@Matrix.Translation(-W.translation)@W);update()
    if "head_orientation_xyzw" in frame["joint_intents"]:
        current_head=world("head");desired=bm(frame["joint_intents"]["head_orientation_xyzw"])@REST["head"]
        desired.translation=current_head.translation;pose("head",desired);update()
    for side in ("L","R"):
        ft=frame["feet"][side]
        solved,ankle=solve_control("leg",side,delta,bv(ft["ankle_m"]),bv(ft["knee_pole_m"]))
        for prefix,control in (("upperleg","proximal"),("lowerleg","distal")):
            for suffix in ("01","02"):pose(prefix+suffix+"."+side,solved[control]@REST[prefix+suffix+"."+side]);update()
        foot_delta=bm(ft["rotation_xyzw"]);foot_delta.translation=ankle-foot_delta.to_3x3()@REST["foot."+side].translation
        pose("foot."+side,foot_delta@REST["foot."+side]);update()
        axis=bv(ft.get("pitch_axis_unit",[1,0,0]));toeQ=Quaternion(axis,ft["toe_flexion_rad"]).to_matrix().to_4x4()
        for i in range(1,6):
            name="toe"+str(i)+"-1."+side;W=foot_delta@REST[name]
            pose(name,Matrix.Translation(W.translation)@toeQ@Matrix.Translation(-W.translation)@W);update()
    resolved={};hand_reach={}
    mouth_rest=bv(MORPH["landmarks_m"]["mouth"]);actual_mouth=world("jaw")@REST_INV["jaw"]@mouth_rest
    actual_head=world("head")@REST_INV["head"]@bv(MORPH["landmarks_m"]["head"])
    for side in ("L","R"):
        shoulder=position("upperarm01."+side);S=world("upperarm01."+side)@REST_INV["upperarm01."+side]
        length=(REST["lowerarm01."+side].translation-REST["upperarm01."+side].translation).length+(REST["wrist."+side].translation-REST["lowerarm01."+side].translation).length
        sign=1 if side=="L" else -1
        target=bv(frame["hands_m"][side])
        pole=bv(frame["arm_poles"][side]["position_m"])
        assert frame["arm_poles"][side]["reference"]=="world"
        solved,hand=solve_control("arm",side,S,target,pole)
        for prefix,control in (("upperarm","proximal"),("lowerarm","distal")):
            for suffix in ("01","02"):pose(prefix+suffix+"."+side,solved[control]@REST[prefix+suffix+"."+side]);update()
        pose("wrist."+side,solved["distal"]@REST["wrist."+side]);update()
        resolved[side]=cv(target);hand_reach[side]=(position("wrist."+side)-target).length
    return {"resolved_hands_m":resolved,"actual_mouth_proxy_m":cv(actual_mouth),"actual_head_proxy_m":cv(actual_head),"hand_reach_error_m":hand_reach,"target_semantics":"Aquatic hands are already resolved world targets; no mouth/head adjustment."}

foot_vertex_ids={}
for side in ("L","R"):
    relevant={i for i,g in enumerate(skin.vertex_groups) if g.name=="foot."+side or g.name.startswith("toe") and g.name.endswith("."+side)}
    foot_vertex_ids[side]=np.array([v.index for v in skin.data.vertices if sum(g.weight for g in v.groups if g.group in relevant)>.5],int)
    assert len(foot_vertex_ids[side])>100

def observe_context_geometry():
    if bpy.data.objects.get("R246 tub floor") is None:
        return {"status":"NATIVE_CONTEXT_NOT_EXPORTED_TO_BODY_GLB"}
    def top(name):
        obj=bpy.data.objects["R246 tub "+name]
        points=evaluated(obj)
        assert len(points)==8 and len(obj.data.polygons)==12
        # Indices 4..7 are the top corners of our original eight-vertex box.
        corners=[cv(p) for p in points[4:8]]
        return corners,np.mean(corners,axis=0).tolist()
    floor,fc=top("floor");seat,sc=top("seat")
    rim={};rim_corners={}
    for key,name in (("L","left rim"),("R","right rim"),("back","back rim"),("front","front rim")):
        corners,center=top(name);rim[key]=center;rim_corners[key]=corners
    return {"status":"EVALUATED_NATIVE_MESH_WORLD_VERTICES","coordinates":"canonical_metres_y_up",
       "tub":{"floor_top_center_m":fc,"floor_top_corners_m":floor,"seat_top_center_m":sc,"seat_top_corners_m":seat,
              "rim_top_centers_m":rim,"rim_top_corners_m":rim_corners},
       "water":{"surface_corners_m":[cv(p) for p in evaluated(bpy.data.objects["R246 static water surface"])],
                "bottom_corners_m":[cv(p) for p in evaluated(bpy.data.objects["R246 static pool bottom"])]}}

def observe(frame,resolved):
    update();actual={"hip_center_m":cv((position("upperleg01.L")+position("upperleg01.R"))/2),
        "root_transform":np.array(CI@world(next(p.name for p in rig.pose.bones if p.parent is None))@C).tolist(),
        "feet":{},"hands_m":{s:cv(position("wrist."+s)) for s in ("L","R")},
        "intermediate_bones":{n:intermediate_sample(n) for n in intermediates},
        "mouth_m":cv(world("jaw")@REST_INV["jaw"]@bv(MORPH["landmarks_m"]["mouth"])),
        "head_m":cv(world("head")@REST_INV["head"]@bv(MORPH["landmarks_m"]["head"])),
        "context_geometry":observe_context_geometry()}
    vertices=evaluated(skin)
    for side in ("L","R"):
        actual["feet"][side]={"hip_m":cv(position("upperleg01."+side)),"knee_m":cv(position("lowerleg01."+side)),"ankle_m":cv(position("foot."+side)),
          **{region+"_m":marker(side,region) for region in ("heel","forefoot","toe")},
          "rotation_xyzw":quat_xyzw((CI@world("foot."+side)@REST_INV["foot."+side]@C).to_quaternion()),
          "skin_sole_min_y_m":float(vertices[foot_vertex_ids[side],2].min())}
    actual["chest_surface_anchor_m"]=cv(vertices[CHEST_ID])
    actual["chest_source_vertex_id"]=CHEST_ID
    actual["arms"]={side:{"shoulder_m":cv(position("upperarm01."+side)),"elbow_m":cv(position("lowerarm01."+side)),"wrist_m":cv(position("wrist."+side))} for side in ("L","R")}
    if any(p.get("id")=="sponge" for p in frame.get("props",[])):
        obj=bpy.data.objects.get("R246 rigid sponge proxy")
        if obj:
            ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());local=sum((v.co for v in obj.data.vertices),Vector())/len(obj.data.vertices)
            center=ev.matrix_world@local;actual["sponge_center_m"]=cv(center)
            actual["sponge_center_to_chest_vertex_m"]=(center-Vector(vertices[CHEST_ID])).length
        else:actual["sponge_status"]="NATIVE_RENDER_PROP_NOT_EXPORTED_TO_GLB"
    return {"time_s":frame["time_s"],"actual":actual,"target":frame,"resolved_task":resolved,"replay_phase":"native_ik_then_original_rig_fk"}

def capture_source_world():
    return np.array([np.array(CI@world(n)@REST_INV[n]@C)@SOURCE_WORLD[i] for i,n in enumerate(NAMES)])

def cpu_skin(W):
    skinning=W@inverse_bind;p=np.column_stack((source_vertices,np.ones(len(source_vertices))));result=np.zeros((len(p),4))
    for slot in range(source_weights.shape[1]):
        result+=np.einsum("nij,nj->ni",skinning[source_indices[:,slot]],p)*source_weights[:,slot,None]
    return result[:,:3][:,[0,2,1]]*np.array([1,-1,1])

# Calibrate the original sponge once and attach it rigidly to the source wrist.
bath_first=AQUATIC["bathing_seated_wash"]["frames"][0];solve(bath_first)
dominant=MORPH.get("dominant_hand","R");wrist="wrist."+dominant
sponge_spec=next(p for p in bath_first["props"] if p["id"]=="sponge")
center=Vector(sponge_spec["position_m"]);radius=sponge_spec["radius_m"]
vertices=[];faces=[];add_box(vertices,faces,center-Vector((0,radius,0)),radius*2,radius,radius*2)
inverse=(world(wrist)@REST_INV[wrist]).inverted()
sponge=make_mesh("R246 rigid sponge proxy",[tup(inverse@bv(v)) for v in vertices],faces,material("Original sponge proxy",(.92,.69,.12)))
bone_parent(sponge,wrist,False)
# Static visual contexts, with cutaway tub surfaces for actual pose review.
context_objects={"swimming_front_crawl":[],"bathing_seated_wash":[]}
water_context=AQUATIC["swimming_front_crawl"]["instance"]["context"]
tub_context=AQUATIC["bathing_seated_wash"]["instance"]["context"]
def context_mesh(name,v,f,mat,activity):
    obj=make_mesh(name,[tup(bv(p)) for p in v],f,mat);context_objects[activity].append(obj.name);return obj
watermat=material("Static translucent water context",(.035,.24,.39))
nodes=watermat.node_tree.nodes;links=watermat.node_tree.links;surface=nodes.get("Principled BSDF");output=nodes.get("Material Output")
transparent=nodes.new("ShaderNodeBsdfTransparent");mix=nodes.new("ShaderNodeMixShader");mix.inputs[0].default_value=.14
links.new(transparent.outputs[0],mix.inputs[1]);links.new(surface.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs[0])
y=water_context["surface_y_m"]
context_mesh("R246 static water surface",[(-3,y,-4),(3,y,-4),(3,y,5),(-3,y,5)],[(0,1,2),(0,2,3)],watermat,"swimming_front_crawl")
floormat=material("Pool floor",(.08,.16,.20))
context_mesh("R246 static pool bottom",[(-3,y-water_context["depth_m"],-4),(3,y-water_context["depth_m"],-4),(3,y-water_context["depth_m"],5),(-3,y-water_context["depth_m"],5)],[(0,1,2),(0,2,3)],floormat,"swimming_front_crawl")
w=tub_context["interior_width_m"];length=tub_context["interior_length_m"];floor_y=tub_context["floor_y_m"];rim_y=tub_context["rim_y_m"];cx,cz=tub_context["center_xz_m"]
tubmat=material("Tub reference porcelain",(.55,.67,.69))
for name,center,width,depth,height in [
    ("floor",Vector((cx,floor_y-.025,cz)),w,length,.025),
    ("left rim",Vector((cx+w/2,rim_y-.035,cz)),.035,length,.035),
    ("right rim",Vector((cx-w/2,rim_y-.035,cz)),.035,length,.035),
    ("back rim",Vector((cx,rim_y-.035,cz-length/2)),w,.035,.035),
    ("front rim",Vector((cx,rim_y-.035,cz+length/2)),w,.035,.035),
    ("seat",Vector(tub_context["seat_center_m"])-Vector((0,.025,0)),tub_context["seat_width_m"],tub_context["seat_depth_m"],.025)]:
    v=[];f=[];add_box(v,f,center,width,depth,height);context_mesh("R246 tub "+name,v,f,tubmat,"bathing_seated_wash")
def context_visibility(activity):
    for key,names in context_objects.items():
        for name in names:bpy.data.objects[name].hide_render=key!=activity
    bpy.data.objects["R246 rigid sponge proxy"].hide_render=activity!="bathing_seated_wash"

FULL=set(AQUATIC);IDS=list(AQUATIC)
clips=[];actions={};tracks={};checks=[];replay_reference={};activity_state=[];clip_inputs={}
for activity in IDS:
    clip=AQUATIC[activity]
    sample_ids=list(range(len(clip["frames"]))) if activity in FULL and not QUICK else sorted(set(np.linspace(0,len(clip["frames"])-1,5,dtype=int).tolist()))
    rows=[];W_all=[];bone_basis=[];times=[]
    for idx in sample_ids:
        frame=clip["frames"][idx];resolved=solve(frame);rows.append(observe(frame,resolved))
        W=capture_source_world();W_all.append(W);times.append(frame["time_s"])
        bone_basis.append([(p.location.copy(),p.rotation_quaternion.copy(),p.scale.copy()) for p in (rig.pose.bones[n] for n in NAMES)])
        if idx in (sample_ids[0],sample_ids[len(sample_ids)//2],sample_ids[-1]):
            actual=evaluated(skin);error=nearest_error(actual,cpu_skin(W),2048)
            checks.append({"activity_id":activity,"time_s":frame["time_s"],"phase":"native_fk_vs_exact_source_full_weight_lbs","max_bidirectional_error_m":error})
            replay_reference[(activity,frame["time_s"])]=actual.copy()
    # Keyframe original source armature. Controls are separate and never replace its 163 bones.
    rig.animation_data_clear();rig.animation_data_create()
    action=bpy.data.actions.new(CASE["id"]+" / "+activity);action.use_fake_user=True;rig.animation_data.action=action
    for ti,poses in zip(times,bone_basis):
        for n,(loc,rot,scale) in zip(NAMES,poses):
            pb=rig.pose.bones[n];pb.location=loc;pb.rotation_quaternion=rot;pb.scale=scale
            pb.keyframe_insert("location",frame=1+ti*24,group=n);pb.keyframe_insert("rotation_quaternion",frame=1+ti*24,group=n)
    curves=list(action.fcurves) if hasattr(action,"fcurves") else [fc for layer in action.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]
    for fc in curves:
        for key in fc.keyframe_points:key.interpolation="LINEAR"
    actions[activity]=action.name;tracks[activity]={"times":times,"world":np.array(W_all)};clip_inputs[activity]=clip
    row={"activity_id":activity,"compiler_clip":clip,"frames":rows,"sample_scope":"all authored 24 fps frames" if len(sample_ids)==len(clip["frames"]) else "five critical keys only; sparse interpolation is not qualified"}
    clips.append(row)
    activity_state.append({"activity_id":activity,"compile":"PASS","native_rig_evaluation":"COMPLETE_24_FPS" if len(sample_ids)==len(clip["frames"]) else "FIVE_CRITICAL_KEYS","evaluated_frames":len(rows),"authored_frames":len(clip["frames"]),"render":"PENDING","glb_export":"PENDING","blend_replay":"PENDING"})
    log("CLIP",{"case":CASE["id"],"activity":activity,"frames":len(rows),"max_ankle_target_error_m":max(np.linalg.norm(np.array(r["actual"]["feet"][s]["ankle_m"])-r["target"]["feet"][s]["ankle_m"]) for r in rows for s in ("L","R")),"skin_lbs_error_m":max(c["max_bidirectional_error_m"] for c in checks if c["activity_id"]==activity)})

rest={"hips_m":MORPH["hips_m"],"knees_m":MORPH["knees_m"],"ankles_m":MORPH["ankles_m"],
      "thigh_length_m":{s:float(np.linalg.norm(np.array(MORPH["hips_m"][s])-MORPH["knees_m"][s])) for s in ("L","R")},
      "shin_length_m":{s:float(np.linalg.norm(np.array(MORPH["knees_m"][s])-MORPH["ankles_m"][s])) for s in ("L","R")},
      "arms":MEASURED["arms"],
      "intermediate_bones":{n:intermediate_sample(n,True) for n in intermediates}}
observations={"schema":"oneirifact.aquatic-native-observations/v1","cases":[{"id":CASE["id"],"morphology":MORPH,"footwear":SHOE,"bind_sha":MORPH["source_bind_sha256"],"environment":{"medium":"aquatic_context"},"rest":rest,"clips":clips}],
 "scope":"Actual original-rig FK/full-weight skin and actual source chest vertex. Feet markers are rigid original-joint FK landmarks, not skin-contact proof. Explicit world aquatic targets. Static context/sponge, no fluid forces, buoyancy, airway, grip/contact, joint-range or realism admission."}
save_json(OUT/"native-ik-observations.json",observations)
save_json(OUT/"consumer-observations.json",observations)
save_json(OUT/"ik-calibration.json",calibration)

def export_glb():
    d=copy.deepcopy(DOC);b=bytearray(BIN)
    d["animations"]=[]
    for name,data in tracks.items():
        sampler_input=add(d,b,np.array(data["times"],dtype="<f4").reshape(-1,1),kind="SCALAR",bounds=True)
        anim={"name":name,"samplers":[],"channels":[]}
        matrices={}
        for i in range(163):
            matrices[i]=np.array([np.linalg.inv(W[PARENTS[i]])@W[i] if i in PARENTS and PARENTS[i]<163 else W[i] for W in data["world"]])
        for ni,ms in matrices.items():
            rotations=np.array([quat_xyzw(Matrix(m.tolist()).to_quaternion()) for m in ms])
            for j in range(1,len(rotations)):
                if rotations[j-1]@rotations[j]<0:rotations[j]*=-1
            for path,value,kind in (("translation",ms[:,:3,3],"VEC3"),("rotation",rotations,"VEC4")):
                out_accessor=add(d,b,value.astype("<f4"),kind=kind)
                anim["channels"].append({"sampler":len(anim["samplers"]),"target":{"node":ni,"path":path}})
                anim["samplers"].append({"input":sampler_input,"output":out_accessor,"interpolation":"LINEAR"})
        d["animations"].append(anim)
    d["asset"]["generator"]="Oneirifact R246 observed Blender motion baked to exact full-weight source hierarchy"
    packed=encode(d,b);(OUT/"aquatic-prototypes.glb").write_bytes(packed)
    dd,bb=parse(packed);pa=dd["meshes"][0]["primitives"][0]["attributes"]
    assert all(np.array_equal(read(dd,bb,pa[k]),read(DOC,BIN,attrs[k])) for k in attrs),"source geometry/weights changed during motion export"
    assert len(dd["skins"][0]["joints"])==163
    return {"sha256":sha(packed),"bytes":len(packed),"full_source_attributes_bit_identical":True,"original_skin_bones":163,"source_max_influences":9,"animations":len(tracks)}

export=export_glb()
def choose_action(activity,t):
    rig.animation_data_create();rig.animation_data.action=bpy.data.actions[actions[activity]]
    if hasattr(rig.animation_data,"action_slot") and len(rig.animation_data.action.slots):rig.animation_data.action_slot=rig.animation_data.action.slots[0]
    f=1+t*24;scene.frame_set(int(f),subframe=f-int(f));update()

for (activity,t),expected in replay_reference.items():
    choose_action(activity,t);err=nearest_error(evaluated(skin),expected,2048)
    checks.append({"activity_id":activity,"time_s":t,"phase":"baked_blend_action","max_bidirectional_error_m":err})
for activity in IDS:
    if activity in actions:
        for t in (.3125,.7291666666666666):
            choose_action(activity,t)
            replay_reference[(activity,t)]=evaluated(skin).copy()
assert max(c["max_bidirectional_error_m"] for c in checks)<5e-5,"full-weight native/export-basis transport error"

if QUICK:
    save_json(OUT/"local-preflight.json",{"checks":checks,"export":export,"calibration":calibration,"qualification":"LOCAL_PREFLIGHT_ONLY; public pinned runtime still required"})
    log("PREFLIGHT_COMPLETE",{"case":CASE["id"],"worst_skin_error_m":max(c["max_bidirectional_error_m"] for c in checks)});sys.exit(0)

# Actual product scene and CPU rendering; no source mesh edits.
scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=6;scene.cycles.use_denoising=not bool(os.environ.get("R246_LOCAL_NO_DENOISE"));scene.cycles.max_bounces=3
scene.render.resolution_x=420;scene.render.resolution_y=560;scene.render.resolution_percentage=100;scene.render.image_settings.file_format="PNG"
scene.world=bpy.data.worlds.new("Neutral motion studio");scene.world.use_nodes=True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value=(.035,.05,.075,1);scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value=.5
scene.view_settings.view_transform="AgX"
def look(obj,point):obj.rotation_euler=(Vector(point)-obj.location).to_track_quat("-Z","Y").to_euler()
bpy.ops.object.camera_add(location=(3,-6,2.2));camera=bpy.context.object;camera.name="Motion review camera";camera.data.type="ORTHO";scene.camera=camera
for loc,power,size in (((3,-4,5),550,4),((-3,-1,3),400,3),((1,4,3),650,3)):
    bpy.ops.object.light_add(type="AREA",location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape="DISK";o.data.size=size;look(o,(0,0,.8))
def render(activity,t,path,preview=False):
    choose_action(activity,t);context_visibility(activity)
    points=evaluated(skin);center=(points.min(0)+points.max(0))/2
    if activity=="swimming_front_crawl":
        camera.data.ortho_scale=MORPH["stature_m"]*1.48;camera.location=center+np.array([2.7,-3.3,3.0])
    else:
        camera.data.ortho_scale=MORPH["stature_m"]*1.40
        camera.location=center+np.array([2.6,-4.2,2.8])
    look(camera,center)
    scene.render.resolution_x=384 if preview else 640;scene.render.resolution_y=288 if preview else 480;scene.cycles.samples=4 if preview else 12
    scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
render_specs=[("swimming_front_crawl",0,"01-crawl-entry"),("swimming_front_crawl",.6,"02-crawl-recovery"),("bathing_seated_wash",0,"03-seated-wash"),("bathing_seated_wash",1.6,"04-wash-sweep")]
for activity,t,name in render_specs:render(activity,t,OUT/(name+".png"))
video_manifest=[]
for activity in IDS:
    folder=OUT/(activity+"-frames");folder.mkdir()
    duration=AQUATIC[activity]["instance"]["duration_s"]
    for i,t in enumerate(np.arange(0,duration,1/8)):render(activity,float(t),folder/(str(i).zfill(4)+".png"),True)
    video_manifest.append({"activity_id":activity,"folder":folder.name,"fps":8,"frames":i+1,"scope":"Actual authored aquatic native pose sequence, static water/tub context; no physics or realism admission."})
for row in activity_state:
    row["render"]="VIDEO_8_FPS_AND_STILL" if row["activity_id"] in [v["activity_id"] for v in video_manifest] else "STILL" if row["activity_id"] in [x[0] for x in render_specs] else "NOT_RENDERED"
    row["glb_export"]="SOURCE_ATTRIBUTES_EXACT_OBSERVED_POSE_BAKED";row["blend_replay"]="PASS_SAMPLED_ACTION_REPLAY"

choose_action("swimming_front_crawl",.6);context_visibility("swimming_front_crawl")
scene.frame_start=1;scene.frame_end=int(1+clip_inputs["swimming_front_crawl"]["instance"]["duration_s"]*24)
source_text=bpy.data.texts.new("R246 consumer source");source_text.write(Path(__file__).read_text())
notes=bpy.data.texts.new("R246 scope and replay");notes.write(json.dumps({"case":CASE,"activities":activity_state,"source_rig":rig.name,"actions":actions,"limitations":["Authored aquatic kinematic prototypes, not measured mocap or dynamics","Explicitly barefoot. Static water/tub context and rigid sponge are native/render-only proxies","Choose the original rig action in the Action Editor; 163 original bones retained","Separate IK controls are construction controls; source actions are baked snapshots","No internal anatomy, full-body collision, grip/washing contact, fluid forces, balance, airway or physiology acceptance"]},indent=2))
blend=OUT/"aquatic-prototypes.blend";bpy.ops.wm.save_as_mainfile(filepath=str(blend),compress=True)
rig_name=rig.name;skin_name=skin.name
bpy.ops.wm.open_mainfile(filepath=str(blend));scene=bpy.context.scene;rig=bpy.data.objects[rig_name];skin=bpy.data.objects[skin_name]
refresh_markers()
for (activity,t),expected in replay_reference.items():
    choose_action(activity,t);error=nearest_error(evaluated(skin),expected,2048)
    checks.append({"phase":"saved_blend_reopened","activity_id":activity,"time_s":t,"max_bidirectional_error_m":error})
for clip in observations["cases"][0]["clips"]:
    rows=[]
    for row in clip["frames"]:
        choose_action(clip["activity_id"],row["time_s"]);new=observe(row["target"],row["resolved_task"]);new["replay_phase"]="saved_blend_reopened";rows.append(new)
    clip["frames"]=rows
save_json(OUT/"reopened-blend-observations.json",observations)

# Reimport the packed body-only GLB independently, including both animation slots.
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(OUT/"aquatic-prototypes.glb"))
scene=bpy.context.scene;scene.render.fps=24
import_rig=next(o for o in scene.objects if o.type=="ARMATURE");import_skin=next(o for o in scene.objects if o.type=="MESH" and any(m.type=="ARMATURE" for m in o.modifiers))
assert len(import_rig.data.bones)==163
import_actions=list(bpy.data.actions)
def apply_import_action(obj,activity):
    ad=obj.animation_data
    candidates=[]
    if ad:
        for track in ad.nla_tracks:
            track.mute=True
            if track.name==activity:
                for strip in track.strips:
                    if strip.action:candidates.append((strip.action,getattr(strip,"action_slot",None)))
    assert len(candidates)==1,"missing/ambiguous exact imported NLA animation "+activity+" for "+obj.name
    action,slot=candidates[0];obj.animation_data_create();obj.animation_data.action=action
    if slot is not None:obj.animation_data.action_slot=slot
for (activity,t),expected in replay_reference.items():
    apply_import_action(import_rig,activity)
    f=float(import_rig.animation_data.action.frame_range[0])+t*24;scene.frame_set(int(f),subframe=f-int(f));update()
    error=nearest_error(evaluated(import_skin),expected,2048)
    checks.append({"phase":"baked_glb_reimported","activity_id":activity,"time_s":t,"max_bidirectional_error_m":error})
    log("GLB_REPLAY",checks[-1])
rig=import_rig;skin=import_skin;refresh_markers()
for clip in observations["cases"][0]["clips"]:
    apply_import_action(import_rig,clip["activity_id"])
    rows=[]
    for row in clip["frames"]:
        f=float(import_rig.animation_data.action.frame_range[0])+row["time_s"]*24;scene.frame_set(int(f),subframe=f-int(f));update()
        new=observe(row["target"],row["resolved_task"]);new["replay_phase"]="exported_glb_reimported";rows.append(new)
    clip["frames"]=rows
save_json(OUT/"consumer-observations.json",observations)

worst=max(c["max_bidirectional_error_m"] for c in checks)
transport="PASS" if worst<5e-5 else "FAIL"
receipt={"schema":"oneirifact.aquatic-native-consumer-receipt/v1","status":transport+"_NATIVE_CONSUMER_TRANSPORT","realism":"HOLD_AUTHORED_KINEMATIC_PROTOTYPE","case":CASE,
 "actual_footwear":"barefoot; no footwear meshes in native render or body GLB",
 "source_head_commit":os.environ.get("SOURCE_HEAD_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),"blender_version":bpy.app.version_string,
 "time_mapping":{"authored_blend":"frame=1+24*time_s","imported_glb":"frame=observed_action_first_frame+24*time_s","fractional_seek":"Two off-key samples per aquatic clip, compared after reopen and reimport"},
 "activities":activity_state,"videos":video_manifest,"export":export,"checks":checks,"marker_import_guards":marker_import_guards,"worst_transport_error_m":worst,"transport_tolerance_m":5e-5,
 "contact_acceptance":"SEPARATE_AQUATIC_OBSERVATION_CRITIC_PENDING","geometry_preservation":"Original 13380 vertices/26756 triangles,163 source bones,3packed influence sets retained; source rest-bind fitting precedes animation.",
 "props":{"water":"Static world surface and bottom context only","tub":"Static exact context floor, rim and seat, walls omitted for review cutaway","sponge":"Rigid original-wrist child in native scene/render only; actual mesh center observed; no grip/contact admission"},
 "limitations":["Two explicitly barefoot source binds; no aquatic footwear qualification","All poses are original authored kinematic prototypes, not captured human motion","Feet markers are rigid joint-local landmarks; skin sole subset is observed separately","No fluid forces, buoyancy, friction, dynamic balance, joint limits or full-body collision qualification","Actual mouth proxy height does not qualify breathing or airway clearance","Actual source chest vertex and sponge proximity do not establish washing contact","Native context and sponge are omitted from animated body-only GLB; no standard per-clip visibility encoding","Skin-only: internal anatomical skeletal meshes and physiological tissues omitted"],"files":{}}
for path in sorted(OUT.iterdir()):
    if path.is_file() and path.name!="consumer-receipt.json":receipt["files"][path.name]={"bytes":path.stat().st_size,"sha256":sha(path.read_bytes())}
save_json(OUT/"consumer-receipt.json",receipt)
log("COMPLETE",{"case":CASE["id"],"status":receipt["status"],"worst_transport_error_m":worst,"clips":len(clips),"blend_bytes":blend.stat().st_size})
assert transport=="PASS","independent saved/reimported consumer transport exceeded tolerance"
