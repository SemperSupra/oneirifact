"""Fit closed swept loops to actual lantern geometry; R204 public-safe diagnostic.
Uses full mesh vertices for fitting and disjoint surface samples for scoring.
Not an independent scan, canonical Foundry source, or engineering equivalence.
"""
import sys,json,zipfile,hashlib
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'inverse-r201'))
from fit import read_glb,sample,topology
from components import split,torus

def sweep(c,R,major,straight,tube,n=7,m=8):
    # Local axes: normal, short, long. Two semicircles with straight joins.
    t=np.r_[np.linspace(0,np.pi,n),np.linspace(np.pi,2*np.pi,n)]
    y=major*np.cos(t);z=major*np.sin(t)+np.r_[np.full(n,straight),np.full(n,-straight)]
    a=np.arange(m)*2*np.pi/m
    v=np.stack(np.broadcast_arrays(tube*np.sin(a)[None,:],y[:,None]+tube*np.cos(t)[:,None]*np.cos(a)[None,:],z[:,None]+tube*np.sin(t)[:,None]*np.cos(a)[None,:]),axis=-1).reshape(-1,3)
    f=[]
    for i in range(len(t)):
        for j in range(m):
            a0=i*m+j;b=((i+1)%len(t))*m+j;d=i*m+(j+1)%m;e=((i+1)%len(t))*m+(j+1)%m
            f.extend(((a0,b,e),(a0,e,d)))
    return v@R.T+c,np.array(f)
def metric(p,v,f,extent,seed):
    q=sample(v,f,16000,seed);a=cKDTree(q).query(p)[0];b=cKDTree(p).query(q)[0]
    return {'rmse_relative':float(np.sqrt((np.mean(a*a)+np.mean(b*b))/2)/extent),'coverage_2pct':float(min(np.mean(a<=.02*extent),np.mean(b<=.02*extent))),'p95_relative':float(max(np.quantile(a,.95),np.quantile(b,.95))/extent)}
def write_obj(path,v,f):
    path.write_text(''.join('v %.9f %.9f %.9f\n'%tuple(x) for x in v)+''.join('f %d %d %d\n'%tuple(x+1) for x in f))
def drawmesh(im,rect,v,f,c,scale,color):
    x,y,w,h=rect;a,b=np.radians([26,16]);R=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])@np.array([[1,0,0],[0,np.cos(b),-np.sin(b)],[0,np.sin(b),np.cos(b)]])
    p=(v-c)@R;xy=np.column_stack((x+w/2+p[:,0]*scale,y+h/2-p[:,1]*scale));t=p[f];norm=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);norm/=np.maximum(np.linalg.norm(norm,axis=1)[:,None],1e-12);shade=.38+.62*np.abs(norm@np.array([.3,.4,.866]));d=ImageDraw.Draw(im)
    for i in np.argsort(t[:,:,2].mean(1)):
        d.polygon([tuple(q) for q in xy[f[i]]],fill=tuple(int(k*shade[i]) for k in color))
def run(root,out):
    out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(root/'github-actions-artifact-15228548803.zip') as z:
        raw=z.read('normalized.glb');receipt=json.loads(z.read('receipt.json'));assert hashlib.sha256(raw).hexdigest()==receipt['files']['normalized.glb'];parts=read_glb(raw)
    results=[];models=[]
    for name,(v,f) in parts.items():
        if 'Chain' not in name:continue
        for idx,(sv,sf) in enumerate(split(v,f)):
            top=topology(sv,sf);extent=float(np.ptp(sv,axis=0).max())
            if top['boundary_edges'] or top['euler']!=0:
                results.append({'shell':idx,'status':'RETAIN_OPEN_SOURCE','topology':top});continue
            unique=np.unique(np.round(sv,8),axis=0);c=unique.mean(0);_,R=np.linalg.eigh((unique-c).T@(unique-c));q=(unique-c)@R
            lo,hi=q.min(0),q.max(0);c=c+((lo+hi)/2)@R.T;half=(hi-lo)/2
            tube=float(half[0]);major=float(half[1]-tube);straight=float(half[2]-tube-major)
            assert major>tube>0 and straight>0
            train=sample(sv,sf,12000,51);val=sample(sv,sf,16000,53);test=sample(sv,sf,24000,57)
            tag,tv,tf,tp=next(torus(sv,train)); candidates=[(tag,tv,tf,tp)]
            for n in (5,7,9,13,21):
                for m in (6,8,12,16):
                    pv,pf=sweep(c,R,major,straight,tube,n,m);candidates.append(('stadium-sweep',pv,pf,{'semicircle_samples':n,'cross_section_samples':m,'center':c.tolist(),'frame':R.tolist(),'major_radius':major,'straight_half_length':straight,'tube_radius':tube}))
            eligible=[];evaluated=[]
            for tag,pv,pf,params in candidates:
                compatible=topology(pv,pf)==top
                met=metric(val,pv,pf,extent,81)
                evaluated.append({'kind':tag,'parameters':params,'faces':len(pf),'topology_match':compatible,'validation':met})
                if compatible and met['coverage_2pct']>=.95:eligible.append((met['rmse_relative'],len(pf),tag,pv,pf,params,met))
            base=metric(test,tv,tf,extent,99)
            if not eligible:
                results.append({'shell':idx,'status':'RETAIN_SOURCE','baseline':base,'topology':top,'candidates':evaluated});continue
            _,_,tag,pv,pf,params,vm=min(eligible,key=lambda x:(x[0],x[1])); met=metric(test,pv,pf,extent,99)
            passed=met['coverage_2pct']>=.95
            row={'shell':idx,'status':'COARSE_GEOMETRY_ONLY' if passed else 'RETAIN_SOURCE','baseline':base,'candidate':met,'validation':vm,'kind':tag,'parameters':params,'topology':top,'faces_source':len(sf),'faces_candidate':len(pf),'candidates':evaluated};results.append(row)
            for label_,vv,ff in [('source',sv,sf),('torus',tv,tf),('sweep',pv,pf)]:write_obj(out/f'link-{idx}-{label_}.obj',vv,ff)
            if tag=='stadium-sweep':models.append((idx,sv,sf,tv,tf,pv,pf,c,extent,row))
    vout=[];fout=[];offset=0
    for name,(v,f) in parts.items():
        for idx,(sv,sf) in enumerate(split(v,f)):
            match=next((x for x in models if 'Chain' in name and x[0]==idx and x[-1]['status']=='COARSE_GEOMETRY_ONLY'),None)
            pv,pf=(match[5],match[6]) if match else (sv,sf)
            vout.extend(pv);fout.extend(pf+offset);offset+=len(pv)
    write_obj(out/'Lantern-r204-hybrid.obj',np.array(vout),np.array(fout))
    if models:
        idx,sv,sf,tv,tf,pv,pf,c,extent,row=models[0];R=np.array(row['parameters']['frame']);perm=[1,2,0]
        im=Image.new('RGB',(1200,620),'#18212c');d=ImageDraw.Draw(im);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',25);small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
        d.text((22,18),'R204 | Actual lantern chain link — swept construction recovery',font=font,fill='white');d.text((22,58),'Identical source-relative scale • geometry only • same-source sampled evaluation',font=small,fill='#b4c7d8')
        for j,(label_,vv,ff,color,sub) in enumerate([('Original mesh',sv,sf,(164,209,225),'224 source triangles'),('Circular torus',tv,tf,(201,159,109),f"Coverage {row['baseline']['coverage_2pct']:.1%}"),('Recovered sweep',pv,pf,(108,209,178),f"Coverage {row['candidate']['coverage_2pct']:.1%}")]):
            xx=20+j*393;d.rectangle((xx,110,xx+380,580),outline='#42546a');d.text((xx+15,125),label_,font=font,fill='white');d.text((xx+15,165),sub,font=small,fill='#c3d4df');drawmesh(im,(xx+10,195,360,365),((vv-c)@R)[:,perm],ff,np.zeros(3),280/extent,color)
        im.save(out/'chain-comparison.png')
    report={'schema':'r204-sweep-bakeoff/v1','source_sha256':hashlib.sha256(raw).hexdigest(),'scope':'full source mesh vertex fitting, same-source sampled test, coarse geometry-only; no texture, independent scans, interlink collision or Foundry qualification','results':results}
    (out/'receipt.json').write_text(json.dumps(report,indent=2))
    print(json.dumps([{k:v for k,v in row.items() if k not in ('candidates','parameters')} for row in results],indent=2))
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
