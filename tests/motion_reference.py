"""Independent double-precision glTF animation/LBS oracle for the actual WebGL shader.

No browser evaluator or shader code is imported. Original accessors are read directly.
Every skin and rigid vertex is retained at three arbitrary times per source product; all other
named clips receive an additional complete-vertex sample. The browser compares its
actual transform-feedback positions, not target empties or the CPU helper.
"""
import argparse,json,math,struct
from pathlib import Path
import numpy as np

def read_glb(path):
    raw=path.read_bytes();assert raw[:4]==b'glTF';n=struct.unpack_from('<I',raw,12)[0]
    return json.loads(raw[20:20+n]),raw[28+n:]

def array(d,b,index):
    a=d['accessors'][index];view=d['bufferViews'][a['bufferView']]
    dtype={5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']]
    n={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']];dt=np.dtype(dtype)
    offset=view.get('byteOffset',0)+a.get('byteOffset',0);stride=view.get('byteStride',n*dt.itemsize)
    r=np.ndarray((a['count'],n),dt,b,offset,(stride,dt.itemsize)).copy().astype(np.float64)
    if a.get('normalized'):r=np.maximum(-1,r/np.iinfo(dt).max)
    return r

def rotation(q):
    q=np.asarray(q,dtype=float);q=q/np.linalg.norm(q);x,y,z,w=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])

def pose(d,b,a,time):
    translations=[np.array(n.get('translation',[0,0,0]),float) for n in d['nodes']]
    rotations=[np.array(n.get('rotation',[0,0,0,1]),float) for n in d['nodes']]
    scales=[np.array(n.get('scale',[1,1,1]),float) for n in d['nodes']]
    for c in a['channels']:
        sampler=a['samplers'][c['sampler']];times=array(d,b,sampler['input'])[:,0];values=array(d,b,sampler['output']);i=max(0,min(len(times)-1,np.searchsorted(times,time,side='right')-1));j=min(i+1,len(times)-1);v=values[i]
        if i!=j and sampler.get('interpolation','LINEAR')!='STEP':
            f=max(0,min(1,(time-times[i])/(times[j]-times[i])));u=values[j];path=c['target']['path']
            if path=='rotation':
                dot=float(v@u)
                if dot<0:u=-u;dot=-dot
                if dot>.9995:v=v+f*(u-v)
                else:
                    angle=math.acos(min(1,dot));v=(math.sin((1-f)*angle)*v+math.sin(f*angle)*u)/math.sin(angle)
                v=v/np.linalg.norm(v)
            else:v=v+f*(u-v)
        {'translation':translations,'rotation':rotations,'scale':scales}[c['target']['path']][c['target']['node']]=v
    parents={child:i for i,n in enumerate(d['nodes']) for child in n.get('children',[])};world={}
    def visit(i):
        if i in world:return world[i]
        node=d['nodes'][i]
        if 'matrix' in node:m=np.array(node['matrix']).reshape(4,4).T
        else:m=np.eye(4);m[:3,:3]=rotation(rotations[i])@np.diag(scales[i]);m[:3,3]=translations[i]
        world[i]=visit(parents[i])@m if i in parents else m
        return world[i]
    for i in range(len(d['nodes'])):visit(i)
    results=[];mesh_index=0
    for i,n in enumerate(d['nodes']):
        if 'mesh' not in n:continue
        for p in d['meshes'][n['mesh']]['primitives']:
            attrs=p['attributes'];positions=array(d,b,attrs['POSITION']);v=np.column_stack([positions,np.ones(len(positions))])
            if 'skin' not in n:
                out=(world[i]@v.T).T[:,:3];results.append((mesh_index,out,0.,'rigid',n.get('name',''),None));mesh_index+=1;continue
            skin=d['skins'][n['skin']];ibm=array(d,b,skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
            palette=np.array([world[j]@ibm[k] for k,j in enumerate(skin['joints'])]);out=np.zeros((len(v),3));eight=np.zeros_like(out)
            sets=sorted(int(k[8:]) for k in attrs if k.startswith('WEIGHTS_'))
            for s in sets:
                joints=array(d,b,attrs['JOINTS_'+str(s)]).astype(int);weights=array(d,b,attrs['WEIGHTS_'+str(s)])
                for k in range(4):
                    contribution=np.einsum('nij,nj->ni',palette[joints[:,k]],v)[:,:3]*weights[:,k,None];out+=contribution
                    if s<2:eight+=contribution
            results.append((mesh_index,out,float(np.max(np.linalg.norm(out-eight,axis=1))),'skin',n.get('name',''),n['skin']));mesh_index+=1
    return results

def build(site,out):
    out.mkdir(parents=True,exist_ok=False);index=json.loads((site/'motion/catalogs.json').read_text());rows=[];offset=0;worst_negative=0
    with (out/'positions.bin').open('wb') as f:
        for entry in index['packs']:
            root=site/'motion'/entry['base_url'];catalog=json.loads((site/'motion'/entry['catalog']).read_text())
            for p in catalog['packages']:
                d,b=read_glb(root/p['assets']['model']['path']);animations={a['name']:a for a in d['animations']};primary=next((c for c in p['clips'] if c['id']=='walking'),p['clips'][0])['animation_name'];samples=[]
                for clip in p['clips']:
                    times=[clip['duration_s']*s for s in ([.137,.513,.883] if clip['animation_name']==primary else [.413])]
                    for t in times:
                        for mesh,positions,truncation,kind,node_name,skin_index in pose(d,b,animations[clip['animation_name']],t):
                            raw=positions.astype('<f4').tobytes();f.write(raw);samples.append({'animation':clip['animation_name'],'time_s':t,'mesh':mesh,'kind':kind,'node_name':node_name,'skin_index':skin_index,'vertices':len(positions),'offset_bytes':offset,'length_bytes':len(raw),'eight_slot_omission_max_error_m':truncation});offset+=len(raw);worst_negative=max(worst_negative,truncation)
                rows.append({'id':p['id'],'model_path':entry['base_url']+p['assets']['model']['path'],'model_sha256':p['assets']['model']['sha256'],'animation_names':[c['animation_name'] for c in p['clips']],'actor_count':len(p['actors']),'samples':samples})
    assert len(rows)>=17 and worst_negative>.00005,'Ninth influence negative must be observable'
    report={'schema':'oneirifact.motion-browser-independent-position-oracle/v1','method':'Independent Python double-precision TRS, hemisphere SLERP, hierarchical transforms, complete-set linear blend skinning and rigid node transforms. Compare actual GPU transform feedback for every source skin and rigid vertex.','tolerance_m':0.00005,'source_products':rows,'total_position_bytes':offset,'eight_slot_omission_max_error_m':worst_negative}
    (out/'oracle.json').write_text(json.dumps(report,indent=2)+'\n');print('MOTION_REFERENCE_READY',len(rows),sum(len(p['samples']) for p in rows),offset,worst_negative)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('site',type=Path);a.add_argument('out',type=Path);args=a.parse_args();build(args.site,args.out)
