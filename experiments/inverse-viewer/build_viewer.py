import sys,zipfile,json,base64
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'inverse-r201'))
from fit import read_glb
root=Path(sys.argv[1]); result=Path(sys.argv[2]); output=Path(sys.argv[3])
assets={'Avocado':15229781019,'Lantern':15228548803,'WaterBottle':15228334677}
def obj(path):
 v=[]; f=[]; groups=[]; color=[]; g=0
 for l in path.read_text().splitlines():
  if l.startswith('o '): g=1 if 'COARSE_GEOMETRY_ONLY' in l else 0
  elif l.startswith('v '): v.append([float(x) for x in l.split()[1:]])
  elif l.startswith('f '): f.append([int(x.split('/')[0])-1 for x in l.split()[1:]]); color.append(g)
 return np.array(v),np.array(f),np.array(color)
def pack(v,f,c):
 # Explicit triangle positions, flat normals generated on GPU, per-face color indicator.
 tri=v[f].astype('<f4'); n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]); n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-12)
 data=np.concatenate([tri,np.repeat(n[:,None,:],3,axis=1),np.repeat(c[:,None,None],3,axis=1)],axis=2).astype('<f4')
 return base64.b64encode(data.tobytes()).decode()
models={}
for name,id in assets.items():
 with zipfile.ZipFile(root/f'github-actions-artifact-{id}.zip') as z: parts=read_glb(z.read('normalized.glb'))
 v=[]; f=[]; offset=0
 for pv,pf in parts.values(): v.extend(pv);f.extend(pf+offset);offset+=len(pv)
 v=np.array(v);f=np.array(f); center=(v.max(0)+v.min(0))/2;scale=np.ptp(v,axis=0).max()
 models[name]={'original':pack((v-center)/scale,f,np.zeros(len(f))), 'sourceFaces':len(f)}
 for kind in ['candidate','hybrid']:
  a,b,c=obj(result/f'{name}-{kind}.obj'); models[name][kind]=pack((a-center)/scale,b,c if kind=='hybrid' else np.ones(len(b)));models[name][kind+'Faces']=len(b)

html=Path(__file__).with_name("template.html").read_text()
output.write_text(html.replace("__MODELS__",json.dumps(models,separators=(",",":"))))
print("Viewer generated", output.stat().st_size)
