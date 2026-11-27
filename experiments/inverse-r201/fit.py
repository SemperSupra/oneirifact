"""R201 diagnostic: fixed normalized GLB meshes, held-out area samples and symmetric coverage.
Uses original input geometry only; model units normalized by max global extent.
"""
import io,json,struct,zipfile,hashlib,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from scipy.optimize import least_squares

from loft import loft
N=16000

def read_glb(raw):
    magic,version,length,n,kind=struct.unpack_from('<4sIII4s',raw)
    assert (magic,version,length,kind)==(b'glTF',2,len(raw),b'JSON')
    doc=json.loads(raw[20:20+n]); off=28+n
    def acc(i):
        a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']]; dt=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]); k={'SCALAR':1,'VEC3':3}[a['type']]; start=off+v.get('byteOffset',0)+a.get('byteOffset',0); stride=v.get('byteStride',k*dt.itemsize)
        return np.ndarray((a['count'],k),dtype=dt,buffer=raw,offset=start,strides=(stride,dt.itemsize)).copy()
    parts={}
    for node in doc['nodes']:
        assert not any(k in node for k in ('translation','rotation','scale','matrix','children'))
        if 'mesh' not in node:continue
        vs=[];fs=[];base=0
        for p in doc['meshes'][node['mesh']]['primitives']:
            assert p.get('mode',4)==4
            v=acc(p['attributes']['POSITION']).astype(float); f=acc(p['indices']).reshape(-1,3).astype(int);vs.append(v);fs.append(f+base);base+=len(v)
        parts[node['name']]=(np.concatenate(vs),np.concatenate(fs))
    return parts

def sample(v,f,n,seed):
    tri=v[f];area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
    rng=np.random.default_rng(seed);t=tri[rng.choice(len(f),n,p=area/area.sum())];u=rng.random((n,2));u[u.sum(axis=1)>1]=1-u[u.sum(axis=1)>1];return t[:,0]+u[:,0,None]*(t[:,1]-t[:,0])+u[:,1,None]*(t[:,2]-t[:,0])

def box(c,s):
    v=np.array([[x,y,z] for x in [-1,1] for y in [-1,1] for z in [-1,1]])*s/2+c
    f=np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],[2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]])
    return v,f

def revolve(c,axis,ys,rs):
    rad=[i for i in range(3) if i!=axis];n=96;theta=np.arange(n)*2*np.pi/n;v=np.zeros((len(ys)*n+2,3));f=[]
    for j,(y,r) in enumerate(zip(ys,rs)):
        v[j*n:(j+1)*n,axis]=y;v[j*n:(j+1)*n,rad[0]]=r*np.cos(theta);v[j*n:(j+1)*n,rad[1]]=r*np.sin(theta)
        for i in range(n):
            k=(i+1)%n
            if j: f.extend((( (j-1)*n+i,(j-1)*n+k,j*n+k),((j-1)*n+i,j*n+k,j*n+i)))
    v[-2,axis]=ys[0];v[-1,axis]=ys[-1]
    for i in range(n):
        k=(i+1)%n;f.extend(((len(v)-2,k,i),(len(v)-1,(len(ys)-1)*n+i,(len(ys)-1)*n+k)))
    return v+c,np.array(f)

def ellipsoid(c,r):
    # latitude rings with nonzero tiny radius at poles; caps close the surface.
    t=np.linspace(-np.pi/2,np.pi/2,65);v,f=revolve(np.zeros(3),1,np.sin(t),np.maximum(1e-6,np.cos(t)));return v*r+c,f

def metrics(test,v,f,seed=99,extent=1.):
    q=sample(v,f,N,seed);a=cKDTree(q).query(test)[0];b=cKDTree(test).query(q)[0]
    return {'forward_rmse':float(np.sqrt(np.mean(a*a))),'reverse_rmse':float(np.sqrt(np.mean(b*b))),'symmetric_rmse':float(np.sqrt((np.mean(a*a)+np.mean(b*b))/2)),'p95':float(max(np.quantile(a,.95),np.quantile(b,.95))),'coverage_2pct':float(min(np.mean(a<=.02),np.mean(b<=.02))),'coverage_2pct_part':float(min(np.mean(a<=.02*extent),np.mean(b<=.02*extent)))}

def proposals(v,f,train):
    lo=v.min(0);hi=v.max(0);c=(lo+hi)/2;s=hi-lo;axis=int(np.argmax(s));rad=[i for i in range(3) if i!=axis];half=s/2
    yield 'box',*box(c,s),{'center':c.tolist(),'size':s.tolist()}
    yield 'cylinder',*revolve(c,axis,[-half[axis],half[axis]],[np.mean(half[rad])]*2),{'center':c.tolist(),'axis':axis,'radius':float(np.mean(half[rad])),'height':float(s[axis])}
    def residual(q):
        cc=q[:3]; rr=np.exp(q[3:]);return (np.linalg.norm((train-cc)/rr,axis=1)-1)*min(rr)
    opt=least_squares(residual,np.r_[c,np.log(np.maximum(half,1e-5))],max_nfev=100,bounds=(np.r_[lo,np.log(np.maximum(half*.25,1e-6))],np.r_[hi,np.log(np.maximum(half*4,1e-5))]))
    cc=opt.x[:3];rr=np.exp(opt.x[3:]);yield 'ellipsoid',*ellipsoid(cc,rr),{'center':cc.tolist(),'radii':rr.tolist()}
    # Use source vertex levels to preserve shoulders and lip steps; radius
    # fitted from train area samples in local slabs, not held-out test points.
    y=train[:,axis]-c[axis];r=np.linalg.norm(train[:,rad]-c[rad],axis=1)
    levels=np.unique(np.round(v[:,axis]-c[axis],5)); levels=np.sort(levels)
    # Limit degrees of freedom to 32 knots, choose geometry-informed levels.
    if len(levels)>32: levels=np.unique(np.quantile(levels,np.linspace(0,1,32)))
    levels[0]=-half[axis];levels[-1]=half[axis]
    radii=[]
    for j,k in enumerate(levels):
        width=max(.004*s[axis],min(abs(k-levels[j-1]) if j else np.inf,abs(levels[j+1]-k) if j+1<len(levels) else np.inf)*.45)
        mask=np.abs(y-k)<=width
        if mask.sum()<20:mask=np.argsort(np.abs(y-k))[:30];vals=r[mask]
        else:vals=r[mask]
        radii.append(float(np.quantile(vals,.85)))
    yield 'revolved-profile',*revolve(c,axis,levels,radii),{'center':c.tolist(),'axis':axis,'levels':levels.tolist(),'radii':radii}
    yield 'section-loft',*loft(v,train)

def topology(v,f):
    # Weld UV/normal seam duplicates before mesh connectivity analysis.
    _,ix=np.unique(np.round(v,6),axis=0,return_inverse=True); faces=ix[f];faces=faces[(faces[:,0]!=faces[:,1])&(faces[:,1]!=faces[:,2])&(faces[:,0]!=faces[:,2])]
    edges=np.sort(np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]])),axis=1);edges,count=np.unique(edges,axis=0,return_counts=True)
    par=list(range(int(ix.max())+1))
    def find(a):
        while par[a]!=a:par[a]=par[par[a]];a=par[a]
        return a
    for a,b in edges:par[find(a)]=find(b)
    used=np.unique(faces);components=len({find(a) for a in used})
    return {'components':components,'boundary_edges':int(sum(count==1)),'nonmanifold_edges':int(sum(count>2)),'euler':int(len(used)-len(edges)+len(faces))}

def run(root):
    result={};meshout={}
    for name,aid in [('Avocado',15229781019),('Lantern',15228548803),('WaterBottle',15228334677)]:
        with zipfile.ZipFile(root/f'github-actions-artifact-{aid}.zip') as z:
            raw=z.read('normalized.glb');receipt=json.loads(z.read('receipt.json'));assert hashlib.sha256(raw).hexdigest()==receipt['files']['normalized.glb'];parts=read_glb(raw)
        result[name]={};meshout[name]={}
        for part,(v,f) in parts.items():
            train=sample(v,f,10000,31);validation=sample(v,f,N,72);test=sample(v,f,N,173);rows={};meshes={};extent=float(np.ptp(v,axis=0).max())
            for kind,pv,pf,params in proposals(v,f,train):
                m=metrics(validation,pv,pf,extent=extent);m['part_extent']=extent;m['part_normalized_rmse']=m['symmetric_rmse']/extent;rows[kind]={'metrics':m,'parameters':params};meshes[kind]=(pv,pf)
            best=min(rows,key=lambda k:rows[k]['metrics']['symmetric_rmse']); final=metrics(test,*meshes[best],seed=201,extent=extent);final['part_normalized_rmse']=final['symmetric_rmse']/extent;source_topo=topology(v,f);candidate_topo=topology(*meshes[best]);status='COARSE_GEOMETRY_ONLY' if final['coverage_2pct_part']>=.95 and source_topo==candidate_topo else 'RETAIN_SOURCE_MESH';result[name][part]={'vertices':len(v),'faces':len(f),'best':best,'candidates':rows,'final_independent_sample':final,'source_topology':source_topo,'candidate_topology':candidate_topo,'disposition':status};meshout[name][part]=(v,f,*meshes[best]);print(name,part,best,{k:round(x['metrics']['symmetric_rmse'],5) for k,x in rows.items()},'coverage',round(rows[best]['metrics']['coverage_2pct'],3),flush=True)
    return result,meshout
if __name__=='__main__':
    root=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(exist_ok=True,parents=True);result,meshes=run(root);(out/'diagnostics.json').write_text(json.dumps(result,indent=2));
    for asset,parts in meshes.items():
        # OBJ with independently named recovered components, editable analytic parameters in JSON.
        lines=[];offset=1
        for part,(_,_,v,f) in parts.items():
            lines.append('o '+part+'-candidate');lines.extend('v %.8f %.8f %.8f'%tuple(x) for x in v);lines.extend('f %d %d %d'%tuple(x+offset) for x in f);offset+=len(v)
        (out/(asset+'-candidate.obj')).write_text('\n'.join(lines)+'\n')
