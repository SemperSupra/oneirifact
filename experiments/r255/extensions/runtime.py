"""Source-preserving native actors and exact multi-skin GLB transport."""
import ast,copy,hashlib,json,math,sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix,Quaternion,Vector
from mathutils.kdtree import KDTree
HERE=Path(__file__).resolve().parent
PARENT=HERE/"vendor"/"r246_native"
PROVENANCE=json.loads((PARENT/"provenance.json").read_text())
for row in PROVENANCE["files"]:
    raw=(PARENT/row["path"]).read_bytes()
    assert len(raw)==row["bytes"] and hashlib.sha256(raw).hexdigest()==row["sha256"],row["path"]
sys.path.insert(0,str(PARENT))
from gltf import parse,read,add,encode,sha,worlds
from choreography import hands
C=Matrix(((1,0,0,0),(0,0,-1,0),(0,1,0,0),(0,0,0,1)));CI=C.inverted()
def bv(p):return Vector((float(p[0]),float(-p[2]),float(p[1])))
def cv(p):return np.array([p[0],p[2],-p[1]],float)
def B(R):return C@Matrix(np.asarray(R).tolist()).to_4x4()@CI
def update():bpy.context.view_layer.update()
def evaluated(obj):
    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh();a=np.empty(len(mesh.vertices)*3)
    mesh.vertices.foreach_get("co",a);a=a.reshape(-1,3);W=np.array(ev.matrix_world);a=a@W[:3,:3].T+W[:3,3];ev.to_mesh_clear();return a
def material(name,color):
    m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=(*color,1);p=m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value=(*color,1);p.inputs["Roughness"].default_value=.55;return m
def quatxy(q):return [float(q.x),float(q.y),float(q.z),float(q.w)]
def curves(action):
    return list(action.fcurves) if hasattr(action,"fcurves") else [fc for l in action.layers for s in l.strips for b in s.channelbags for fc in b.fcurves]
def action_set(obj,action):
    obj.animation_data_create();obj.animation_data.action=action
    if hasattr(obj.animation_data,"action_slot") and len(action.slots):obj.animation_data.action_slot=action.slots[0]
def frame_set(t,origin=1):
    f=origin+24*t;bpy.context.scene.frame_set(int(f),subframe=f-int(f));update()

# Reuse only named pure function definitions, never the parent's top-level job.
REUSED=("make_chain","solve_control","world","position","pose","capture_source_world","cpu_skin")
PARENT_RAW=(PARENT/"witness.py").read_bytes();PARENT_SHA=sha(PARENT_RAW)
TREE=ast.parse(PARENT_RAW);DEFS=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in REUSED]
assert {n.name for n in DEFS}==set(REUSED)
HELPER_CODE=compile(ast.Module(body=DEFS,type_ignores=[]),str(PARENT/"witness.py"),"exec")

class Actor:
    def __init__(self,folder,identity,color):
        self.id=identity;self.folder=Path(folder);self.case=json.loads((self.folder/"case.json").read_text());self.meta=copy.deepcopy(self.case["morphology"])
        raw=(self.folder/"bound-source.glb").read_bytes();assert sha(raw)==self.meta["source_bind_sha256"]
        self.doc,self.bin=parse(raw);self.source_world,self.parents=worlds(self.doc);self.names=[n["name"] for n in self.doc["nodes"][:163]]
        before=set(bpy.context.scene.objects);bpy.ops.import_scene.gltf(filepath=str(self.folder/"bound-source.glb"));new=set(bpy.context.scene.objects)-before
        self.rig=next(o for o in new if o.type=="ARMATURE");self.skin=next(o for o in new if o.type=="MESH" and any(m.type=="ARMATURE" for m in o.modifiers))
        self.rig.name=identity+" source rig";self.skin.name=identity+" source exterior"
        assert len(self.rig.data.bones)==163 and len(self.skin.data.vertices)==13380 and len(self.skin.data.polygons)==26756
        for o in new:
            if o!=self.skin and o.type=="MESH":o.hide_render=True;o.hide_set(True)
        for pb in self.rig.pose.bones:pb.rotation_mode="QUATERNION"
        self.rest={n:self.rig.matrix_world@self.rig.data.bones[n].matrix_local for n in self.names};self.rest_inv={n:m.inverted() for n,m in self.rest.items()}
        attrs=self.doc["meshes"][0]["primitives"][0]["attributes"];self.attrs=attrs
        self.verts=read(self.doc,self.bin,attrs["POSITION"]);self.joints=np.concatenate([read(self.doc,self.bin,attrs["JOINTS_"+str(i)]) for i in range(3)],axis=1)
        self.weights=np.concatenate([read(self.doc,self.bin,attrs["WEIGHTS_"+str(i)]) for i in range(3)],axis=1)
        self.ib=read(self.doc,self.bin,self.doc["skins"][0]["inverseBindMatrices"]).reshape(-1,4,4).transpose(0,2,1)
        assert self.weights.shape==(13380,12) and int((self.weights>0).sum(1).max())==9
        self.index_guard=float(np.max(np.linalg.norm(evaluated(self.skin)-self.verts[:,[0,2,1]]*[1,-1,1],axis=1)));assert self.index_guard<3e-6
        env=dict(globals());env.update(scene=bpy.context.scene,rig=self.rig,REST=self.rest,REST_INV=self.rest_inv,RIG_INV=self.rig.matrix_world.inverted(),NAMES=self.names,
            SOURCE_WORLD=self.source_world,source_vertices=self.verts,source_indices=self.joints,source_weights=self.weights,inverse_bind=self.ib,controls={})
        exec(HELPER_CODE,env);self.e=env;self.controls=env["controls"]
        for side in ("L","R"):
            for part,joints in (("leg",("upperleg01","lowerleg01","foot")),("arm",("upperarm01","lowerarm01","wrist"))):
                self.controls[(part,side)]=env["make_chain"](identity+" IK "+part+side,*[self.rest[n+"."+side].translation for n in joints])
        self.skin.data.materials.clear();self.skin.data.materials.append(material(identity+" untextured source",color))
        for p in self.skin.data.polygons:p.use_smooth=True
        self.meta["shoulders_m"]={s:cv(self.rest["upperarm01."+s].translation).tolist() for s in ("L","R")}
        self.meta["wrists_m"]={s:cv(self.rest["wrist."+s].translation).tolist() for s in ("L","R")}
        self.anchor_ids={};self.palm_normals={};self.palm_offsets={};self.hand_ids={};self.foot_ids={};self.meta["foot_skin_offsets_m"]={}
        h=self.meta["stature_m"]
        def select(center,names,normal=None):
            ni={self.names.index(n) for n in names};membership=np.isin(self.joints,list(ni));w=(self.weights*membership).sum(1);ids=np.flatnonzero(w>.5)
            if not len(ids):raise ValueError("No admitted source vertices for "+str(names))
            dist=np.linalg.norm(self.verts[ids]-center,axis=1)
            return int(ids[np.argmin(dist)]),ids
        for s in ("L","R"):
            wrist=np.array(self.meta["wrists_m"][s]);middle=cv(self.rest["finger3-1."+s].translation)
            across=cv(self.rest["finger2-1."+s].translation)-cv(self.rest["finger5-1."+s].translation)
            forward=middle-wrist;normal=np.cross(forward,across);normal/=np.linalg.norm(normal)
            if normal[2]<0:normal=-normal
            center=wrist+.65*forward+normal*.007
            names=[n for n in self.names if (n=="wrist."+s or n.startswith("finger") and n.endswith("."+s))]
            vid,ids=select(center,names);self.anchor_ids["palm."+s]=vid;self.hand_ids[s]=ids
            self.palm_normals[s]=normal;self.palm_offsets[s]=self.verts[vid]-wrist
            _,ids=select(np.array(self.meta["ankles_m"][s]),[n for n in self.names if n=="foot."+s or n.startswith("toe") and n.endswith("."+s)])
            self.foot_ids[s]=ids
            self.meta["foot_skin_offsets_m"][s]=(self.verts[ids]-np.array(self.meta["ankles_m"][s])).tolist()
            for region in ("heel","forefoot","toe"):
                center=np.array(self.meta["ankles_m"][s])+self.meta["feet"][s][region+"_from_ankle_m"]
                self.anchor_ids[region+"."+s]=int(ids[np.argmin(np.linalg.norm(self.verts[ids]-center,axis=1))])
        for key,center,names in (
            ("chest",[0,.74*h,.09*h],["spine01","spine02","spine03"]),
            ("back",[0,.70*h,-.06*h],["spine02","spine03","spine04"]),
            ("shoulder",[.12*h,.78*h,0],["clavicle.L","shoulder01.L","upperarm01.L"]),
            ("knee",cv(self.rest["lowerleg01.L"].translation),["upperleg02.L","lowerleg01.L"])):
            self.anchor_ids[key]=select(np.asarray(center),names)[0]
        self.poses=[];self.worlds=[];self.rows=[];self.times=[];self.action=None;self.raw_crossings=[]
    def point(self,n):return self.e["position"](n)
    def world(self,n):return self.e["world"](n)
    def pose(self,n,m):self.e["pose"](n,m)
    def geometry(self):return evaluated(self.skin)
    def anchors(self):
        a=self.geometry();return {k:cv(a[i]).tolist() for k,i in self.anchor_ids.items()}
    def stage(self,f):
        self.rig.animation_data_clear()
        for pb in self.rig.pose.bones:pb.matrix_basis=Matrix.Identity(4)
        update();R=B(f["R"]);hip0=bv(self.meta["hip_center_m"]);hip=bv(f["hip"])
        delta=Matrix.Translation(hip)@R@Matrix.Translation(-hip0);self.pose("root",delta@self.rest["root"]);update()
        for n in ("spine05","spine04","spine03","spine02","spine01"):
            W=self.world(n);Q=B(f["R"])@Matrix.Rotation(f["torso"]/5,4,"X")@Matrix.Rotation(f["twist"]/5,4,"Z")@B(f["R"]).inverted()
            self.pose(n,Matrix.Translation(W.translation)@Q@Matrix.Translation(-W.translation)@W);update()
        W=self.world("head");Q=B(f["R"])@Matrix.Rotation(f["head"],4,"X")@B(f["R"]).inverted()
        self.pose("head",Matrix.Translation(W.translation)@Q@Matrix.Translation(-W.translation)@W);update()
        self.foot_deltas={};self.reach={}
        for s in ("L","R"):
            target=bv(f["feet"][s]);pole=hip+R.to_3x3()@bv(f["knee_local"]+np.array([(.06 if s=="L" else -.06)*self.meta["stature_m"],0,0]))
            solved,ankle=self.e["solve_control"]("leg",s,delta,target,pole)
            for prefix,control in (("upperleg","proximal"),("lowerleg","distal")):
                for suffix in ("01","02"):self.pose(prefix+suffix+"."+s,solved[control]@self.rest[prefix+suffix+"."+s]);update()
            F=B(f["foot_R"][s]);F.translation=ankle-F.to_3x3()@self.rest["foot."+s].translation
            self.pose("foot."+s,F@self.rest["foot."+s]);update();self.foot_deltas[s]=F
            self.reach["ankle."+s]=float((ankle-target).length)
        self.frame=f
    def arms(self,partner=None,record=True):
        f=self.frame;shoulders={s:cv(self.point("upperarm01."+s)) for s in ("L","R")}
        targets,palms,contact=hands(self.meta,f,shoulders,partner=partner);self.contact_intents=f["contacts"]+contact
        for s,sign in (("L",1),("R",-1)):
            shoulder=self.point("upperarm01."+s);S=self.world("upperarm01."+s)@self.rest_inv["upperarm01."+s]
            handR=B(f["R"])
            if s in palms:
                # Orient actual source palm normal towards support surface/partner.
                n=bv(self.palm_normals[s]);goal=bv([0,-1,0] if f["hand_mode"] in ("push_up","cartwheel") else np.asarray(palms[s])-cv(shoulder))
                q=n.rotation_difference(goal.normalized());handR=q.to_matrix().to_4x4()
                target=bv(palms[s])-handR.to_3x3()@bv(self.palm_offsets[s])
            else:target=bv(targets[s])
            pole=shoulder+B(f["R"]).to_3x3()@bv([sign*.4*self.meta["stature_m"],-.1*self.meta["stature_m"],-.15*self.meta["stature_m"]])
            solved,end=self.e["solve_control"]("arm",s,S,target,pole)
            for prefix,control in (("upperarm","proximal"),("lowerarm","distal")):
                for suffix in ("01","02"):self.pose(prefix+suffix+"."+s,solved[control]@self.rest[prefix+suffix+"."+s]);update()
            if s in palms:
                handR.translation=end-handR.to_3x3()@self.rest["wrist."+s].translation;self.pose("wrist."+s,handR@self.rest["wrist."+s])
            else:self.pose("wrist."+s,solved["distal"]@self.rest["wrist."+s])
            update();self.reach["wrist."+s]=float((self.point("wrist."+s)-target).length)
            if f["fingers"]:
                for finger in range(1,6):
                    for segment,angle in ((1,50),(2,65),(3,40)):
                        n=f"finger{finger}-{segment}.{s}";pb=self.rig.pose.bones[n]
                        pb.rotation_mode="QUATERNION";pb.rotation_quaternion=Quaternion((1,0,0),math.radians(angle)*f["fingers"])
                update()
        if f["diagnostic"]=="source_rest":
            for pb in self.rig.pose.bones:pb.matrix_basis=Matrix.Identity(4)
            update()
        a=self.geometry();canonical=a[:,[0,2,1]]*[1,1,-1]
        contacts=[]
        for c in self.contact_intents:
            r=copy.deepcopy(c);part=c["actor_part"]
            if part.startswith("palm"):
                vid=self.anchor_ids[part];actual=canonical[vid];side=part[-1];ids=self.hand_ids[side];lowest=int(ids[np.argmin(canonical[ids,1])])
                r.update(source_vertex_id=vid,actual_point_m=actual.tolist(),distance_m=float(np.linalg.norm(actual-c["point_m"])),
                    actual_hand_skin_min_y_m=float(canonical[lowest,1]),minimum_hand_source_vertex_id=lowest,minimum_hand_source_point_m=canonical[lowest].tolist())
            else:
                s=part[-1];r.update(source_vertex_subset_count=len(self.foot_ids[s]),actual_min_y_m=float(canonical[self.foot_ids[s],1].min()),
                    source_contact_points={region:{"vertex_id":self.anchor_ids[region+"."+s],"point_m":canonical[self.anchor_ids[region+"."+s]].tolist()} for region in ("heel","forefoot","toe")})
            contacts.append(r)
        lengths={};subdivision=0.
        for s in ("L","R"):
            for part,a0,b0,c0 in (("leg","upperleg","lowerleg","foot"),("arm","upperarm","lowerarm","wrist")):
                for prefix,endname in ((a0,b0+"01"),(b0,c0)):
                    n=prefix+"01."+s;e=endname+"."+s;lengths[n]=float(abs((self.point(n)-self.point(e)).length-(self.rest[n].translation-self.rest[e].translation).length))
                    n2=prefix+"02."+s;parent=self.rig.data.bones[n2].parent.name
                    bind=(self.rest[parent].inverted()@self.rest[n2]).to_quaternion();now=(self.world(parent).inverted()@self.world(n2)).to_quaternion()
                    subdivision=max(subdivision,float(bind.rotation_difference(now).angle))
        row={"time_s":f["time_s"],"actor":self.id,"root_hip_m":f["hip"].tolist(),"actual_hip_center_m":cv((self.point("upperleg01.L")+self.point("upperleg01.R"))/2).tolist(),"contacts":contacts,"target_errors_m":self.reach.copy(),"limb_length_drift_m":lengths,
             "actual_ankles_m":{s:cv(self.point("foot."+s)).tolist() for s in ("L","R")},
             "intermediate_relative_rotation_error_rad":subdivision,"whole_skin_min_y_m":float(canonical[:,1].min()),"diagnostic":f["diagnostic"]}
        if record:
            self.rows.append(row);self.times.append(f["time_s"]);self.worlds.append(self.e["capture_source_world"]())
            self.poses.append([(self.rig.pose.bones[n].location.copy(),self.rig.pose.bones[n].rotation_quaternion.copy()) for n in self.names])
        return row
    def bake(self,activity):
        self.rig.animation_data_clear();action=bpy.data.actions.new(self.id+" / "+activity);action.use_fake_user=True;action_set(self.rig,action);previous={};corrected=0
        for i,(t,poses) in enumerate(zip(self.times,self.poses)):
            for n,(loc,raw) in zip(self.names,poses):
                q=raw.copy()
                if n in previous and previous[n].dot(q)<0:
                    self.raw_crossings.append({"bone":n,"start_s":self.times[i-1],"end_s":t,"midpoint_s":(self.times[i-1]+t)/2,"dot":float(previous[n].dot(q))});q.negate();corrected+=1
                assert n not in previous or previous[n].dot(q)>=0
                pb=self.rig.pose.bones[n];pb.location=loc;pb.rotation_quaternion=q;previous[n]=q.copy()
                pb.keyframe_insert("location",frame=1+24*t,group=n);pb.keyframe_insert("rotation_quaternion",frame=1+24*t,group=n)
        for fc in curves(action):
            for k in fc.keyframe_points:k.interpolation="LINEAR"
        self.action=action;return {"corrected_keys":corrected,"raw_crossings":self.raw_crossings,"native_interpolation":"LINEAR, hemisphere aligned"}

def merge_export(actors,activity,props,path):
    d={"asset":{"version":"2.0","generator":"Oneirifact R255 full-weight observed native actors"},"buffers":[{"byteLength":0}],"bufferViews":[],"accessors":[],"nodes":[],"meshes":[],"skins":[],"materials":[],"scenes":[{"nodes":[]}],"scene":0,"animations":[]}
    b=bytearray();anim={"name":activity,"samplers":[],"channels":[]};offsets=[]
    for actor in actors:
        src=copy.deepcopy(actor.doc);off={k:len(d[k]) for k in ("bufferViews","accessors","nodes","meshes","skins","materials")};offsets.append(off)
        b.extend(b"\0"*(-len(b)%4));byteoff=len(b);b.extend(actor.bin)
        for v in src["bufferViews"]:v["byteOffset"]=v.get("byteOffset",0)+byteoff;v["buffer"]=0;d["bufferViews"].append(v)
        for a in src["accessors"]:a["bufferView"]+=off["bufferViews"];d["accessors"].append(a)
        for m in src.get("materials",[]):d["materials"].append(m)
        color=list(actor.skin.data.materials[0].diffuse_color);d["materials"].append({"name":actor.id+" exterior","pbrMetallicRoughness":{"baseColorFactor":color,"metallicFactor":0,"roughnessFactor":.55}});mat=len(d["materials"])-1
        for m in src["meshes"]:
            m["name"]=actor.id+" exterior"
            for p in m["primitives"]:
                p["attributes"]={k:v+off["accessors"] for k,v in p["attributes"].items()};p["indices"]+=off["accessors"];p["material"]=mat
            d["meshes"].append(m)
        for n in src["nodes"]:
            n["name"]=actor.id+"__"+n.get("name","node");n["extras"]={"source_actor":actor.id}
            if "children" in n:n["children"]=[i+off["nodes"] for i in n["children"]]
            if "mesh" in n:n["mesh"]+=off["meshes"]
            if "skin" in n:n["skin"]+=off["skins"]
            d["nodes"].append(n)
        for skin in src["skins"]:
            skin["joints"]=[i+off["nodes"] for i in skin["joints"]];skin["inverseBindMatrices"]+=off["accessors"]
            if "skeleton" in skin:skin["skeleton"]+=off["nodes"]
            d["skins"].append(skin)
        d["scenes"][0]["nodes"].extend(i+off["nodes"] for i in src["scenes"][src.get("scene",0)]["nodes"])
        inp=add(d,b,np.array(actor.times,dtype="<f4").reshape(-1,1),kind="SCALAR",bounds=True)
        W=np.array(actor.worlds)
        for ni in range(163):
            ms=np.array([np.linalg.inv(row[actor.parents[ni]])@row[ni] if ni in actor.parents and actor.parents[ni]<163 else row[ni] for row in W])
            q=np.array([quatxy(Matrix(m.tolist()).to_quaternion()) for m in ms])
            for i in range(1,len(q)):
                if q[i-1]@q[i]<0:q[i]*=-1
            for channel,values,kind in (("translation",ms[:,:3,3],"VEC3"),("rotation",q,"VEC4")):
                output=add(d,b,values.astype("<f4"),kind=kind);anim["channels"].append({"sampler":len(anim["samplers"]),"target":{"node":off["nodes"]+ni,"path":channel}})
                anim["samplers"].append({"input":inp,"output":output,"interpolation":"LINEAR"})
    for prop in props:
        v=np.asarray(prop["vertices"],dtype="<f4");tri=np.asarray(prop["triangles"],dtype="<u4").reshape(-1,1)
        pos=add(d,b,v,target=34962,bounds=True);idx=add(d,b,tri,kind="SCALAR",component=5125,target=34963)
        mat=len(d["materials"]);d["materials"].append({"name":prop["name"],"doubleSided":True,"pbrMetallicRoughness":{"baseColorFactor":[*prop["color"],1],"metallicFactor":0,"roughnessFactor":.7}})
        mesh=len(d["meshes"]);d["meshes"].append({"name":prop["name"],"primitives":[{"attributes":{"POSITION":pos},"indices":idx,"material":mat}]})
        node=len(d["nodes"]);d["nodes"].append({"name":prop["name"],"mesh":mesh});d["scenes"][0]["nodes"].append(node)
        if prop.get("matrices"):
            ms=np.array(prop["matrices"]);q=np.array([quatxy(Matrix(m.tolist()).to_quaternion()) for m in ms])
            for i in range(1,len(q)):
                if q[i-1]@q[i]<0:q[i]*=-1
            inp=add(d,b,np.array(actors[0].times,dtype="<f4").reshape(-1,1),kind="SCALAR",bounds=True)
            for ch,values,kind in (("translation",ms[:,:3,3],"VEC3"),("rotation",q,"VEC4")):
                out=add(d,b,values.astype("<f4"),kind=kind);anim["channels"].append({"sampler":len(anim["samplers"]),"target":{"node":node,"path":ch}});anim["samplers"].append({"input":inp,"output":out,"interpolation":"LINEAR"})
    d["animations"]=[anim];packed=encode(d,b);path.write_bytes(packed);dd,bb=parse(packed)
    for actor,off in zip(actors,offsets):
        attrs=dd["meshes"][off["meshes"]]["primitives"][0]["attributes"]
        assert all(np.array_equal(read(dd,bb,attrs[k]),read(actor.doc,actor.bin,v)) for k,v in actor.attrs.items())
        assert np.array_equal(read(dd,bb,dd["meshes"][off["meshes"]]["primitives"][0]["indices"]),read(actor.doc,actor.bin,actor.doc["meshes"][0]["primitives"][0]["indices"]))
        assert np.array_equal(read(dd,bb,dd["skins"][off["skins"]]["inverseBindMatrices"]),read(actor.doc,actor.bin,actor.doc["skins"][0]["inverseBindMatrices"]))
    return {"meshes":len(dd["meshes"]),"skins":len(dd["skins"]),"joints_per_skin":[len(s["joints"]) for s in dd["skins"]],"total_skin_vertices":13380*len(actors),"source_weight_sets":["JOINTS_0/WEIGHTS_0","JOINTS_1/WEIGHTS_1","JOINTS_2/WEIGHTS_2"],"maximum_positive_influences":9,"source_attributes_and_inverse_binds_bit_identical":True,"sha256":sha(packed),"bytes":len(packed)}
