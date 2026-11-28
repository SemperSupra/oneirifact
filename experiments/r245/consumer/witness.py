"""Actual Blender motion consumer. All observations are evaluated geometry/FK.

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
from compiler import compile_clip,footwear_from_profile,compose_upper_body

OUT=Path(sys.argv[sys.argv.index("--")+1]);QUICK="--quick" in sys.argv
DAILY="--daily-coverage" in sys.argv
daily_props=None
CASE=json.loads((OUT/"case.json").read_text());MORPH=CASE["morphology"]
SHOE=footwear_from_profile(CASE["shoe_profile"],MORPH)
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
def log(tag,x):print("R245_"+tag,json.dumps(x,allow_nan=False),flush=True)

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
shoemat=material("Footwear support proxy",(.045,.065,.09),.32)
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

standing=compile_clip("standing",MORPH,SHOE,fps=24)
shoe_objects=[];markers={};bindings=standing["footwear_bindings"]
for side in ("L","R"):
    binding=bindings[side];ankle=Vector(MORPH["ankles_m"][side]);foot=standing["frames"][0]["feet"][side]
    Q=qmat(foot["rotation_xyzw"]);D=Matrix.Translation(Vector(foot["ankle_m"]))@Q@Matrix.Translation(-ankle)
    vertices=[];faces=[];marks={}
    for region in ("heel","forefoot"):
        center=Vector(foot[region+"_m"]);w,l=SHOE[region+"_footprint_m"]
        marks[region]=add_box(vertices,faces,center,w,l,max(.004,SHOE[region+"_stack_m"]),D.inverted())
    # A narrow rigid upper sole connects the support posts; all geometry is fixed at bind.
    h=Vector(foot["heel_m"]);f=Vector(foot["forefoot_m"]);h.y+=SHOE["heel_stack_m"];f.y+=SHOE["forefoot_stack_m"]
    strip_start=len(vertices);w=MORPH["feet"][side]["width_m"]*.34
    for thickness in (-.005,0):
        for p in (h-Vector((w,0,0)),h+Vector((w,0,0)),f+Vector((w*1.3,0,0)),f-Vector((w*1.3,0,0))):
            vertices.append(tup(D.inverted()@(p+Vector((0,thickness,0)))))
    faces.extend(tuple(strip_start+j for j in ids) for ids in ((0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)))
    obj=make_mesh("Shoe rigid "+side,[tup(bv(v)) for v in vertices],faces,shoemat);bone_parent(obj,"foot."+side)
    shoe_objects.append(obj)
    markers[side]={region:(obj,indices) for region,indices in marks.items()}
    pivot=ankle+Vector(binding["toe_pivot_from_ankle_rest_m"])
    flex=Quaternion(Vector(binding["pitch_axis_unit"]),foot["toe_flexion_rad"]).to_matrix().to_4x4()
    TD=D@Matrix.Translation(pivot)@flex@Matrix.Translation(-pivot)
    tv=[];tf=[];width=MORPH["feet"][side]["width_m"]*.82
    length=max(.025,(Vector(foot["toe_m"])-Vector(foot["forefoot_m"])).length*.95)
    ids=add_box(tv,tf,Vector(foot["toe_m"]),width,length,max(.004,SHOE["forefoot_stack_m"]),TD.inverted())
    toe=make_mesh("Shoe toe "+side,[tup(bv(v)) for v in tv],tf,shoemat);bone_parent(toe,"toe3-1."+side)
    shoe_objects.append(toe);markers[side]["toe"]=(toe,ids)
MARKER_SPEC={s:{k:(o.name,list(ids)) for k,(o,ids) in m.items()} for s,m in markers.items()}
MARKER_LOCAL_SPEC={s:{k:np.array([tuple(o.data.vertices[i].co) for i in ids]) for k,(o,ids) in m.items()} for s,m in markers.items()}
marker_import_guards=[]
def refresh_markers():
    global markers
    markers={s:{k:(bpy.data.objects[name],ids) for k,(name,ids) in m.items()} for s,m in MARKER_SPEC.items()}
    for side,items in markers.items():
        for region,(obj,ids) in items.items():
            expected=MARKER_LOCAL_SPEC[side][region];actual=np.array([tuple(obj.data.vertices[i].co) for i in ids])
            error=nearest_error(actual,expected,len(expected));centroid_error=float(np.linalg.norm(actual.mean(0)-expected.mean(0)))
            assert max(error,centroid_error)<2e-6,"imported marker index/geometry mismatch"
            marker_import_guards.append({"side":side,"region":region,"local_face_vertex_error_m":error,"local_centroid_error_m":centroid_error})

def marker(side,region):
    obj,ids=markers[side][region];ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    local=sum((obj.data.vertices[i].co for i in ids),Vector())/len(ids)
    return cv(ev.matrix_world@local)

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
        W=world(n);Q=Matrix.Rotation(frame["joint_intents"]["spine_flexion_rad"]/5,4,"X")
        pose(n,Matrix.Translation(W.translation)@Q@Matrix.Translation(-W.translation)@W);update()
    for side in ("L","R"):
        ft=frame["feet"][side]
        solved,ankle=solve_control("leg",side,delta,bv(ft["ankle_m"]),bv(ft["knee_pole_m"]))
        for prefix,control in (("upperleg","proximal"),("lowerleg","distal")):
            for suffix in ("01","02"):pose(prefix+suffix+"."+side,solved[control]@REST[prefix+suffix+"."+side]);update()
        foot_delta=bm(ft["rotation_xyzw"]);foot_delta.translation=ankle-foot_delta.to_3x3()@REST["foot."+side].translation
        pose("foot."+side,foot_delta@REST["foot."+side]);update()
        axis=bv(ft["pitch_axis_unit"]);toeQ=Quaternion(axis,ft["toe_flexion_rad"]).to_matrix().to_4x4()
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
        if side in frame["hands_m"]:
            target=bv(frame["hands_m"][side]);is_head=any(p.get("target")=="head" for p in frame["prop_contacts"])
            anchor=actual_head if is_head else actual_mouth
            name="head" if is_head else "mouth"
            predicted=bv(MORPH["landmarks_m"][name])+hip-hip0
            target+=anchor-predicted
        else:
            angle=frame["joint_intents"]["arm_swing_rad"].get(side,0.)
            # Authored relaxed posture; wrist beside thigh, not the source A-pose.
            target=shoulder+bv((sign*.11*length,-.93*length,math.sin(angle)*.6*length+.025))
        pole=shoulder+bv((sign*.75*length,-.38*length,-.45*length))
        solved,hand=solve_control("arm",side,S,target,pole)
        for prefix,control in (("upperarm","proximal"),("lowerarm","distal")):
            for suffix in ("01","02"):pose(prefix+suffix+"."+side,solved[control]@REST[prefix+suffix+"."+side]);update()
        pose("wrist."+side,solved["distal"]@REST["wrist."+side]);update()
        if daily_props is not None:daily_props.adjust_wrist(frame,side)
        resolved[side]=cv(target);hand_reach[side]=(position("wrist."+side)-target).length
    return {"resolved_hands_m":resolved,"actual_mouth_proxy_m":cv(actual_mouth),"actual_head_proxy_m":cv(actual_head),"hand_reach_error_m":hand_reach}

foot_vertex_ids={}
for side in ("L","R"):
    relevant={i for i,g in enumerate(skin.vertex_groups) if g.name=="foot."+side or g.name.startswith("toe") and g.name.endswith("."+side)}
    foot_vertex_ids[side]=np.array([v.index for v in skin.data.vertices if sum(g.weight for g in v.groups if g.group in relevant)>.5],int)
    assert len(foot_vertex_ids[side])>100

def observe(frame,resolved):
    update();actual={"hip_center_m":cv((position("upperleg01.L")+position("upperleg01.R"))/2),
        "root_transform":np.array(CI@world(next(p.name for p in rig.pose.bones if p.parent is None))@C).tolist(),
        "feet":{},"hands_m":{s:cv(position("wrist."+s)) for s in ("L","R")},
        "intermediate_bones":{n:intermediate_sample(n) for n in intermediates},
        "mouth_m":cv(world("jaw")@REST_INV["jaw"]@bv(MORPH["landmarks_m"]["mouth"])),
        "head_m":cv(world("head")@REST_INV["head"]@bv(MORPH["landmarks_m"]["head"]))}
    vertices=evaluated(skin)
    for side in ("L","R"):
        actual["feet"][side]={"hip_m":cv(position("upperleg01."+side)),"knee_m":cv(position("lowerleg01."+side)),"ankle_m":cv(position("foot."+side)),
          **{region+"_m":marker(side,region) for region in ("heel","forefoot","toe")},
          "rotation_xyzw":quat_xyzw((CI@world("foot."+side)@REST_INV["foot."+side]@C).to_quaternion()),
          "skin_sole_min_y_m":float(vertices[foot_vertex_ids[side],2].min())}
    if any(p.get("id")=="toothbrush" for p in frame.get("props",[])) and bpy.data.objects.get("Toothbrush support proxy"):
        obj=bpy.data.objects["Toothbrush support proxy"];ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        tip=ev.matrix_world@(sum((obj.data.vertices[i].co for i in BRUSH_TIP_IDS),Vector())/len(BRUSH_TIP_IDS))
        actual["prop_tips_m"]={"toothbrush":cv(tip)}
        actual["toothbrush_tip_to_mouth_proxy_m"]=(tip-bv(actual["mouth_m"])).length
    if daily_props is not None:daily_props.observe(frame,actual)
    return {"time_s":frame["time_s"],"actual":actual,"target":frame,"resolved_task":resolved,"replay_phase":"native_ik_then_original_rig_fk"}

def capture_source_world():
    return np.array([np.array(CI@world(n)@REST_INV[n]@C)@SOURCE_WORLD[i] for i,n in enumerate(NAMES)])

def cpu_skin(W):
    skinning=W@inverse_bind;p=np.column_stack((source_vertices,np.ones(len(source_vertices))));result=np.zeros((len(p),4))
    for slot in range(source_weights.shape[1]):
        result+=np.einsum("nij,nj->ni",skinning[source_indices[:,slot]],p)*source_weights[:,slot,None]
    return result[:,:3][:,[0,2,1]]*np.array([1,-1,1])

# Original rigid tool geometry calibrated once, then attached to the source wrist.
# It remains a .blend/render prop; standard GLB visibility does not encode per-clip props.
brush_first=compile_clip("brushing_teeth",MORPH,SHOE,fps=24)["frames"][0]
brush_resolved=solve(brush_first);dominant=MORPH.get("dominant_hand","R")
wrist="wrist."+dominant;wrist_delta=world(wrist)@REST_INV[wrist]
brush_tip=bv(brush_first["props"][0]["tip_target_m"])
brush_tip+=bv(brush_resolved["actual_mouth_proxy_m"])-bv(MORPH["landmarks_m"]["mouth"])-bv(np.array(brush_first["hip_center_m"])-MORPH["hip_center_m"])
brush_start=position(wrist);axis=(brush_tip-brush_start).normalized();u=axis.cross(Vector((0,0,1))).normalized();v=axis.cross(u).normalized()
brush_vertices=[];brush_faces=[]
for p,radius in ((brush_start-axis*.025,.004),(brush_tip-axis*.02,.004),(brush_tip-axis*.02,.009),(brush_tip,.009)):
    for i in range(8):brush_vertices.append(tup(wrist_delta.inverted()@(p+radius*(math.cos(i*math.tau/8)*u+math.sin(i*math.tau/8)*v))))
for ring in range(3):
    for i in range(8):
        a=ring*8+i;b=ring*8+(i+1)%8;c=b+8;d=a+8;brush_faces.extend(((a,b,c),(a,c,d)))
BRUSH_TIP_IDS=list(range(24,32))
brush=make_mesh("Toothbrush support proxy",brush_vertices,brush_faces,material("Toothbrush handle",(.05,.58,.51),.4))
brush.data.materials.append(material("Brush head proxy",(.84,.89,.85),.7))
for p in brush.data.polygons:
    if p.index>=32:p.material_index=1
bone_parent(brush,wrist,False)
if DAILY:
    from daily_props import DailyProps
    daily_props=DailyProps(globals())

FULL={"standing","sit_to_stand","squatting","walking","brushing_teeth","walking_brush"}
IDS=["standing","sitting","sit_to_stand","squatting","walking","brushing_teeth","crouching","jogging","running","showering","eating_ice_cream_cone","walking_brush"]
if DAILY:FULL=set(IDS)
if QUICK:IDS=["standing","squatting","walking","brushing_teeth"]
clips=[];actions={};tracks={};checks=[];replay_reference={};activity_state=[];clip_inputs={}
for activity in IDS:
    if activity=="walking_brush":
        base=compile_clip("walking",MORPH,SHOE,fps=24)
        overlay=compile_clip("brushing_teeth",MORPH,SHOE,fps=24,duration_s=base["instance"]["duration_s"])
        clip=compose_upper_body(base,overlay)
    else:clip=compile_clip(activity,MORPH,SHOE,fps=24)
    sample_ids=list(range(len(clip["frames"]))) if activity in FULL and not QUICK else sorted(set(np.linspace(0,len(clip["frames"])-1,5,dtype=int).tolist()))
    rows=[];W_all=[];shoe_world=[];bone_basis=[];times=[]
    for idx in sample_ids:
        frame=clip["frames"][idx];resolved=solve(frame);rows.append(observe(frame,resolved))
        W=capture_source_world();W_all.append(W);times.append(frame["time_s"])
        shoe_world.append([np.array(o.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world) for o in shoe_objects])
        bone_basis.append([(p.location.copy(),p.rotation_quaternion.copy(),p.scale.copy()) for p in (rig.pose.bones[n] for n in NAMES)])
        if idx in (sample_ids[0],sample_ids[len(sample_ids)//2],sample_ids[-1]):
            actual=evaluated(skin);error=nearest_error(actual,cpu_skin(W),2048)
            checks.append({"activity_id":activity,"time_s":frame["time_s"],"phase":"native_fk_vs_exact_source_full_weight_lbs","max_bidirectional_error_m":error})
            replay_reference[(activity,frame["time_s"])]=(actual.copy(),{o.name:evaluated(o) for o in shoe_objects})
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
    actions[activity]=action.name;tracks[activity]={"times":times,"world":np.array(W_all),"shoes":np.array(shoe_world)};clip_inputs[activity]=clip
    row={"activity_id":activity,"compiler_clip":clip,"frames":rows,"sample_scope":"all authored 24 fps frames" if len(sample_ids)==len(clip["frames"]) else "five critical keys only; sparse interpolation is not qualified"}
    clips.append(row)
    activity_state.append({"activity_id":activity,"compile":"PASS","native_rig_evaluation":"COMPLETE_24_FPS" if len(sample_ids)==len(clip["frames"]) else "FIVE_CRITICAL_KEYS","evaluated_frames":len(rows),"authored_frames":len(clip["frames"]),"render":"PENDING","glb_export":"PENDING","blend_replay":"PENDING"})
    log("CLIP",{"case":CASE["id"],"activity":activity,"frames":len(rows),"max_ankle_target_error_m":max(np.linalg.norm(np.array(r["actual"]["feet"][s]["ankle_m"])-r["target"]["feet"][s]["ankle_m"]) for r in rows for s in ("L","R")),"skin_lbs_error_m":max(c["max_bidirectional_error_m"] for c in checks if c["activity_id"]==activity)})

rest={"hips_m":MORPH["hips_m"],"knees_m":MORPH["knees_m"],"ankles_m":MORPH["ankles_m"],
      "thigh_length_m":{s:float(np.linalg.norm(np.array(MORPH["hips_m"][s])-MORPH["knees_m"][s])) for s in ("L","R")},
      "shin_length_m":{s:float(np.linalg.norm(np.array(MORPH["knees_m"][s])-MORPH["ankles_m"][s])) for s in ("L","R")},
      "intermediate_bones":{n:intermediate_sample(n,True) for n in intermediates}}
observations={"schema":"oneirifact.motion-consumer-observations/v1","cases":[{"id":CASE["id"],"morphology":MORPH,"footwear":SHOE,"bind_sha":MORPH["source_bind_sha256"],"environment":{"ground_y_m":0},"rest":rest,"clips":clips}],
 "scope":"Actual original-rig FK and skin plus fixed rest-local bone-parented rigid shoe vertices. Mouth/head are authored proxies. Static support proxy is not fitted footwear. No dynamic balance, joint-range, soft-tissue or anatomical admission."}
save_json(OUT/"native-ik-observations.json",observations)
save_json(OUT/"consumer-observations.json",observations)
save_json(OUT/"ik-calibration.json",calibration)

def export_glb():
    d=copy.deepcopy(DOC);b=bytearray(BIN);shoe_nodes=[]
    d.setdefault("materials",[]).append({"name":"Rigid footwear support proxy","pbrMetallicRoughness":{"baseColorFactor":[.045,.065,.09,1],"metallicFactor":0,"roughnessFactor":.32}})
    for obj in shoe_objects:
        v=np.array([cv(p.co) for p in obj.data.vertices],dtype="<f4")
        faces=np.array([tuple(p.vertices) for p in obj.data.polygons],dtype="<u4");assert faces.shape[1]==3
        position_accessor=add(d,b,v,target=34962,bounds=True);index_accessor=add(d,b,faces.reshape(-1,1),kind="SCALAR",component=5125,target=34963)
        mi=len(d["meshes"]);d["meshes"].append({"name":obj.name,"primitives":[{"attributes":{"POSITION":position_accessor},"indices":index_accessor,"material":len(d["materials"])-1}]})
        parent=INDEX[obj.parent_bone]
        ni=len(d["nodes"]);d["nodes"].append({"name":obj.name,"mesh":mi,"matrix":np.linalg.inv(SOURCE_WORLD[parent]).T.reshape(-1).tolist()})
        d["nodes"][parent].setdefault("children",[]).append(ni);shoe_nodes.append(ni)
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
    d["asset"]["generator"]="Oneirifact R245 observed Blender motion baked to exact full-weight source hierarchy"
    packed=encode(d,b);(OUT/"activity-prototypes.glb").write_bytes(packed)
    dd,bb=parse(packed);pa=dd["meshes"][0]["primitives"][0]["attributes"]
    assert all(np.array_equal(read(dd,bb,pa[k]),read(DOC,BIN,attrs[k])) for k in attrs),"source geometry/weights changed during motion export"
    assert len(dd["skins"][0]["joints"])==163
    return {"sha256":sha(packed),"bytes":len(packed),"full_source_attributes_bit_identical":True,"original_skin_bones":163,"source_max_influences":9,"animations":len(tracks)}

export=export_glb()
def choose_action(activity,t):
    rig.animation_data_create();rig.animation_data.action=bpy.data.actions[actions[activity]]
    if hasattr(rig.animation_data,"action_slot") and len(rig.animation_data.action.slots):rig.animation_data.action_slot=rig.animation_data.action.slots[0]
    f=1+t*24;scene.frame_set(int(f),subframe=f-int(f));update()
    if DAILY:
        if bpy.data.objects.get("Toothbrush support proxy"):bpy.data.objects["Toothbrush support proxy"].hide_render=activity not in ("brushing_teeth","walking_brush")
        if bpy.data.objects.get("Authored chair support proxy"):bpy.data.objects["Authored chair support proxy"].hide_render=activity not in ("sitting","sit_to_stand")
        if daily_props is not None:daily_props.visibility(activity)

for (activity,t),(expected,shoes) in replay_reference.items():
    choose_action(activity,t);err=nearest_error(evaluated(skin),expected,2048)
    se=max(nearest_error(evaluated(bpy.data.objects[n]),v,len(v)) for n,v in shoes.items())
    checks.append({"activity_id":activity,"time_s":t,"phase":"baked_blend_action","max_bidirectional_error_m":err,"shoe_error_m":se})
for activity in (IDS if DAILY else ("walking","squatting","brushing_teeth")):
    if activity in actions:
        for t in (.3125,.7291666666666666):
            choose_action(activity,t)
            replay_reference[(activity,t)]=(evaluated(skin).copy(),{o.name:evaluated(o) for o in shoe_objects})
assert max(c["max_bidirectional_error_m"] for c in checks)<5e-5,"full-weight native/export-basis transport error"

if QUICK:
    save_json(OUT/"local-preflight.json",{"checks":checks,"export":export,"calibration":calibration,"qualification":"LOCAL_PREFLIGHT_ONLY; public pinned runtime still required"})
    log("PREFLIGHT_COMPLETE",{"case":CASE["id"],"worst_skin_error_m":max(c["max_bidirectional_error_m"] for c in checks)});sys.exit(0)

# Actual product scene and CPU rendering; no source mesh edits.
scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=6;scene.cycles.use_denoising=not bool(os.environ.get("R245_LOCAL_NO_DENOISE"));scene.cycles.max_bounces=3
scene.render.resolution_x=420;scene.render.resolution_y=560;scene.render.resolution_percentage=100;scene.render.image_settings.file_format="PNG"
scene.world=bpy.data.worlds.new("Neutral motion studio");scene.world.use_nodes=True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value=(.035,.05,.075,1);scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value=.5
scene.view_settings.view_transform="AgX"
def look(obj,point):obj.rotation_euler=(Vector(point)-obj.location).to_track_quat("-Z","Y").to_euler()
bpy.ops.object.camera_add(location=(3,-6,2.2));camera=bpy.context.object;camera.name="Motion review camera";camera.data.type="ORTHO";scene.camera=camera
for loc,power,size in (((3,-4,5),550,4),((-3,-1,3),400,3),((1,4,3),650,3)):
    bpy.ops.object.light_add(type="AREA",location=loc);o=bpy.context.object;o.data.energy=power;o.data.shape="DISK";o.data.size=size;look(o,(0,0,.8))
floor=make_mesh("Ground y0",[(-20,-20,-.0005),(20,-20,-.0005),(20,20,-.0005),(-20,20,-.0005)],[(0,1,2),(0,2,3)],material("Matte floor",(.105,.135,.18)))
chair_objects=[]
chair_spec=clip_inputs["sit_to_stand"]["props"][0]
cvv=[];cff=[];center=Vector(chair_spec["seat_center_m"]);center.y-=.025
add_box(cvv,cff,center,chair_spec["seat_width_m"],chair_spec["seat_depth_m"],.025)
for x in (-.42,.42):
    for z in (-.42,.42):
        foot=center+Vector((x*chair_spec["seat_width_m"],-center.y,z*chair_spec["seat_depth_m"]))
        add_box(cvv,cff,foot,.025,.025,center.y)
chair=make_mesh("Authored chair support proxy",[tup(bv(v)) for v in cvv],cff,material("Chair",(.34,.25,.13)));chair_objects.append(chair)
def render(activity,t,path,detail=False,preview=False):
    choose_action(activity,t);chair.hide_render=activity not in ("sitting","sit_to_stand")
    brush.hide_render=activity not in ("brushing_teeth","walking_brush")
    if daily_props is not None:daily_props.visibility(activity)
    vertices=evaluated(skin);center=(vertices.min(0)+vertices.max(0))/2
    if detail:center=np.array([center[0],center[1],.14]);camera.data.ortho_scale=.67
    else:camera.data.ortho_scale=MORPH["stature_m"]*1.20;center[2]=MORPH["stature_m"]*.47
    camera.location=center+np.array([2.5,-5,1.1] if not detail else [1.8,-3,.65]);look(camera,center)
    scene.render.resolution_x=288 if preview else 420;scene.render.resolution_y=384 if preview else 560;scene.cycles.samples=3 if preview else 8
    scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)

render_specs=[("standing",0,"01-standing"),("sit_to_stand",0,"02-sitting"),("squatting",2,"03-squat"),("walking",.55,"04-walk"),("brushing_teeth",.5,"05-brushing"),("standing",0,"06-footwear")]
if DAILY:render_specs += [("crouching",0,"07-crouching"),("jogging",.3,"08-jogging"),("running",.28,"09-running"),("showering",.5,"10-showering"),("eating_ice_cream_cone",1.5,"11-ice-cream")]
for activity,t,name in render_specs:render(activity,t,OUT/(name+".png"),name=="06-footwear")
video_case=DAILY or CASE["id"] in ("male155flat","male185stiletto","female155stiletto","female185flat")
video_manifest=[]
if video_case:
    for activity in (("sit_to_stand","crouching","jogging","running","showering","eating_ice_cream_cone") if DAILY else ("walking","squatting","walking_brush")):
        folder=OUT/(activity+"-frames");folder.mkdir()
        duration=clip_inputs[activity]["instance"]["duration_s"]
        for i,t in enumerate(np.arange(0,duration,1/8)):render(activity,float(t),folder/(str(i).zfill(4)+".png"),preview=True)
        video_manifest.append({"activity_id":activity,"folder":folder.name,"fps":8,"frames":i+1,"scope":"Actual CPU rendered authored kinematic prototype; no realism acceptance."})
for row in activity_state:
    row["render"]="VIDEO_8_FPS_AND_STILL" if row["activity_id"] in [v["activity_id"] for v in video_manifest] else "STILL" if row["activity_id"] in [x[0] for x in render_specs] else "NOT_RENDERED"
    row["glb_export"]="SOURCE_ATTRIBUTES_EXACT_OBSERVED_POSE_BAKED";row["blend_replay"]="PASS_SAMPLED_ACTION_REPLAY"

choose_action("walking",.55)
scene.frame_start=1;scene.frame_end=int(1+clip_inputs["walking"]["instance"]["duration_s"]*24)
source_text=bpy.data.texts.new("R245 consumer source");source_text.write(Path(__file__).read_text())
notes=bpy.data.texts.new("R245 scope and replay");notes.write(json.dumps({"case":CASE,"activities":activity_state,"source_rig":rig.name,"actions":actions,"limitations":["Authored kinematic prototypes, not measured mocap or dynamics","Rigid footwear support proxies, not fitted shoe designs","Choose the original rig action in the Action Editor; 163 original bones retained","Separate IK controls are construction controls; source actions are baked snapshots","No anatomy, self-collision, dental contact, balance, breathing or physiology acceptance"]},indent=2))
blend=OUT/"activity-prototypes.blend";bpy.ops.wm.save_as_mainfile(filepath=str(blend),compress=True)
rig_name=rig.name;skin_name=skin.name
bpy.ops.wm.open_mainfile(filepath=str(blend));scene=bpy.context.scene;rig=bpy.data.objects[rig_name];skin=bpy.data.objects[skin_name];shoe_objects=[bpy.data.objects[o] for o in ["Shoe rigid L","Shoe toe L","Shoe rigid R","Shoe toe R"]]
refresh_markers()
for (activity,t),(expected,shoes) in replay_reference.items():
    choose_action(activity,t);error=nearest_error(evaluated(skin),expected,2048)
    shoe_error=max(nearest_error(evaluated(bpy.data.objects[n]),v,len(v)) for n,v in shoes.items())
    checks.append({"phase":"saved_blend_reopened","activity_id":activity,"time_s":t,"max_bidirectional_error_m":error,"shoe_error_m":shoe_error})
for clip in observations["cases"][0]["clips"]:
    rows=[]
    for row in clip["frames"]:
        choose_action(clip["activity_id"],row["time_s"]);new=observe(row["target"],row["resolved_task"]);new["replay_phase"]="saved_blend_reopened";rows.append(new)
    clip["frames"]=rows
save_json(OUT/"reopened-blend-observations.json",observations)

# Reimport the packed GLB independently, including all animation slots and shoe meshes.
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(OUT/"activity-prototypes.glb"))
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
for (activity,t),(expected,shoes) in replay_reference.items():
    apply_import_action(import_rig,activity)
    f=float(import_rig.animation_data.action.frame_range[0])+t*24;scene.frame_set(int(f),subframe=f-int(f));update()
    error=nearest_error(evaluated(import_skin),expected,2048)
    shoe_error=max(nearest_error(evaluated(bpy.data.objects[n]),v,len(v)) for n,v in shoes.items())
    checks.append({"phase":"baked_glb_reimported","activity_id":activity,"time_s":t,"max_bidirectional_error_m":error,"shoe_error_m":shoe_error})
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

worst=max(max(c["max_bidirectional_error_m"],c.get("shoe_error_m",0)) for c in checks)
transport="PASS" if worst<5e-5 else "FAIL"
receipt={"schema":"oneirifact.motion-consumer-receipt/v1","status":transport+"_NATIVE_CONSUMER_TRANSPORT","realism":"HOLD_AUTHORED_KINEMATIC_PROTOTYPE","case":CASE,
 "source_head_commit":os.environ.get("SOURCE_HEAD_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),"blender_version":bpy.app.version_string,
 "time_mapping":{"authored_blend":"frame=1+24*time_s","imported_glb":"frame=observed_action_first_frame+24*time_s","fractional_seek":"Two off-key samples each for dense walking, squat and brush, compared after reopen and reimport"},
 "activities":activity_state,"videos":video_manifest,"export":export,"checks":checks,"marker_import_guards":marker_import_guards,"worst_transport_error_m":worst,"transport_tolerance_m":5e-5,
 "contact_acceptance":"SEPARATE_INDEPENDENT_CRITIC_PENDING","geometry_preservation":"Original 13380 vertices/26756 triangles,163 source bones,3packed influence sets retained; source rest-bind fitting precedes animation.",
 "props":{"chair":"Static .blend/render context only; seat/body contact unqualified","toothbrush":"Actual wrist-bone-parented rigid .blend/render prop; actual tip-to-mouth proxy distance observed; excluded from GLB because per-clip prop visibility is not encoded","finger_grip_and_dental_contact":"NOT_QUALIFIED"},
 "limitations":["Eight uniform-stature source combinations plus one actual nonuniform male-older donor morph; no universal morph coverage","Footwear meshes are rigid support proxies, not fitted shoes","Toe articulation uses middle-toe source joint for shoe hinge; original five toe roots retain their own heads","No measured human motion, forces, balance, joint limits, self-collision or soft tissue validation","Mouth/head and arm-neutral targets are authored proxies; no dental contact admission","Skin-only: anatomical skeletal meshes and all internal physiology omitted"],"files":{}}
if DAILY:
    receipt["extension"]={"id":"r248-dense-daily-activity","parent_head":"7fc8141fef8e2133ecceb2474005e82da4da69ad","coverage":"All12 activity/composition entries sampled at authored24fps; fractional replay probes for every entry","props":"Actual rigid wrist-parented cone with fixed authored wrist orientation, evaluated tip; static shower head/context lines. Native scene/render only; GLB retains body/shoe animation. Grip, oral contact, water mechanics and realism remain unqualified."}
    receipt["time_mapping"]["fractional_seek"]="Two off-key samples for every authored activity, compared after reopen and reimport"
    receipt["props"]["ice_cream_cone"]="Original rigid wrist-parented mesh; evaluated scoop-tip to mouth-proxy distances; no eating/contact acceptance"
    receipt["props"]["shower"]="Original static head and context lines; no fluid simulation or wet-contact claim"
for path in sorted(OUT.iterdir()):
    if path.is_file() and path.name!="consumer-receipt.json":receipt["files"][path.name]={"bytes":path.stat().st_size,"sha256":sha(path.read_bytes())}
save_json(OUT/"consumer-receipt.json",receipt)
log("COMPLETE",{"case":CASE["id"],"status":receipt["status"],"worst_transport_error_m":worst,"clips":len(clips),"blend_bytes":blend.stat().st_size})
assert transport=="PASS","independent saved/reimported consumer transport exceeded tolerance"
