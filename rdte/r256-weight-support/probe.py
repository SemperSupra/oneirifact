"""Actual forward dynamics of an explicitly simplified fixed-pose body surrogate.

Original diagnostic model; NOT a human controller, organ model, source-skin
retarget, physical fracture prediction or accepted realistic activity product.
The support event changes collision eligibility only, never the root trajectory.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os
from pathlib import Path
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

G=9.81
EVENT_S=0.6
DURATION_S=2.0

def model_xml(height=1.7,mass=75.,build=1.,dt=.001,gravity=True,floor=True):
    # Declared uniform ellipsoid approximation for the aggregate inertia.
    # No organ masses are added to this already-total mass.
    a,b,c=.09*height*build,.13*height*build,.45*height
    inertia=mass/5*np.array([b*b+c*c,a*a+c*c,a*a+b*b])
    scale=height/1.7
    world_floor='<geom name="floor" type="plane" size="5 5 .1" rgba=".18 .21 .27 1"/>' if floor else ''
    parts=[
      ('torso','capsule',f'0 0 {.50*height} 0 0 {.80*height}',f'{.105*height*build}'),
      ('right_leg','capsule',f'0 {-.065*height} {.10*height} 0 {-.065*height} {.49*height}',f'{.038*height*build}'),
      ('left_leg','capsule',f'0 {.065*height} {.10*height} 0 {.065*height} {.49*height}',f'{.038*height*build}'),
      ('right_arm','capsule',f'0 {-.16*height} {.48*height} 0 {-.16*height} {.76*height}',f'{.025*height*build}'),
      ('left_arm','capsule',f'0 {.16*height} {.48*height} 0 {.16*height} {.76*height}',f'{.025*height*build}')]
    geoms=''.join(f'<geom name="{name}" type="{kind}" fromto="{ends}" size="{radius}" mass="0" rgba=".20 .64 .75 1"/>' for name,kind,ends,radius in parts)
    return f'''<mujoco model="r256_declared_rigid_body_support_probe">
      <compiler angle="radian"/><option timestep="{dt}" gravity="0 0 {-G if gravity else 0}" integrator="implicitfast" solver="Newton" iterations="100" tolerance="1e-12"/>
      <default><geom friction=".8 .002 .0001" condim="3" solref=".004 1" solimp=".99 .999 .0001"/></default>
      <worldbody>{world_floor}<body name="aggregate" pos="0 0 0"><freejoint name="root"/>
        <inertial pos="0 0 {.52*height}" mass="{mass}" diaginertia="{' '.join(map(str,inertia))}"/>
        {geoms}<geom name="head" type="sphere" pos="0 0 {.93*height}" size="{.07*height}" mass="0" rgba=".63 .79 .80 1"/>
        <geom name="toe" type="box" pos="{.14*scale} 0 .012" size="{.035*scale} {.065*scale} .012" mass="0" rgba=".92 .65 .24 1"/>
        <geom name="heel" type="cylinder" pos="{-.08*scale} 0 .055" size=".008 .055" mass="0" rgba=".92 .65 .24 1"/>
        <geom name="sole" type="capsule" fromto="{-.08*scale} 0 .11 {.14*scale} 0 .032" size=".01" mass="0" rgba=".35 .39 .47 1"/>
      </body></worldbody></mujoco>'''

def run_case(case,broken,dt=.001,gravity=True,floor=True,force=0.,duration=DURATION_S):
    model=mujoco.MjModel.from_xml_string(model_xml(**case,dt=dt,gravity=gravity,floor=floor))
    data=mujoco.MjData(model)
    heel=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,'heel')
    data.qpos[2]=0 if floor else 3.
    mujoco.mj_forward(model,data)
    trace=[];stride=max(1,round(.01/dt));event=False
    for step in range(round(duration/dt)+1):
        if broken and not event and data.time>=EVENT_S-1e-10:
            model.geom_contype[heel]=0;model.geom_conaffinity[heel]=0;event=True
        data.xfrc_applied[1,0]=force
        mujoco.mj_forward(model,data)
        if step%stride==0:
            support=0.;heel_contacts=0
            for ci in range(data.ncon):
                con=data.contact[ci];cf=np.zeros(6);mujoco.mj_contactForce(model,data,ci,cf)
                wf=con.frame.reshape(3,3).T@cf[:3]
                support+=abs(float(wf[2]))
                heel_contacts+=int(heel in (con.geom1,con.geom2))
            rot=data.xmat[1].reshape(3,3)
            trace.append({'time_s':round(float(data.time),6),'root_x_m':float(data.qpos[0]),'root_z_m':float(data.qpos[2]),
              'com_x_m':float(data.xipos[1,0]),'com_z_m':float(data.xipos[1,2]),'pitch_rad':math.atan2(float(rot[0,2]),float(rot[2,2])),
              'vx_m_s':float(data.qvel[0]),'vz_m_s':float(data.qvel[2]),'support_force_N':support,
              'heel_contacts':heel_contacts,'contacts':int(data.ncon),'heel_enabled':not event,
              'qpos':data.qpos.copy().tolist(),'qvel':data.qvel.copy().tolist()})
        if step<round(duration/dt):mujoco.mj_step(model,data)
    return model,data,trace

def metrics(case,trace):
    rest=[r for r in trace if .4<=r['time_s']<.59]
    after=[r for r in trace if EVENT_S+.01<=r['time_s']]
    return {'total_mass_kg':case['mass'],'stature_m':case['height'],'build_scale':case['build'],
     'settled_support_force_N':float(np.mean([r['support_force_N'] for r in rest])),
     'expected_weight_N':case['mass']*G,'max_abs_pitch_rad':max(abs(r['pitch_rad']) for r in trace),
     'post_event_max_abs_pitch_rad':max(abs(r['pitch_rad']) for r in after),
     'last_com_height_m':trace[-1]['com_z_m'],'post_event_heel_contact_samples':sum(r['heel_contacts'] for r in after),
     'trajectory_is_integrated':True}

def font(size):
    path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    return ImageFont.truetype(path,size) if Path(path).exists() else ImageFont.load_default()

def draw_state(im,box,case,row,broken,title):
    d=ImageDraw.Draw(im);x0,y0,w,h=box
    d.rectangle((x0,y0,x0+w,y0+h),fill='#111b2a')
    d.text((x0+12,y0+10),title,font=font(18),fill='white')
    scale=min(w/2.7,(h-100)/2.1);origin=(x0+w*.65,y0+h-54)
    def project(v):
        q=row['qpos'][3:7];rot=np.zeros(9);mujoco.mju_quat2Mat(rot,np.asarray(q))
        p=rot.reshape(3,3)@np.asarray(v)+np.asarray(row['qpos'][:3])
        return origin[0]+p[0]*scale,origin[1]-p[2]*scale
    d.line((x0,origin[1],x0+w,origin[1]),fill='#617183',width=2)
    H=case['height'];B=case['build']
    for a,b,r in [((0,0,.5*H),(0,0,.8*H),.105*H*B),((0,0,.10*H),(0,0,.49*H),.038*H*B),((0,0,.48*H),(0,0,.76*H),.025*H*B)]:
        p1,p2=project(a),project(b);width=max(2,int(2*r*scale));d.line((*p1,*p2),fill='#37a4b8',width=width)
        for p in (p1,p2):d.ellipse((p[0]-width/2,p[1]-width/2,p[0]+width/2,p[1]+width/2),fill='#37a4b8')
    p=project((0,0,.93*H));r=.07*H*scale;d.ellipse((p[0]-r,p[1]-r,p[0]+r,p[1]+r),fill='#a0c6ce')
    S=H/1.7
    d.line((*project((-.08*S,0,.11)),*project((.14*S,0,.032))),fill='#aab6c6',width=4)
    d.line((*project((.105*S,0,.012)),*project((.175*S,0,.012))),fill='#edb249',width=5)
    if row['heel_enabled']:d.line((*project((-.08*S,0,.0)),*project((-.08*S,0,.11))),fill='#edb249',width=5)
    p=(origin[0]+row['com_x_m']*scale,origin[1]-row['com_z_m']*scale);d.ellipse((p[0]-4,p[1]-4,p[0]+4,p[1]+4),fill='#ff5577')
    d.text((x0+12,y0+h-42),f"t={row['time_s']:.2f}s   support={row['support_force_N']:.0f} N",font=font(15),fill='#c4d0df')
    d.text((x0+12,y0+h-23),'heel contact removed' if broken and not row['heel_enabled'] else 'heel support present',font=font(13),fill='#edb249')

def products(out,case,a,b):
    frames=[]
    for i in range(0,min(len(a),len(b)),4):
        im=Image.new('RGB',(1040,640),'#0b111b')
        d=ImageDraw.Draw(im);d.text((22,14),'Weight and support: actual forward dynamics',font=font(25),fill='white')
        d.text((22,49),'Fixed-pose aggregate; declared inertia; no balance controller, fracture or organ deformation',font=font(14),fill='#bbc8d8')
        draw_state(im,(16,82,500,500),case,a[i],False,'Intact support')
        draw_state(im,(524,82,500,500),case,b[i],True,'Support removed at 0.60 s')
        d=ImageDraw.Draw(im);d.text((22,603),f"{case['height']:.2f} m / {case['mass']:.0f} kg   Gravity 9.81 m/s2   Magenta: integrated centre of mass",font=font(15),fill='#c4d0df')
        frames.append(im)
    frames[0].save(out/'support-loss.gif',save_all=True,append_images=frames[1:],duration=40,loop=0,optimize=True)
    selected=[0,round(.6/.04),round(1.1/.04),len(frames)-1]
    sheet=Image.new('RGB',(2080,1280))
    for k,i in enumerate(selected):sheet.paste(frames[i],((k%2)*1040,(k//2)*640))
    sheet.save(out/'support-loss-comparison.png')

def main(out):
    out.mkdir(parents=True,exist_ok=False)
    cases=[{'height':h,'mass':m,'build':b} for h,m,b in [(1.55,55.,.9),(1.7,75.,1.),(1.85,95.,1.15)]]
    rows=[];traces={}
    for ci,case in enumerate(cases):
        for broken in (False,True):
            name=f'case-{ci+1}-'+('lost-heel' if broken else 'intact')
            model,data,trace=run_case(case,broken)
            (out/(name+'.xml')).write_text(model_xml(**case))
            with (out/(name+'.csv')).open('w',newline='') as f:
                fields=[k for k in trace[0] if k not in ('qpos','qvel')];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r[k] for k in fields} for r in trace)
            (out/(name+'-replay.json')).write_text(json.dumps({'case':case,'event':{'time_s':EVENT_S,'action':'remove heel collision eligibility only'} if broken else None,'trace':trace},separators=(',',':')))
            rows.append({'id':name,'broken':broken,**metrics(case,trace)});traces[name]=trace
    controls={}
    for mass in (55.,95.):
        case={'height':1.7,'mass':mass,'build':1.}
        _,data,trace=run_case(case,False,gravity=False,floor=False,force=30.,duration=.2)
        controls[f'force_mass_{mass:g}']={'observed_delta_v_m_s':float(data.qvel[0]),'expected_delta_v_m_s':30*.2/mass,'pass':bool(abs(data.qvel[0]-30*.2/mass)<1e-9)}
        _,data,trace=run_case(case,False,gravity=True,floor=False,duration=.2)
        controls[f'freefall_mass_{mass:g}']={'observed_vz_m_s':float(data.qvel[2]),'expected_vz_m_s':-G*.2,'pass':bool(abs(data.qvel[2]+G*.2)<1e-9)}
    case=cases[1]
    _,_,zero=run_case(case,True,gravity=False)
    p0=np.asarray(zero[0]['qpos'][:3]);q0=np.asarray(zero[0]['qpos'][3:7])
    displacement=max(float(np.linalg.norm(np.asarray(r['qpos'][:3])-p0)) for r in zero)
    angle=max(2*math.acos(min(1.,abs(float(np.dot(q0,r['qpos'][3:7]))))) for r in zero)
    speed=max(float(np.linalg.norm(r['qvel'])) for r in zero)
    controls['zero_gravity_support_removal']={'max_root_displacement_m':displacement,'max_orientation_change_rad':angle,'max_generalized_speed':speed,'tolerance':1e-9,'pass':displacement<1e-9 and angle<1e-9 and speed<1e-9}
    for r in rows:
        ok=abs(r['settled_support_force_N']/r['expected_weight_N']-1)<.02
        controls[r['id']+'_weight_balance']={'relative_error':abs(r['settled_support_force_N']/r['expected_weight_N']-1),'pass':ok}
        controls[r['id']+'_support_response']={'pass':r['post_event_max_abs_pitch_rad']>.1 and r['post_event_heel_contact_samples']==0 if r['broken'] else r['max_abs_pitch_rad']<.03}
    _,_,fine=run_case(case,True,dt=.0005)
    coarse=traces['case-2-lost-heel']
    k=next(i for i,r in enumerate(coarse) if r['time_s']==1.0)
    delta=abs(coarse[k]['com_z_m']-fine[k]['com_z_m'])
    controls['half_step_preimpact_comparison']={'time_s':1.,'com_z_delta_m':delta,'tolerance_m':.01,'pass':delta<.01}
    products(out,case,traces['case-2-intact'],traces['case-2-lost-heel'])
    report={'schema':'oneirifact.weight-support-probe/v1','status':'PASS_DECLARED_MECHANICS_PROBE' if all(c['pass'] for c in controls.values()) else 'FAIL',
       'mujoco_version':mujoco.__version__,'source_head':os.environ.get('SOURCE_HEAD_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
       'runner':{'os':os.environ.get('RUNNER_OS'),'arch':os.environ.get('RUNNER_ARCH'),'environment':os.environ.get('RUNNER_ENVIRONMENT')},
       'event_time_s':EVENT_S,'cases':rows,'controls':controls,
       'scope':['Actual forward-integrated gravity, aggregate inertia, contact and friction','Three explicitly assigned stature/mass/build combinations','Collision support removal without writing trajectory or velocity'],
       'limits':['Rigid fixed-pose engineering surrogate; not the source human mesh or a human multibody rig','Uniform ellipsoid aggregate inertia is declared, not measured human/organ inertia','No balance, protective step, joint compliance, fracture mechanics or deformable organs','Assigned total mass already includes all contents; no organ mass is added','No claim of realistic heel-break outcome, clinical interpretation or human validation']}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    manifest={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'cases':rows,'controls':controls},indent=2))
    if report['status'].startswith('FAIL'):raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();main(args.out)

