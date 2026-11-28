"""Original, explicit kinematic studies. No captured motion or dynamics model.

Coordinates are metres, +Y up, +Z forward. Angles are authored diagnostic inputs.
Targets are separate from observed geometry and never constitute contact proof.
"""
import math
import numpy as np

GROUPS = {
    "support-events": ["slip_fall", "trip_fall", "backward_fall", "stiletto_heel_break"],
    "acrobatics-combat": ["somersault", "cartwheel", "karate_sequence", "judo_partner_throw", "wrestling_partner_takedown"],
    "exercise-dance": ["push_up", "sit_up", "dance_steps", "diagnostic_poses"],
}
DURATION = {k:4.0 for v in GROUPS.values() for k in v}
DURATION.update(diagnostic_poses=12.0, dance_steps=6.0, judo_partner_throw=5.0, wrestling_partner_takedown=5.0)
PAIRED = {"judo_partner_throw", "wrestling_partner_takedown"}
POSES = ["source_rest", "reference_t", "reference_a", "shoulder_elevation", "elbow_flexion", "torso_twist", "torso_flexion", "hip_knee_flexion", "single_leg_stance", "squat", "hand_open", "fist"]
NOTES = {
 "slip_fall":"Authored forward foot slip and backward fall; no friction or impact simulation.",
 "trip_fall":"Authored foot arrest at a visible low obstacle and forward brace/fall; collision response is not simulated.",
 "backward_fall":"Authored lowering and backward fall; no injury, balance or impact prediction.",
 "stiletto_heel_break":"Explicit 0.10 m heel / 0.008 m forefoot support proxy. Right heel detaches at 1.40 s; fragment and body response are authored, not fracture or rigid-body dynamics.",
 "somersault":"Authored forward rotation with airborne tuck; no flight, momentum or safe-technique validation.",
 "cartwheel":"Authored sideways rotation with alternating hand-support intent; contact and technique require measured/visual review.",
 "karate_sequence":"Original guard, straight-punch and front-kick study; no style, coaching or technique acceptance.",
 "judo_partner_throw":"Two independently bound actors: entry, explicit torso/shoulder contact intent, partner lift/rotation and release. A generic partnered throwing study, not a named or validated Judo technique.",
 "wrestling_partner_takedown":"Two independently bound actors: lowered entry, explicit leg/back contact intent, takedown and release. No technique, grappling-force or collision acceptance.",
 "push_up":"Authored hand/forefoot support and elbow flexion study. Contacts measured on source skin; no strength/load prediction.",
 "sit_up":"Authored supine-to-flexed trunk study with feet planted by intent. No exercise prescription or spinal-limit acceptance.",
 "dance_steps":"Original six-second side-step, sway and arm sequence; finite clip with explicit root motion, not a captured dance.",
 "diagnostic_poses":"Source rest remains immutable. T/A references and declared joint-angle inputs are posed diagnostics, not new binds or universal physiological limits.",
}

def smooth(x):
    x=float(np.clip(x,0,1));return x*x*(3-2*x)
def window(t,a,b):return smooth((t-a)/(b-a))
def pulse(t,a,b,c):return window(t,a,b)*(1-window(t,b,c))
def rot(axis,angle):
    a=np.asarray(axis,float);a/=np.linalg.norm(a);x,y,z=a;c=math.cos(angle);s=math.sin(angle);C=1-c
    return np.array([[c+x*x*C,x*y*C-z*s,x*z*C+y*s],[y*x*C+z*s,c+y*y*C,y*z*C-x*s],[z*x*C-y*s,z*y*C+x*s,c+z*z*C]])
def mix(a,b,u):return np.asarray(a)*(1-u)+np.asarray(b)*u

def sample(meta, activity, t, actor_index=0):
    """Return explicit world targets and reference rotations for one actor."""
    h=meta["stature_m"];hip0=np.array(meta["hip_center_m"]);duration=DURATION[activity];p=t/duration
    hip=hip0.copy();R=np.eye(3);torso=0.;twist=0.;head=0.;fist=0.;contacts=[]
    feet={s:np.array(meta["ankles_m"][s]) for s in ("L","R")}
    foot_R={s:np.eye(3) for s in feet};hand_mode="relaxed";hand_overrides={};knee_local=np.array([0,0,.6*h])
    foot_stance={s:True for s in feet};fingers=0.;diagnostic=None
    if activity in ("slip_fall","backward_fall","trip_fall"):
        forward=activity=="trip_fall";u=window(t,.65,3.15);pitch=(math.pi/2 if forward else -math.pi/2)*u
        R=rot([1,0,0],pitch);hip=mix(hip0,[0,.12*h,(.27 if forward else -.23)*h],u)
        torso=(.22 if forward else -.06)*math.sin(math.pi*u)
        for s,sign in (("L",1),("R",-1)):
            z=(.17 if activity=="slip_fall" else .02)*h*window(t,.35,1.0) if s=="R" else 0
            end=hip+R@np.array([sign*.08*h,-.30*h,.12*h]);end[1]=max(end[1],.045*h)
            feet[s]=mix(feet[s]+[0,0,z],end,window(t,1.25,3.1));foot_R[s]=rot([1,0,0],pitch*.55)
            foot_stance[s]=t<(.45 if s=="R" and activity=="slip_fall" else 1.25)
        hand_mode="brace_front" if forward else "brace_back"
    elif activity=="stiletto_heel_break":
        u=window(t,1.4,2.6);hip += [.055*h*u,-.12*h*u,.018*h*u];R=rot([0,0,1],-.12*u);torso=.12*u
        for s in feet:
            f=meta["feet"][s];heel=np.array(f["heel_from_ankle_m"]);fore=np.array(f["forefoot_from_ankle_m"])
            delta=fore-heel;length=math.hypot(delta[1],delta[2]);theta=math.asin(np.clip((.10-.008)/length,-1,1))-math.atan2(-delta[1],delta[2])
            pitch=theta*(1-u if s=="R" else 1);foot_R[s]=rot([1,0,0],pitch)
            fore_world=np.array(meta["ankles_m"][s])+fore;fore_world[1]=.008
            feet[s]=fore_world-foot_R[s]@fore
        hip[1]+=.08;hand_mode="balance"
    elif activity=="somersault":
        u=window(t,.7,3.25);air=math.sin(math.pi*u);R=rot([1,0,0],2*math.pi*u)
        hip=hip0+np.array([0,.28*h*air,.80*h*u]);tuck=math.sin(math.pi*u)**2
        for s,sign in (("L",1),("R",-1)):
            feet[s]=hip+R@mix(np.array(meta["ankles_m"][s])-hip0,[sign*.09*h,-.16*h,.16*h],tuck)
            foot_R[s]=R;foot_stance[s]=u in (0.,1.)
        hand_mode="tuck";torso=.25*tuck
    elif activity=="cartwheel":
        u=window(t,.6,3.5);R=rot([0,0,1],2*math.pi*u)
        hip=hip0+[-.95*h*u,0,0]
        # Lower into each lateral hand entry, rise over the inverted support.
        # This declared kinematic arc is subsequently checked against source
        # hand reach and the full evaluated skin, not treated as dynamics.
        hip[1]=hip0[1]-.22*h*math.sin(2*math.pi*u)**2+.04*h*math.sin(math.pi*u)**4
        for s,sign in (("L",1),("R",-1)):
            # Widen the legs on a measured reach sphere, not by increasing
            # Cartesian X while retaining the original fully extended Y.
            joint=np.array(meta["hips_m"][s]);knee=np.array(meta["knees_m"][s]);ankle=np.array(meta["ankles_m"][s])
            length=(np.linalg.norm(knee-joint)+np.linalg.norm(ankle-knee))*.99;angle=.10+.53*math.sin(math.pi*u)**2
            spread=joint-hip0+np.array([sign*length*math.sin(angle),-length*math.cos(angle),ankle[2]-joint[2]])
            local=mix(ankle-hip0,spread,math.sin(math.pi*u)**2)
            feet[s]=hip+R@local;foot_R[s]=R;foot_stance[s]=u<.02 or u>.98
        hand_mode="cartwheel";torso=.02
    elif activity=="karate_sequence":
        a=pulse(t,.3,1.0,1.6);kick=pulse(t,1.7,2.7,3.7);torso=.08*a;twist=.22*a;fingers=1.;hand_mode="guard"
        hand_overrides["R"]=[.05*h,.02*h,(.17+.14*a)*h]
        feet["R"]+=np.array([-.045*h,.26*h*kick,.30*h*kick]);foot_R["R"]=rot([1,0,0],-.35*kick);foot_stance["R"]=kick<1e-6
        hip += [ .03*h*kick,-.025*h*kick,-.015*h*kick]
    elif activity in PAIRED:
        u=window(t,1.5,4.3);entry=window(t,0,1.4);yaw=0 if actor_index==0 else math.pi
        R=rot([0,1,0],yaw);hip+=np.array([0,0,(-.13 if actor_index==0 else .13)*h]);feet={s:hip+R@(np.array(v)-hip0) for s,v in feet.items()};foot_R={s:R.copy() for s in feet}
        if actor_index==0:
            hip[1]-=(.27 if activity=="wrestling_partner_takedown" else .06)*h*entry
            torso=(.42 if activity=="wrestling_partner_takedown" else .20)*entry*(1-.5*u);twist=.35*u
            hip[2]+=.09*h*u
        else:
            if activity=="judo_partner_throw":
                pitch=math.pi/2*u;R=rot([0,1,0],math.pi)@rot([1,0,0],pitch)
                hip=mix(hip,[0,.14*h,-.47*h],u);hip[1]+=.22*h*math.sin(math.pi*u)
            else:
                R=rot([0,1,0],math.pi)@rot([1,0,0],-math.pi/2*u)
                hip=mix(hip,[0,.13*h,.50*h],u)
                hip[1]-=.08*h*entry*(1-u)
                hip[2]-=.10*h*entry*(1-u)
            for s,sign in (("L",1),("R",-1)):
                local=mix(np.array(meta["ankles_m"][s])-hip0,[sign*.09*h,-.29*h,.16*h],math.sin(math.pi*u)**2)
                feet[s]=hip+R@local;foot_R[s]=R;foot_stance[s]=u<.01
            if activity=="wrestling_partner_takedown":
                release=window(t,2.25,3.0);stance_root=hip0+np.array([0,0,.13*h]);stance_R=rot([0,1,0],math.pi)
                for s in feet:
                    anchor=stance_root+stance_R@(np.array(meta["ankles_m"][s])-hip0)
                    feet[s]=mix(anchor,feet[s],release);foot_stance[s]=release==0.
                    foot_R[s]=rot([0,1,0],math.pi)@rot([1,0,0],-math.pi/2*u*release)
        release_time=2.25 if activity=="wrestling_partner_takedown" else 2.55
        hand_mode="partner" if 1.15<t<release_time else "balance"
    elif activity=="push_up":
        depth=(1-math.cos(2*math.pi*t/2))/2;hip=np.array([0,(.20-.075*depth)*h,0.])
        foot_R={s:rot([1,0,0],.95) for s in feet};spans=[];heights=[]
        for s in feet:
            offsets=np.asarray(meta["foot_skin_offsets_m"][s]);height=.002-float((offsets@foot_R[s].T)[:,1].min())
            joint=np.array(meta["hips_m"][s]);knee=np.array(meta["knees_m"][s]);ankle=np.array(meta["ankles_m"][s])
            length=.995*(np.linalg.norm(joint-knee)+np.linalg.norm(knee-ankle));span=math.sqrt(max(0,length**2-(hip[1]-height)**2))
            feet[s]=np.array([joint[0]-hip0[0],height,joint[2]-hip0[2]-span]);spans.append(span);heights.append(height)
        angle=math.atan2(float(np.mean(spans)),hip[1]-float(np.mean(heights)));R=rot([1,0,0],angle);torso=.025
        hand_mode="push_up"
    elif activity=="sit_up":
        flex=(1-math.cos(2*math.pi*t/4))/2;hip=np.array([0,.105*h,0.]);R=rot([1,0,0],-math.pi/2);torso=1.05*flex;head=.20*flex
        feet={s:np.array([sign*.09*h,.045*h,.31*h]) for s,sign in (("L",1),("R",-1))};hand_mode="chest"
    elif activity=="dance_steps":
        phase=2*math.pi*t/3;hip+=np.array([.11*h*math.sin(phase),-.025*h*(1-math.cos(phase*2)),.03*h*math.sin(phase/2)])
        R=rot([0,1,0],.20*math.sin(phase));torso=.07*math.sin(phase*2);twist=.18*math.sin(phase);head=-.12*math.sin(phase);hand_mode="dance"
        for s,sign in (("L",1),("R",-1)):
            swing=max(0,sign*math.sin(phase));feet[s]+=np.array([.09*h*math.sin(phase),.075*h*swing,.03*h*math.sin(phase/2)])
            foot_stance[s]=swing<.05
    elif activity=="diagnostic_poses":
        index=min(11,int(t));diagnostic=POSES[index];hand_mode="diagnostic"
        if diagnostic=="torso_twist":twist=math.radians(30)
        if diagnostic=="torso_flexion":torso=math.radians(30)
        if diagnostic in ("hip_knee_flexion","single_leg_stance"):
            feet["L"]+=np.array([0,.18*h,.16*h if diagnostic=="hip_knee_flexion" else 0]);foot_stance["L"]=False
        if diagnostic=="squat":hip[1]-=.22*h;torso=.24
        if diagnostic=="fist":fingers=1.
    if not foot_stance["L"] and not foot_stance["R"]:contacts=[]
    for s in feet:
        if foot_stance[s]:contacts.append({"actor_part":"foot."+s,"kind":"ground_support_intent","world_plane_y_m":0.})
    return {"time_s":float(t),"activity":activity,"actor_index":actor_index,"hip":hip,"R":R,"torso":torso,"twist":twist,"head":head,
            "feet":feet,"foot_R":foot_R,"stance":foot_stance,"hand_mode":hand_mode,"hand_overrides":hand_overrides,"knee_local":knee_local,
            "fingers":fingers,"contacts":contacts,"diagnostic":diagnostic,"phase":p}

def hands(meta,frame,shoulders,chest=None,partner=None):
    """World wrist targets; actual palm contact separately observed by producer."""
    h=meta["stature_m"];R=frame["R"];mode=frame["hand_mode"];t=frame["time_s"];targets={};palm={};contacts=[]
    for s,sign in (("L",1),("R",-1)):
        shoulder=np.array(shoulders[s]);offset=np.array([sign*.025*h,-.255*h,.025*h]);rotation=R.copy()
        if mode=="tuck":offset=np.array([-sign*.035*h,-.14*h,.14*h])
        elif mode in ("balance","brace_front","brace_back"):
            offset=np.array([sign*.10*h,-.13*h,(.14 if mode!="brace_back" else -.10)*h])
        elif mode=="guard":offset=np.array([-sign*.025*h,-.045*h,.17*h])
        elif mode=="dance":offset=np.array([sign*.17*h,.07*h*math.sin(2*math.pi*t/3+sign),.03*h])
        elif mode=="chest":offset=np.array([-sign*.07*h,-.02*h,.09*h])
        elif mode=="push_up":
            target=np.array([sign*.14*h,0.,.28*h]);palm[s]=target
            contacts.append({"actor_part":"palm."+s,"kind":"ground_support_intent","point_m":target.tolist()})
        elif mode=="cartwheel":
            u=window(t,.6,3.5)
            # Travel towards -X makes the anatomical right hand the first
            # support; the left hand follows across the inverted phase.
            if (.22<u<.60 and s=="R") or (.40<u<.78 and s=="L"):
                target=np.array([-(.38 if s=="R" else .58)*h,0.,0.]);palm[s]=target
                contacts.append({"actor_part":"palm."+s,"kind":"ground_support_intent","point_m":target.tolist()})
            elif (s=="R" and u>=.60) or (s=="L" and u>=.78):offset=np.array([sign*.05*h,-.16*h,.07*h])
            else:offset=np.array([sign*.04*h,.28*h,0.])
        elif mode=="partner" and partner:
            # Defender uses upper-body contacts; only the takedown initiator
            # receives the opponent's knee/back targets.
            key=("chest" if s=="L" else "shoulder") if frame["activity"]=="judo_partner_throw" or frame["actor_index"]==1 else ("knee" if s=="L" else "back")
            target=np.array(partner[key]);palm[s]=target
            contacts.append({"actor_part":"palm."+s,"kind":"partner_source_surface_intent","partner_anchor":key,"role":"initiator" if frame["actor_index"]==0 else "defender","phase":"authored_grip_1.15_to_2.25_s" if frame["activity"]=="wrestling_partner_takedown" else "authored_grip_1.15_to_2.55_s","release_semantics":"Explicit authored release before remaining fall; no continuing grip claim.","point_m":target.tolist()})
        elif mode=="diagnostic":
            d=frame["diagnostic"]
            if d in ("source_rest","hand_open","fist"):offset=np.array(meta["wrists_m"][s])-np.array(meta["shoulders_m"][s])
            elif d=="reference_t":offset=np.array([sign*.286*h,0,0])
            elif d=="reference_a":offset=np.array([sign*.20*h,-.20*h,0])
            elif d=="shoulder_elevation":offset=np.array([sign*.015*h,.278*h,0])
            elif d=="elbow_flexion":offset=np.array([sign*.12*h,.015*h,.12*h])
        if s in frame["hand_overrides"]:offset=np.array(frame["hand_overrides"][s])
        targets[s]=shoulder+R@offset
    for c in contacts:
        if c["kind"]=="ground_support_intent":
            side=c["actor_part"][-1];height=frame.get("palm_height_offsets_m",{}).get(side,0.)
            palm[side][1]+=height;c["point_m"]=palm[side].tolist();c["support_plane_y_m"]=0.;c["palm_proxy_height_above_plane_m"]=height
            c["contact_semantics"]="Measured hand-patch plane proximity only; the source palm proxy can lie above it. No load-bearing claim."
    return targets,palm,contacts
