"""Connected-shell segmentation, local-axis fitting and topology-gated hybrid export."""
import sys,json,zipfile
from pathlib import Path
import numpy as np
from fit import read_glb,sample,metrics,topology,proposals

def split(v,f):
    _,ix=np.unique(np.round(v,6),axis=0,return_inverse=True);par=list(range(int(ix.max())+1))
    def find(a):
        while par[a]!=a:par[a]=par[par[a]];a=par[a]
        return a
    for t in ix[f]:
        par[find(t[0])]=find(t[1]);par[find(t[0])]=find(t[2])
    groups={}
    for i,t in enumerate(ix[f]):groups.setdefault(find(t[0]),[]).append(i)
    for ids in sorted(groups.values(),key=len,reverse=True):
        faces=f[ids];used,inv=np.unique(faces,return_inverse=True);yield v[used],inv.reshape(-1,3)

def torus(v,train):
    # Local PCA coordinates: smallest spread is assumed normal to ring.
    c=train.mean(0);q=train-c;cov=q.T@q;_,R=np.linalg.eigh(cov);p=q@R;rho=np.linalg.norm(p[:,1:],axis=1);major=np.median(rho);minor=np.median(np.hypot(rho-major,p[:,0]));
    if minor<=0 or major<=minor:return
    a=np.arange(96)*2*np.pi/96;b=np.arange(32)*2*np.pi/32;aa,bb=np.meshgrid(a,b,indexing='ij');xyz=np.column_stack(((minor*np.sin(bb)).ravel(),((major+minor*np.cos(bb))*np.cos(aa)).ravel(),((major+minor*np.cos(bb))*np.sin(aa)).ravel()));f=[]
    for i in range(96):
        for j in range(32):
            x=i*32+j;y=((i+1)%96)*32+j;z=((i+1)%96)*32+(j+1)%32;w=i*32+(j+1)%32;f.extend(((x,y,z),(x,z,w)))
    yield 'torus',xyz@R.T+c,np.array(f),{'center':c.tolist(),'axis':R[:,0].tolist(),'major_radius':float(major),'minor_radius':float(minor)}

def main(root,out):
    result={}
    for name,aid in [('Avocado',15229781019),('Lantern',15228548803),('WaterBottle',15228334677)]:
        with zipfile.ZipFile(root/f'github-actions-artifact-{aid}.zip') as z:parts=read_glb(z.read('normalized.glb'))
        rows=[];lines=[];offset=1
        for part,(v,f) in parts.items():
            for i,(sv,sf) in enumerate(split(v,f)):
                extent=np.ptp(sv,axis=0).max();top=topology(sv,sf);status='RETAIN_SOURCE_MESH';best=None;metric=None;params=None;pv,pf=sv,sf
                if len(sf)>=20 and extent>1e-6 and min(np.ptp(sv,axis=0))>1e-6:
                    train=sample(sv,sf,6000,51);val=sample(sv,sf,10000,53);test=sample(sv,sf,16000,57)
                    c=sv.mean(0);_,R=np.linalg.eigh((train-c).T@(train-c));local=(sv-c)@R;lt=(train-c)@R;options=[]
                    for tag,vv,ff,pp in proposals(local,sf,lt):options.append((tag,vv@R.T+c,ff,{'local':pp,'frame':R.tolist(),'origin':c.tolist()}))
                    options.extend(torus(sv,train) or [])
                    # Only topology-compatible candidates eligible for acceptance.
                    ranked=[]
                    for tag,vv,ff,pp in options:
                        m=metrics(val,vv,ff,extent=extent);ranked.append((m['symmetric_rmse'],tag,vv,ff,pp,topology(vv,ff)))
                    ranked.sort(key=lambda x:x[0]);_,best,bv,bf,params,bt=ranked[0];metric=metrics(test,bv,bf,seed=201,extent=extent);metric['relative_rmse']=metric['symmetric_rmse']/extent
                    if top==bt and metric['coverage_2pct_part']>=.95:
                        status='COARSE_GEOMETRY_ONLY';pv,pf=bv,bf
                rows.append({'source_part':part,'shell':i,'faces':len(sf),'topology':top,'best':best,'metrics':metric,'params':params,'disposition':status})
                lines.append('o '+part+'-shell-'+str(i)+'-'+status);lines.extend('v %.8f %.8f %.8f'%tuple(x) for x in pv);lines.extend('f %d %d %d'%tuple(x+offset) for x in pf);offset+=len(pv)
        result[name]=rows;(out/(name+'-hybrid.obj')).write_text('\n'.join(lines)+'\n');print(name,'shells',len(rows),'accepted',sum(r['disposition']=='COARSE_GEOMETRY_ONLY' for r in rows),flush=True)
    (out/'component-diagnostics.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
