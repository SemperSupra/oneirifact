"""Bounded synthetic inverse CSG sequencing bakeoff.
Standalone research, not the private Foundry evaluator. Fixed grammar pool,
three disjoint occupancy sample sets, test only after selecting on validation.
"""
import json, math, sys, hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.ndimage import label
from PIL import Image, ImageDraw

# A generic coarse library, not the fixture's exact construction parameters.
def primitive(kind, center, dims):
    return {"op":kind,"center":list(center),"dims":list(dims)}
def field(p,x):
    q=x-np.array(p["center"]);d=p["dims"]
    if p["op"]=="box":
        a=np.abs(q)-np.array(d)/2
        return np.linalg.norm(np.maximum(a,0),axis=1)+np.minimum(np.max(a,axis=1),0)
    if p["op"]=="sphere":return np.linalg.norm(q,axis=1)-d[0]
    a=np.linalg.norm(q[:,:2],axis=1)-d[0];b=np.abs(q[:,2])-d[1]/2
    return np.hypot(np.maximum(a,0),np.maximum(b,0))+np.minimum(np.maximum(a,b),0)
def eval_program(prog,x):
    f=field(prog[0]["primitive"],x)
    for step in prog[1:]:
        g=field(step["primitive"],x)
        if step["combine"]=="union":f=np.minimum(f,g)
        elif step["combine"]=="intersection":f=np.maximum(f,g)
        elif step["combine"]=="difference":f=np.maximum(f,-g)
        else:raise ValueError("bad operator")
    return f
def entry(p,op="root"):return {"combine":op,"primitive":p}
def fixtures():
    z=(0,0,0)
    return {
      "drilled-box":[entry(primitive("box",z,(1.43,1.08,1.03))),entry(primitive("cylinder",(.04,-.03,0),(.29,1.65)),"difference")],
      "pipe":[entry(primitive("cylinder",z,(.66,1.23))),entry(primitive("cylinder",z,(.36,1.8)),"difference")],
      "clipped-sphere":[entry(primitive("sphere",z,(.72,))),entry(primitive("box",(0,0,.19),(1.7,1.7,.77)),"intersection")],
      "stepped-shaft":[entry(primitive("cylinder",(0,0,-.28),(.57,.83))),entry(primitive("cylinder",(0,0,.38),(.32,.69)),"union")]
    }
def library():
    z=(0,0,0);out=[]
    for d in [(1.4,1.1,1),(1.5,1.5,1.2),(1.2,1.2,1.2),(1.8,1.8,.8)]:
        for c in [z,(0,0,.2),(0,0,-.2)]:out.append(primitive("box",c,d))
    for r in [.25,.35,.45,.55,.65,.75]:
        for h in [.7,1.2,1.8]:
            for c in [z,(0,0,-.3),(0,0,.4)]:out.append(primitive("cylinder",c,(r,h)))
    for r in [.45,.6,.75]:out.append(primitive("sphere",z,(r,)))
    return out
def score(a,b):
    inter=np.count_nonzero(a&b);union=np.count_nonzero(a|b)
    return inter/max(union,1)
def search(x,y,pool,width,depth):
    mask=[field(p,x)<0 for p in pool]
    root=sorted([(score(m,y),((i,"root"),),m) for i,m in enumerate(mask)],key=lambda a:(-a[0],a[1]))
    best=root[0];front=root[:width]
    for _ in range(1,depth):
        new=[]
        for _,seq,a in front:
            for j,b in enumerate(mask):
                for op,m in (("union",a|b),("difference",a&~b),("intersection",a&b)):
                    key=seq+((j,op),);new.append((score(m,y)-.001*(len(key)-1),key,m))
        new.sort(key=lambda a:(-a[0],a[1]))
        front=new[:width]
        if front[0][0]>best[0]:best=front[0]
    return [entry(pool[i],op) for i,op in best[1]]
def refine(prog,x,y):
    # Optimize a smooth occupancy margin on training only. Bounded parameters.
    params=[];bounds=[];layout=[]
    for s in prog:
        p=s["primitive"];n=len(p["dims"]);layout.append((p["op"],s["combine"],n))
        params+=p["center"]+p["dims"];bounds += [(-.85,.85)]*3+[(.08,2.2)]*n
    def unpack(v):
        out=[];i=0
        for k,op,n in layout:
            out.append(entry(primitive(k,v[i:i+3],v[i+3:i+3+n]),op));i+=3+n
        return out
    sign=np.where(y,-1.,1.)
    def loss(v):
        f=eval_program(unpack(v),x)
        return float(np.mean(np.logaddexp(0,-sign*f/.025)))
    opt=minimize(loss,np.array(params),method="Powell",bounds=bounds,options={"maxfev":650,"ftol":1e-5})
    return unpack(opt.x)
def grid(prog,n):
    q=np.linspace(-1.15,1.15,n);xyz=np.stack(np.meshgrid(q,q,q,indexing="ij"),-1).reshape(-1,3)
    return (eval_program(prog,xyz)<0).reshape((n,n,n))
def topo(a):
    # Cubical-complex Euler characteristic, plus face-connected foreground
    # and enclosed background components on this discretization.
    n=a.shape[0];v=np.zeros((n+1,n+1,n+1),bool)
    for i in (0,1):
      for j in (0,1):
       for k in (0,1):v[i:i+n,j:j+n,k:k+n]|=a
    e=0;f=0
    for axis in range(3):
      q=np.moveaxis(a,axis,0)
      t=np.zeros((n,n+1,n+1),bool)
      for i in (0,1):
       for j in (0,1):t[:,i:i+n,j:j+n]|=q
      e+=int(t.sum())
      t=np.zeros((n+1,n,n),bool);t[:n]|=q;t[1:]|=q;f+=int(t.sum())
    bg,c=label(~np.pad(a,1,constant_values=False))
    return {"components":int(label(a)[1]),"enclosed_voids":int(c-1),"euler":int(v.sum())-e+f-int(a.sum())}
def obj(path,a):
    n=a.shape[0];step=2.3/(n-1);vertices={};faces=[]
    dirs=[(-1,0,0),(1,0,0),(0,-1,0),(0,1,0),(0,0,-1),(0,0,1)]
    for cell in np.argwhere(a):
      for axis in range(3):
       for side in (0,1):
        nb=cell.copy();nb[axis]+=2*side-1
        if np.all((nb>=0)&(nb<n)) and a[tuple(nb)]:continue
        axes=[i for i in range(3) if i!=axis];ids=[]
        for u,w in ((0,0),(1,0),(1,1),(0,1)):
            p=cell.copy();p[axis]+=side;p[axes[0]]+=u;p[axes[1]]+=w;k=tuple(int(x) for x in p)
            if k not in vertices:vertices[k]=len(vertices)+1
            ids.append(vertices[k])
        if (axis==1)==bool(side):ids.reverse()
        faces.extend([ids[:3],[ids[0],ids[2],ids[3]]])
    path.write_text("".join("v "+" ".join(f"{-1.15+(x-.5)*step:.7f}" for x in p)+"\n" for p in vertices)+"".join("f "+" ".join(map(str,f))+"\n" for f in faces))
def run(out):
    out.mkdir(parents=True,exist_ok=False);pool=library();rows=[]
    rng=np.random.default_rng(203);train=rng.uniform(-1.15,1.15,(6000,3));val=rng.uniform(-1.15,1.15,(12000,3));test=rng.uniform(-1.15,1.15,(40000,3))
    im=Image.new("RGB",(760,800),"#18212c");draw=ImageDraw.Draw(im)
    draw.text((15,10),"R203 • original occupancy / recovered / disagreement (mid-plane slices)",fill="white")
    for i,(name,truth) in enumerate(fixtures().items()):
        y=eval_program(truth,train)<0;yv=eval_program(truth,val)<0;yt=eval_program(truth,test)<0
        single=search(train,y,pool,1,1);greedy=search(train,y,pool,1,3);beam=search(train,y,pool,8,3)
        # Joint optimize after discrete structure search; compare with a
        # refine-first sequence that optimizes the single best primitive.
        variants={"single":single,"single-refine":refine(single,train,y),"greedy":greedy,"beam":beam,"beam-refine":refine(beam,train,y)}
        tv=grid(truth,40);tt=topo(tv)
        rank=[]
        for tag,p in variants.items():
            vscore=score(eval_program(p,val)<0,yv)
            tg=topo(grid(p,40))
            rank.append((tg==tt,vscore,tag,p,tg))
        eligible=[r for r in rank if r[0]]
        chosen=max(eligible or rank,key=lambda r:(r[1],-len(r[3]),r[2]))
        metrics=[]
        for ok,vs,tag,p,tg in rank:
            ts=score(eval_program(p,test)<0,yt)
            metrics.append({"pipeline":tag,"validation_iou":vs,"heldout_iou":ts,"topology":tg,"topology_match":ok,"nodes":len(p),"program":p})
        _,_,tag,p,tg=chosen;g=grid(p,40)
        row={"fixture":name,"reference_topology":tt,"chosen":tag,"admitted":tg==tt and score(eval_program(p,test)<0,yt)>=.95,"metrics":metrics};rows.append(row)
        obj(out/(name+"-reference.obj"),tv);obj(out/(name+"-recovered.obj"),g)
        (out/(name+"-program.json")).write_text(json.dumps({"reference":truth,"recovered":p,"evidence":row},indent=2))
        # visual diagnostics of actual evaluated arrays; horizontal slice through center.
        for j,a in enumerate((tv[:,:,20],g[:,:,20],tv[:,:,20]^g[:,:,20])):
            rgb=np.zeros((40,40,3),np.uint8);rgb[:]=[22,33,48];rgb[a]=[148,200,220] if j<2 else [231,117,74]
            tile=Image.fromarray(rgb).resize((165,165),Image.Resampling.NEAREST);im.paste(tile,(230+j*175,35+i*190))
        draw.text((12,50+i*190),name+"\n"+tag+"\nIoU "+format(score(eval_program(p,test)<0,yt),".4f")+"\n"+("PASS" if row["admitted"] else "HELD"),fill="white")
    im.save(out/"sequence-comparison.png")
    receipt={"schema":"r203-csg-bakeoff/v1","scope":"known synthetic grammar, standalone approximate occupancy; no historical construction uniqueness or private product parity","pool_size":len(pool),"seed":203,"results":rows}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2))
    print(json.dumps({"results":[{"fixture":r["fixture"],"chosen":r["chosen"],"admitted":r["admitted"],"scores":{m["pipeline"]:round(m["heldout_iou"],5) for m in r["metrics"]}} for r in rows]}))
if __name__=="__main__":run(Path(sys.argv[1]))
