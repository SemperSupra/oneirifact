"""Original daily-task review props; no grip, oral-contact or water mechanics.

These objects are native-scene/render evidence. The unchanged source-rig GLB
export deliberately omits per-activity prop visibility.
"""
import math
from mathutils import Matrix, Vector


class DailyProps:
    def __init__(self, g):
        self.g = g
        self.names = []
        self.cone_name = "R248 ice cream cone proxy"
        self.shower_name = "R248 shower head context"
        self.shower_names = []
        self.wrist_orientation = None
        bpy, morph = g["bpy"], g["MORPH"]
        frame = g["compile_clip"]("eating_ice_cream_cone", morph, g["SHOE"], fps=24)["frames"][0]
        resolved = g["solve"](frame)
        self.side = morph.get("dominant_hand", "R")
        self.wrist = "wrist." + self.side
        wrist_matrix = g["world"](self.wrist)
        self.wrist_orientation = wrist_matrix.to_3x3().to_4x4()
        inverse = (wrist_matrix @ g["REST_INV"][self.wrist]).inverted()
        spec = frame["props"][0]
        tip = g["bv"](spec["tip_target_m"])
        predicted = g["bv"](morph["landmarks_m"]["mouth"]) + g["bv"](frame["hip_center_m"]) - g["bv"](morph["hip_center_m"])
        tip += g["bv"](resolved["actual_mouth_proxy_m"]) - predicted
        axis = (tip - wrist_matrix.translation).normalized()
        u = axis.cross(Vector((1, 0, 0))).normalized()
        v = axis.cross(u).normalized()
        radius = spec["scoop_radius_m"]
        center = tip-axis*radius
        rim = center-axis*.25*radius
        cone_tip = rim-axis*spec["cone_height_m"]
        vertices, faces = [], []
        def point(p):
            vertices.append(tuple(inverse @ p))
            return len(vertices)-1
        cone_bottom = point(cone_tip)
        for i in range(24):
            angle = 2*math.pi*i/24
            point(rim+.78*radius*(u*math.cos(angle)+v*math.sin(angle)))
        for i in range(24): faces.append((cone_bottom, 1+i, 1+(i+1)%24))
        cone_face_count = len(faces)
        first = len(vertices)
        for j in range(13):
            polar = math.pi*j/12
            for i in range(24):
                angle = 2*math.pi*i/24
                point(center+radius*(axis*math.cos(polar)+math.sin(polar)*(u*math.cos(angle)+v*math.sin(angle))))
        self.tip_ids = list(range(first, first+24))
        for j in range(12):
            for i in range(24):
                a=first+j*24+i; b=first+j*24+(i+1)%24; c=b+24; d=a+24
                faces.extend(((a,b,c),(a,c,d)))
        obj=g["make_mesh"](self.cone_name,vertices,faces,g["material"]("R248 cone wafer",(.62,.34,.10)))
        obj.data.materials.append(g["material"]("R248 vanilla scoop",(.92,.76,.49)))
        for p in obj.data.polygons:
            p.material_index=int(p.index>=cone_face_count)
            if p.material_index: p.use_smooth=True
        g["bone_parent"](obj,self.wrist,False)
        self.names.append(obj.name)

        shower=g["compile_clip"]("showering",morph,g["SHOE"],fps=24)["frames"][0]
        g["solve"](shower)
        head=g["position"]("head")
        self.shower_center=head+Vector((0,0,.16*morph["stature_m"]))
        bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.045*morph["stature_m"],depth=.014,location=self.shower_center)
        obj=bpy.context.object;obj.name=self.shower_name
        obj.data.materials.append(g["material"]("R248 shower metal",(.45,.49,.52),.25))
        self.shower_names.append(obj.name)
        # Fixed thin cylinders are context lines, never fluid particles or force evidence.
        for i in range(7):
            angle=2*math.pi*i/7
            start=self.shower_center+Vector((math.cos(angle)*.035,math.sin(angle)*.035,-.01))
            end=head+Vector((math.cos(angle)*.06,math.sin(angle)*.06,.03))
            axis_line=end-start
            bpy.ops.mesh.primitive_cylinder_add(vertices=6,radius=.0015,depth=axis_line.length,location=(start+end)/2)
            obj=bpy.context.object;obj.name="R248 water context line "+str(i)
            obj.rotation_euler=axis_line.to_track_quat("Z","Y").to_euler()
            obj.data.materials.append(g["material"]("R248 context water "+str(i),(.11,.44,.68),.3))
            self.shower_names.append(obj.name)
        self.names.extend(self.shower_names)
        self.visibility("standing")

    def adjust_wrist(self, frame, side):
        if side!=self.side or self.wrist_orientation is None: return
        if not any(p.get("id")=="ice_cream_cone" for p in frame.get("props",[])): return
        # Explicit authored task orientation keeps this rigid cone upright.
        # It changes wrist orientation only; actual grip and joint limits are unqualified.
        matrix=self.wrist_orientation.copy()
        matrix.translation=self.g["position"](self.wrist)
        self.g["pose"](self.wrist,matrix)
        self.g["update"]()

    def visibility(self, activity):
        objects=self.g["bpy"].data.objects
        if objects.get(self.cone_name):objects[self.cone_name].hide_render=activity!="eating_ice_cream_cone"
        for name in self.shower_names:
            if objects.get(name):objects[name].hide_render=activity!="showering"

    def observe(self, frame, actual):
        g=self.g;objects=g["bpy"].data.objects
        if any(p.get("id")=="ice_cream_cone" for p in frame.get("props",[])):
            obj=objects.get(self.cone_name)
            if obj:
                ev=obj.evaluated_get(g["bpy"].context.evaluated_depsgraph_get())
                local=sum((obj.data.vertices[i].co for i in self.tip_ids),Vector())/len(self.tip_ids)
                tip=ev.matrix_world@local
                actual.setdefault("prop_tips_m",{})["ice_cream_cone"]=g["cv"](tip)
                actual["ice_cream_tip_to_mouth_proxy_m"]=(tip-g["bv"](actual["mouth_m"])).length
                actual["ice_cream_tip_reference"]="evaluated rigid wrist-parented mesh vertices"
            else:actual["ice_cream_prop_visibility"]="NOT_EXPORTED_TO_GLB"
        if any(p.get("id")=="shower_stream_context" for p in frame.get("props",[])):
            obj=objects.get(self.shower_name)
            if obj:
                actual["shower_head_center_m"]=g["cv"](obj.evaluated_get(g["bpy"].context.evaluated_depsgraph_get()).matrix_world.translation)
                actual["water_mechanics"]="NOT_IMPLEMENTED_FIXED_VISUAL_CONTEXT"
            else:actual["shower_context_visibility"]="NOT_EXPORTED_TO_GLB"
