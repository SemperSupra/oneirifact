"""Actual CPU Blender products, saved/reimported interpolation audit and renders."""
import json,math,os,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from runtime import *
from choreography import GROUPS,DURATION,PAIRED,NOTES,POSES,sample,window,rot
from contact_fit import fit,contact_episodes

args=sys.argv[sys.argv.index("--")+1:];INPUT=Path(args[0]);OUT=Path(args[1]);GROUP=args[2]
QUICK="--quick" in args;ONLY=next((x.split("=",1)[1] for x in args if x.startswith("--only=")),None)
NO_RENDER=QUICK or "--no-render" in args
OUT.mkdir(parents=True,exist_ok=True)
def save(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+"\n")
def log(k,x):print("R255_"+k,json.dumps(x,allow_nan=False),flush=True)
def actual_mesh(name,vertices,triangles,color):
    m=bpy.data.meshes.new(name);m.from_pydata([bv(p) for p in vertices],[],triangles);m.update();o=bpy.data.objects.new(name,m);bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(material(name,color));return o
BOX=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
def box(name,center,width,height,depth,color):
    v=[np.array(center)+[dx*width/2,dy*height/2,dz*depth/2] for dy in (-1,1) for dx,dz in ((-1,-1),(1,-1),(1,1),(-1,1))]
    return {"name":name,"vertices":[p.tolist() for p in v],"triangles":BOX,"color":color,"object":actual_mesh(name,v,BOX,color),"matrices":[]}
def attach_props(actors,activity):
    props=[box("Visible support mat",[0,-.025,0],5.,.05,5.,(.16,.22,.28))]
    if activity=="trip_fall":props.append(box("Trip obstacle proxy",[0,.035,.17],.65,.07,.08,(.85,.30,.07)))
    if activity=="stiletto_heel_break":
        a=actors[0]
        for s in ("L","R"):
            foot=a.meta["feet"][s];ankle=np.array(a.meta["ankles_m"][s]);heel=ankle+foot["heel_from_ankle_m"];fore=ankle+foot["forefoot_from_ankle_m"]
            # Fixed source-local support proxies. Geometry is calibrated once at t=0.
            f=sample(a.meta,activity,0);R=f["foot_R"][s];worldankle=f["feet"][s]
            heelw=worldankle+R@(heel-ankle);forew=worldankle+R@(fore-ankle)
            for region,point,height,width,depth in (("heel",heelw,.10,.012,.018),("forefoot",forew,.008,.075,.065)):
                center=point-np.array([0,height/2,0]);p=box(s+" "+region+" support proxy",center,width,height,depth,(.55,.08,.13))
                # Convert calibrated world vertices back into original foot bind coordinates.
                delta=np.eye(4);delta[:3,:3]=R;delta[:3,3]=worldankle-R@ankle;inv=np.linalg.inv(delta)
                p["vertices"]=[(inv@np.r_[v,1])[:3].tolist() for v in p["vertices"]]
                for vert,co in zip(p["object"].data.vertices,p["vertices"]):vert.co=bv(co)
                p.update(side=s,region=region,calibrated_delta=delta.tolist());props.append(p)
    return props
def move_props(props,actors,activity,t):
    for p in props:
        if "side" not in p:continue
        a=actors[0];M=CI@a.foot_deltas[p["side"]]@C
        if activity=="stiletto_heel_break" and p["side"]=="R" and p["region"]=="heel" and t>=1.4:
            # An explicit authored fragment trajectory, not a solver or force model.
            if "release_matrix" not in p:p["release_matrix"]=np.array(M)
            u=min((t-1.4)/1.2,1.);base=p["release_matrix"];M=Matrix(base.tolist());Q=Matrix(rot([0,0,1],1.3*u).tolist()).to_4x4()
            center=np.mean(p["vertices"],axis=0);pivot=Vector((base@np.r_[center,1])[:3])
            M=Matrix.Translation(pivot+Vector((.13*u,-.035*u,.08*u)))@Q@Matrix.Translation(-pivot)@M
        p["object"].matrix_world=C@M@CI;p["matrices"].append(np.array(M).tolist())
def bake_props(props,times):
    for p in props:
        if not p["matrices"]:continue
        obj=p["object"];obj.rotation_mode="QUATERNION";previous=None
        for t,m in zip(times,p["matrices"]):
            M=C@Matrix(m)@CI;loc,q,scale=M.decompose()
            if previous is not None and previous.dot(q)<0:q.negate()
            previous=q.copy();obj.location=loc;obj.rotation_quaternion=q
            obj.keyframe_insert("location",frame=1+24*t);obj.keyframe_insert("rotation_quaternion",frame=1+24*t)
        for fc in curves(obj.animation_data.action):
            for k in fc.keyframe_points:k.interpolation="LINEAR"
def look(obj,p):obj.rotation_euler=(Vector(p)-obj.location).to_track_quat("-Z","Y").to_euler()
def studio(bounds):
    scene=bpy.context.scene;scene.render.engine="CYCLES";scene.cycles.device="CPU";scene.cycles.samples=4;scene.cycles.max_bounces=2;scene.cycles.use_denoising=bpy.app.version>=(5,2,0)
    scene.render.resolution_x=480;scene.render.resolution_y=360;scene.render.resolution_percentage=100;scene.render.image_settings.file_format="PNG"
    scene.world=bpy.data.worlds.new("Motion review studio");scene.world.use_nodes=True;scene.world.node_tree.nodes["Background"].inputs["Color"].default_value=(.035,.055,.085,1);scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value=.7
    scene.view_settings.view_transform="AgX"
    low,high=bounds;center=(low+high)/2
    bpy.ops.object.camera_add(location=center+np.array([3.8,-5.8,2.8]));camera=bpy.context.object;camera.data.type="ORTHO";camera.data.ortho_scale=max(2.3,float(np.linalg.norm(high-low))*1.10);look(camera,center);scene.camera=camera
    for offset,power in (([3,-4,5],650),([-3,-2,3],500),([1,3,4],700)):
        bpy.ops.object.light_add(type="AREA",location=center+offset);o=bpy.context.object;o.data.energy=power;o.data.size=4;look(o,center)
    return scene

all_receipts=[]
for activity in GROUPS[GROUP]:
    if ONLY and activity!=ONLY:continue
    started=time.time();folder=OUT/activity;folder.mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=24;scene.render.fps_base=1
    primary="female155flat" if GROUP=="support-events" else "male155flat" if GROUP=="acrobatics-combat" else "female185flat"
    specs=[(primary,"actor-a",(.19,.47,.57))]
    if activity in PAIRED:specs.append(("female155flat","actor-b",(.68,.34,.18)))
    actors=[Actor(INPUT/case,identity,color) for case,identity,color in specs];props=attach_props(actors,activity)
    duration=DURATION[activity];times=np.linspace(0,duration,round(duration*24)+1)
    if QUICK:times=np.linspace(0,duration,13)
    bounds=[np.ones(3)*np.inf,np.ones(3)*-np.inf];rawchecks=[];reference={};fit_records=[]
    for i,t in enumerate(times):
        frames=[sample(a.meta,activity,float(t),ai) for ai,a in enumerate(actors)]
        fit_records.extend(fit(actors,frames,activity))
        move_props(props,actors,activity,float(t))
        for a in actors:
            geom=a.geometry();bounds[0]=np.minimum(bounds[0],geom.min(0));bounds[1]=np.maximum(bounds[1],geom.max(0))
            if i in (0,len(times)//2,len(times)-1):
                cpu=a.e["cpu_skin"](a.worlds[-1]);err=float(np.linalg.norm(geom-cpu,axis=1).max());rawchecks.append({"actor":a.id,"time_s":float(t),"phase":"independent_full_weight_cpu_lbs","max_error_m":err});assert err<5e-5
        if i%24==0:log("POSE",{"clip":activity,"key":i,"total":len(times)})
    interpolation={a.id:a.bake(activity) for a in actors};bake_props(props,actors[0].times)
    inventory=merge_export(actors,activity,props,folder/"motion.glb")
    # Compare every between-key midpoint and three full keys. This specifically
    # catches the previously observed native quaternion long-path defect.
    probe_times=sorted(set([0.,duration/2,duration]+[(float(a)+float(b))/2 for a,b in zip(times[:-1],times[1:])]))
    if QUICK:probe_times=sorted(set([0.,duration/2,duration]+[c["midpoint_s"] for a in actors for c in a.raw_crossings]))
    for t in probe_times:
        frame_set(t);reference[t]={a.id:a.geometry().copy() for a in actors}
    scene=studio(bounds);scene.frame_start=1;scene.frame_end=round(1+duration*24);frame_set(duration*.42)
    note=bpy.data.texts.new("R255 scope, contacts and provenance");note.write(json.dumps({"activity":activity,"scope":NOTES[activity],"source_parent":"a8620c416070696fdd8d24d76464c8b30dfe9205","helper_source_sha256":PARENT_SHA,"reused_functions":REUSED,"original_bind":"Immutable source; pose matrices only","physics":"NOT_SIMULATED","realism":"HOLD","contacts":"Observed source vertex/subset diagnostics, not admitted contacts"},indent=2))
    native_names={a.id:{"rig":a.rig.name,"skin":a.skin.name,"action":a.action.name} for a in actors}
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/"motion.blend"),compress=True)
    if not NO_RENDER:
        renderfolder=folder/"frames";renderfolder.mkdir(exist_ok=True)
        vf=6 if activity!="diagnostic_poses" else 2
        for i,t in enumerate(np.arange(0,duration,1/vf)):
            frame_set(float(t));scene.render.filepath=str(renderfolder/f"{i:04d}.png");bpy.ops.render.render(write_still=True)
        video={"fps":vf,"frames":i+1,"duration_s":(i+1)/vf,"folder":"frames"}
    else:video=None
    # Actual save/reopen; compare exact all-source vertex order, no nearest-point surrogate.
    bpy.ops.wm.open_mainfile(filepath=str(folder/"motion.blend"));scene=bpy.context.scene
    for t,expected in reference.items():
        frame_set(t)
        for a in actors:
            skin=bpy.data.objects[native_names[a.id]["skin"]];err=float(np.linalg.norm(evaluated(skin)-expected[a.id],axis=1).max())
            rawchecks.append({"actor":a.id,"time_s":t,"phase":"saved_native_reopened","max_error_m":err})
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(folder/"motion.glb"));scene=bpy.context.scene;scene.render.fps=24;scene.render.fps_base=1
    imported={}
    for a in actors:
        rig=next(o for o in scene.objects if o.type=="ARMATURE" and a.id+"__root" in o.data.bones)
        skin=next(o for o in scene.objects if o.type=="MESH" and o.name.startswith(a.id+"__") and any(m.type=="ARMATURE" and m.object==rig for m in o.modifiers))
        # Blender may combine disjoint glTF skins into a 326-bone import rig.
        # Each original actor still has exactly its own 163 named bones/skin.
        assert len([n for n in rig.data.bones.keys() if n.startswith(a.id+"__")])==163 and len(skin.data.vertices)==13380
        coords=np.array([v.co[:] for v in skin.data.vertices]);assert np.max(np.linalg.norm(coords-a.verts[:,[0,2,1]]*[1,-1,1],axis=1))<3e-6
        candidates=[]
        for track in rig.animation_data.nla_tracks:
            track.mute=True
            if track.name==activity:
                for strip in track.strips:candidates.append((strip.action,getattr(strip,"action_slot",None)))
        assert len(candidates)==1,(activity,rig.name,[t.name for t in rig.animation_data.nla_tracks])
        action,slot=candidates[0];rig.animation_data.action=action
        if slot is not None:rig.animation_data.action_slot=slot
        imported[a.id]=(rig,skin,float(action.frame_range[0]))
    # Props likewise use their exact named action if importer put them in NLA.
    for obj in scene.objects:
        if obj.type=="ARMATURE" or not obj.animation_data:continue
        found=[]
        for track in obj.animation_data.nla_tracks:
            track.mute=True
            if track.name==activity:
                found.extend((s.action,getattr(s,"action_slot",None)) for s in track.strips)
        if found:
            assert len(found)==1;obj.animation_data.action=found[0][0]
            if found[0][1] is not None:obj.animation_data.action_slot=found[0][1]
    for t,expected in reference.items():
        for a in actors:
            rig,skin,start=imported[a.id];frame_set(t,start);err=float(np.linalg.norm(evaluated(skin)-expected[a.id],axis=1).max())
            rawchecks.append({"actor":a.id,"time_s":t,"phase":"glb_reimported_all_source_vertices","max_error_m":err})
    worst=max(x["max_error_m"] for x in rawchecks)
    observations={"schema":"oneirifact.motion-extension-observations/v1","activity":activity,"source_kind":"authored","native_sample_hz":24 if not QUICK else "SPARSE_LOCAL_PREFLIGHT",
        "actors":[{"id":a.id,"case":a.case,"source_anchor_vertex_ids":a.anchor_ids,"frames":a.rows} for a in actors],"limitations":NOTES[activity]}
    save(folder/"observations.json",observations)
    save(folder/"kinematic-fit.json",{"schema":"oneirifact.motion-extension-fit/v1","baseline_head":"8693d0463ba8f23bcb5470ce8d4748d1ea02fe76","baseline_run":46166127034,
        "method":"Explicit bounded evaluated-geometry root/ankle target fitting; source morphology, rest, weights and triangle geometry unchanged; no force solver.","records":fit_records})
    maxreach=max(v for a in actors for r in a.rows for v in r["target_errors_m"].values())
    palmerrors=[c["distance_m"] for a in actors for r in a.rows for c in r["contacts"] if "distance_m" in c]
    floor=min(r["whole_skin_min_y_m"] for a in actors for r in a.rows)
    metrics={"max_ik_target_error_m":maxreach,"max_declared_palm_contact_distance_m":max(palmerrors,default=None),"minimum_whole_skin_y_m":floor,
        "max_limb_length_drift_m":max(v for a in actors for r in a.rows for v in r["limb_length_drift_m"].values()),
        "max_intermediate_relative_rotation_error_rad":max(r["intermediate_relative_rotation_error_rad"] for a in actors for r in a.rows),
        "max_kinematic_root_displacement_m":max(float(np.linalg.norm(r["root_displacement_m"])) for r in fit_records),
        "max_kinematic_ankle_target_displacement_m":max(float(np.linalg.norm(v)) for r in fit_records for v in r["ankle_target_displacement_m"].values())}
    metrics["max_root_speed_m_s"]=max(float(np.linalg.norm(np.array(b["actual_hip_center_m"])-a["actual_hip_center_m"])/(b["time_s"]-a["time_s"])) for actor in actors for a,b in zip(actor.rows[:-1],actor.rows[1:]))
    metrics["max_adjacent_fit_offset_change_m"]=max(float(np.linalg.norm(np.array(b["kinematic_fit"]["root_displacement_m"])-a["kinematic_fit"]["root_displacement_m"])) for actor in actors for a,b in zip(actor.rows[:-1],actor.rows[1:]))
    metrics["max_total_root_change_from_public_baseline_m"]=max(float(np.linalg.norm(r["root_displacement_from_public_baseline_m"])) for r in fit_records)
    episodes={a.id:contact_episodes(a.rows) for a in actors};save(folder/"contact-episodes.json",episodes)
    receipt={"schema":"oneirifact.motion-extension-receipt/v1","id":activity,"group":GROUP,"source_head_commit":os.environ.get("SOURCE_HEAD_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),
        "source_parent":"a8620c416070696fdd8d24d76464c8b30dfe9205","baseline_head":"8693d0463ba8f23bcb5470ce8d4748d1ea02fe76","baseline_run":46166127034,"helper_source_sha256":PARENT_SHA,"reused_helpers":REUSED,"blender_version":bpy.app.version_string,"duration_s":duration,
        "native_fps":24,"video":video,"model_inventory":inventory,"actors":[{"id":a.id,"case_id":a.case["id"],"sex_variant":a.case["sex_variant"],"stature_m":a.meta["stature_m"],"source_bind_sha256":a.meta["source_bind_sha256"],"footwear":"10 cm heel and 8 mm forefoot rigid support proxies" if activity=="stiletto_heel_break" else "barefoot"} for a in actors],
        "transport":"PASS" if worst<5e-5 else "FAIL","worst_transport_error_m":worst,"transport_tolerance_m":5e-5,"time_map":"native frame=1+24t; GLB frame=observed imported action first frame+24t; fps_base=1",
        "probe_scope":"All between-key midpoints plus first/middle/last keys; all 13,380 corresponding skin vertices per actor; independent full-weight CPU LBS at three keys","checks":rawchecks,"interpolation":interpolation,
        "metrics":metrics,"contact_episodes":episodes,"kinematic_fit":"Explicit evaluated-geometry fit, with exact public baseline targets, corrected authored inputs, fitted targets and every displacement in kinematic-fit.json. Root projection can introduce lift, slide and abrupt offset changes; those are measured and remain unaccepted.","contact":"FAIL_DIAGNOSTIC" if maxreach>.03 or floor<-.025 or (palmerrors and max(palmerrors)>.03) else "HOLD_GEOMETRIC_PROXIMITY_ONLY",
        "realism":"HOLD_AUTHORED_KINEMATICS","physics":"NOT_SIMULATED","retarget":"NOT_APPLICABLE_ORIGINAL_AUTHORED_TARGETS","technique":"NOT_ACCEPTED",
        "diagnostic_pose_labels":POSES if activity=="diagnostic_poses" else None,"declared_pose_angles_deg":{"reference_t_shoulder_target":90,"reference_a_shoulder_target":45,"torso_twist":30,"torso_flexion":30,"finger_proximal":50,"finger_middle":65,"finger_distal":40} if activity=="diagnostic_poses" else None,
        "scope":NOTES[activity],"included_layers":["original full-weight source skin","163-bone source armature per actor","visible support context","authored skeletal kinematics"],"omitted_layers":["internal anatomical meshes","soft tissue or organs","contact forces","collision response","breathing physiology"],"elapsed_s":time.time()-started}
    save(folder/"receipt.json",receipt);all_receipts.append(receipt)
    log("COMPLETE",{"activity":activity,"actors":len(actors),"transport":receipt["transport"],"worst_m":worst,"contact":receipt["contact"],"metrics":metrics,"elapsed_s":receipt["elapsed_s"]})
    assert worst<5e-5,"native/GLB transport failed; negative evidence retained"
save(OUT/"batch-receipt.json",{"schema":"oneirifact.motion-extension-batch/v1","group":GROUP,"head":os.environ.get("SOURCE_HEAD_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID"),"clips":[{"id":r["id"],"transport":r["transport"],"contact":r["contact"],"worst_transport_error_m":r["worst_transport_error_m"]} for r in all_receipts]})
