"""Original modular construction graph candidates, independent reference mesher.
Not manufacturer CAD, physical fit qualification or private Foundry execution.
All geometry is authored from first principles; demo models explicitly 10x.
"""
import sys, json, math, hashlib, time
from pathlib import Path
import numpy as np
from skimage.measure import marching_cubes
from PIL import Image,ImageDraw

class Recipe:
    def __init__(self,name):self.name=name;self.nodes=[]
    def add(self,op,params=None,inputs=None):
        id=f"f{len(self.nodes)}";d={"id":id,"op":op}
        if inputs:d["inputs"]=inputs
        if params:d["params"]=params
        self.nodes.append(d);return id
    def box(self,w,d,h):return self.add("box",dict(width=w,depth=d,height=h))
    def cyl(self,r,h):return self.add("cylinder",dict(radius=r,height=h))
    def at(self,a,x,y,z):return self.add("translate",dict(x=x,y=y,z=z),[a])
    def boolean(self,a,b,op):return self.add(op,inputs=[a,b])
    def graph(self,root):return dict(schema="oneirifact.graph/v0.1",name=self.name,unit="m",detail=32,root=root,features=self.nodes)
def brick(scale,name):
    # Independent illustrative dimensions. Not a copy of commercial CAD.
    p=.008*scale;w=2*p-.0002*scale;h=.0096*scale;t=.0015*scale
    r=Recipe(name);outer=r.box(w,w,h)
    cavity=r.at(r.box(w-2*t,w-2*t,h-t+.0004*scale),0,0,-t/2-.0002*scale)
    root=r.boolean(outer,cavity,"difference")
    stud=r.cyl(.0024*scale,.002*scale)
    for x in (-p/2,p/2):
        for y in (-p/2,p/2):
            root=r.boolean(root,r.at(stud,x,y,h/2+.0008*scale),"union")
    return r.graph(root),{"pitch":p,"width":w,"height":h,"stud_radius":.0024*scale,"wall":t,"engagement":.0018*scale}
def log(scale,name):
    r=Recipe(name);l=.048*scale;w=.008*scale;h=.008*scale
    root=r.box(l,w,h);cut=r.box(w+.0004*scale,w+.002*scale,h/2+.001*scale)
    for x in (-.016*scale,.016*scale):root=r.boolean(root,r.at(cut,x,0,-h/4-.0005*scale),"difference")
    return r.graph(root),{"length":l,"width":w,"height":h,"notch_spacing":.032*scale,"course_step":h/2}
def field(graph,p):
    nodes={n["id"]:n for n in graph["features"]}
    def f(k,q):
        n=nodes[k];a=n.get("params",{});o=n["op"];ch=n.get("inputs",[])
        if o=="box":
            v=np.abs(q)-np.array([a["width"],a["depth"],a["height"]])/2
            return np.linalg.norm(np.maximum(v,0),axis=-1)+np.minimum(np.max(v,axis=-1),0)
        if o=="cylinder":
            v=np.stack([np.linalg.norm(q[...,:2],axis=-1)-a["radius"],abs(q[...,2])-a["height"]/2],axis=-1)
            return np.linalg.norm(np.maximum(v,0),axis=-1)+np.minimum(np.max(v,axis=-1),0)
        if o=="translate":return f(ch[0],q-np.array([a[x] for x in "xyz"]))
        l=f(ch[0],q);r=f(ch[1],q)
        return np.minimum(l,r) if o=="union" else np.maximum(l,-r) if o=="difference" else np.maximum(l,r)
    return f(graph["root"],p)
def mesh(g,extent,step):
    axes=[np.arange(-x,x+step*.5,step) for x in extent]
    q=np.stack(np.meshgrid(*axes,indexing="ij"),axis=-1)
    values=field(g,q)
    v,f,_,_=marching_cubes(values,level=0,spacing=(step,)*3,allow_degenerate=False)
    return v+np.array([a[0] for a in axes]),f[:,::-1]
def rot(v,deg):
    a=np.radians(deg);c,s=np.cos(a),np.sin(a)
    return v@np.array([[c,-s,0],[s,c,0],[0,0,1]]).T
def obj(path,parts):
    lines=[];i=1
    for name,v,f in parts:
        lines.append("o "+name);lines.extend("v %.8f %.8f %.8f"%tuple(q) for q in v);lines.extend("f %d %d %d"%tuple(q+i) for q in f);i+=len(v)
    path.write_text("\n".join(lines)+"\n")
def visual(path,parts,title,caption):
    W,H=1200,800;im=Image.new("RGB",(W,H),"#18212c");d=ImageDraw.Draw(im)
    from PIL import ImageFont
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",32);small=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",20)
    d.text((30,24),title,font=font,fill="white");d.text((30,72),caption,font=small,fill="#b3c5d6")
    a,b=np.radians([36,55]);R=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])@np.array([[1,0,0],[0,np.cos(b),-np.sin(b)],[0,np.sin(b),np.cos(b)]])
    vv=np.concatenate([v for _,v,_ in parts]);center=(vv.min(0)+vv.max(0))/2
    q=(vv-center)@R;scale=min(1050/max(np.ptp(q[:,0]),1e-9),610/max(np.ptp(q[:,1]),1e-9));tris=[]
    colors=[(202,83,76),(81,149,209),(224,184,78),(103,173,137)] if "log" not in title.lower() else [(179,125,72),(204,151,92),(158,107,62)]
    for i,(_,v,f) in enumerate(parts):
        p=(v-center)@R;t=p[f];xy=np.stack([600+p[:,0]*scale,447-p[:,1]*scale],axis=-1)
        norms=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);norms/=np.maximum(np.linalg.norm(norms,axis=1)[:,None],1e-12)
        shade=.42+.58*np.abs(norms@np.array([.32,.52,.79]));color=np.array(colors[i%len(colors)])
        tris.extend((z,tuple(map(tuple,xy[face])),tuple((color*s).astype(int))) for z,face,s in zip(t[:,:,2].mean(1),f,shade))
    for _,p,c in sorted(tris,key=lambda x:x[0]):d.polygon(p,fill=c)
    im.save(path)
def main(family,out):
    out.mkdir(parents=True,exist_ok=False);scale=10 if family!="large" else 20
    builder=log if family=="logs" else brick
    g,d=builder(scale,family+"-demonstrator");physical,_=builder(scale/10,family+"-physical-candidate")
    (out/"component.graph.json").write_text(json.dumps(g,indent=2));(out/"physical-candidate.graph.json").write_text(json.dumps(physical,indent=2))
    if family=="logs":
        v,f=mesh(g,(.026*scale,.006*scale,.006*scale),.00055*scale)
        placements=[(f"course-{z}-{i}",(0,a,z*d["course_step"]) if z%2==0 else (a,0,z*d["course_step"]),0 if z%2==0 else 90) for z in range(5) for i,a in enumerate((-.016*scale,.016*scale))]
    else:
        v,f=mesh(g,(d["width"]/2+.002*scale,d["width"]/2+.002*scale,d["height"]/2+.004*scale),.00033*scale)
        p=d["pitch"];h=d["height"]
        placements=[(f"brick-{z}-{x}",(x*2*p+(p if z%2 else 0),0,z*h),0) for z in range(3) for x in range(3 if z%2==0 else 2)]
    parts=[(name,rot(v,a)+np.array(t),f) for name,t,a in placements]
    obj(out/"component.obj",[("component",v,f)]);obj(out/"assembly.obj",parts)
    instances=[{"id":name,"definition_id":family+"-demonstrator","composition_mode":"scene_assembly","transform":{"translation":list(t),"rotation":[0,0,a],"scale":1}} for name,t,a in placements]
    (out/"assembly-candidate.json").write_text(json.dumps({"schema":"oneirifact.scene/v0.1","id":family+"-assembly","name":family+" assembly","composition_mode":"scene_assembly","instances":instances},indent=2))
    (out/"component-definition-candidate.json").write_text(json.dumps({"schema":"oneirifact.component/v0.1","id":family+"-demonstrator","name":family+" demonstrator","unit":"m","graph":g},indent=2))
    # Sample exact continuous membership independently of triangle discretization.
    if family=="logs":
        assert field(g,np.array([[0,0,0],[.016*scale,0,-.002*scale],[.016*scale,0,.002*scale]])).tolist()[0]<0
        assert field(g,np.array([[.016*scale,0,-.002*scale]]))[0]>0
    else:
        assert field(g,np.array([[0,0,-d["height"]*.35]]))[0]>0
        assert field(g,np.array([[d["pitch"]/2,d["pitch"]/2,d["height"]/2+.001*scale]]))[0]<0
    physical_below=[(n["id"],k,x) for n in physical["features"] for k,x in n.get("params",{}).items() if k in ("radius","width","depth","height") and x<.01]
    visual(out/"assembly.png",parts,family.title()+" construction — independent graph reference","10x demonstration scale • distinct reusable instances • not native mesher or physical fit proof")
    visual(out/"component.png",[("component",v,f)],family.title()+" reusable component","Procedural Boolean graph • original design")
    receipt={"family":family,"demonstration_scale":10,"dimensions_m":d,"instances":len(parts),"component_triangles":len(f),"graph_features":len(g["features"]),"physical_dimensions_below_current_minimum":physical_below,"native_status":"SCHEMA_CANDIDATE_NOT_PRODUCT_VALIDATED","reference_membership_checks":"PASS","assembly_collision":"NOT_RUN","definition_pins":"NOT_COMPUTED_USE_NATIVE_HASH","files":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=="__main__":main(sys.argv[1],Path(sys.argv[2]))
