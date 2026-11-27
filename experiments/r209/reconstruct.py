"""Recover rectangular LDraw family recipes from actual subfile references.
Independent reference evaluation. Native-shaped JSON is a candidate, not native admission.
"""
import hashlib,json,sys,zipfile
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes
from PIL import Image,ImageDraw,ImageFont

IDS=("3001","3002","3003","3004","3005","3020","3022")
EXPECTED={"3001":8,"3002":6,"3003":4,"3004":2,"3005":1,"3020":8,"3022":4}
def check(x,m):
    if not x:raise RuntimeError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def read(root):
    for aid in (15232521230,15232132427):
        with zipfile.ZipFile(root/f"github-actions-artifact-{aid}.zip") as z:
            manifest=json.loads(z.read("manifest.json"))
            check(manifest["library_zip_sha256"]=="023083918da2d3697c794fb4267975509584f3611b993095874206a803fa610f","library identity")
            for row in manifest["results"]:
                id=row["id"];a=json.loads(z.read(id+"/ATTRIBUTION.json"))
                for k,v in a["files"].items():check(sha(z.read(id+"/source/"+k))==v["sha256"],"source drift")
                vertices=[];faces=[]
                for l in z.read(id+"/part.obj").decode().splitlines():
                    t=l.split()
                    if t and t[0]=="v":vertices.append([float(x) for x in t[1:]])
                    if t and t[0]=="f":faces.append([int(x)-1 for x in t[1:]])
                yield id,a,np.array(vertices),np.array(faces),row
def xyz(t):return np.array([t[0],t[2],-t[1]])*.0004
def occurrences(a):
    result=[]
    def visit(k,M,T,path):
        check(len(path)<32 and k not in path,"cycle")
        for i,r in enumerate(a["files"][k]["references"]):
            N=M@np.array(r["matrix"]);U=T+M@np.array(r["translation_ldu"]);name=r["file"]
            if name in ("p/stud.dat","p/stud2.dat","p/stud3.dat","p/stud4.dat","p/peghole.dat") or name=="p/box5.dat" and r["invert_next"]:
                result.append(dict(name=name,center=xyz(U).tolist(),matrix=N.tolist(),path=path+[k,f"ref:{i}"],source=a["files"][name]["sha256"]))
            else:visit(name,N,U,path+[k])
    visit(a["part"],np.eye(3),np.zeros(3),[])
    return result
class Recipe:
    def __init__(self,id):self.id=id;self.nodes=[]
    def add(self,op,p=None,ch=None):
        id=f"f{len(self.nodes)}";d={"id":id,"op":op}
        if p is not None:d["params"]={k:float(v) for k,v in p.items()}
        if ch:d["inputs"]=ch
        self.nodes.append(d);return id
    def box(self,d):return self.add("box",dict(zip(("width","depth","height"),np.array(d)*10)))
    def cylinder(self,r,h):return self.add("cylinder",{"radius":r*10,"height":h*10})
    def at(self,id,c):return self.add("translate",dict(zip("xyz",np.array(c)*10)),[id])
    def boolean(self,a,b,op):return self.add(op,None,[a,b])
    def finish(self,r):
        root=self.add("scale",{"factor":.1},[r])
        return {"schema":"oneirifact.graph/v0.1","name":"LDraw reference "+self.id+" hypothesis","unit":"m","detail":32,"root":root,"features":self.nodes}
def graph(id,v,refs):
    lo,hi=v.min(0),v.max(0);h=-lo[2];d=hi[:2]-lo[:2]
    cavities=[r for r in refs if r["name"]=="p/box5.dat"];check(len(cavities)==1,"rectangular cavity")
    cv=cavities[0];m=np.array(cv["matrix"]);check(np.allclose(m,np.diag(np.diag(m))),"non-axis cavity")
    dims=np.abs(np.diag(m));inner=dims[[0,2]]*.0008;depth=dims[1]*.0004;eps=.0001
    r=Recipe(id);root=r.at(r.box([*d,h]),[0,0,-h/2])
    root=r.boolean(root,r.at(r.box([*inner,depth+eps]),[0,0,-h+depth/2-eps/2]),"difference")
    studs=[x for x in refs if x["name"]=="p/stud.dat"];check(len(studs)==EXPECTED[id],"stud count")
    # Primitive dimensions inferred from known LDraw primitive refs and source coordinate convention.
    stud=r.cylinder(.0024,.0016+eps)
    for x in studs:root=r.boolean(root,r.at(stud,np.array(x["center"])+[0,0,(.0016-eps)/2]),"union")
    for x in refs:
        if x["name"] not in ("p/stud3.dat","p/stud4.dat"):continue
        m=np.array(x["matrix"]);check(np.allclose(m,np.diag(np.diag(m))),"non-axis underside")
        length=abs(m[1,1])*.0016;c=np.array(x["center"])-[0,0,(length-eps)/2]
        rad=.0032 if x["name"]=="p/stud4.dat" else .0016
        tube=r.cylinder(rad,length+eps)
        if x["name"]=="p/stud4.dat":tube=r.boolean(tube,r.cylinder(.0024,length+3*eps),"difference")
        root=r.boolean(root,r.at(tube,c),"union")
    g=r.finish(root);nodes={x["id"]:x for x in g["features"]}
    def cost(id):return 1+sum(cost(c) for c in nodes[id].get("inputs",[]))
    visits=cost(g["root"])
    check(visits<=256 and visits*33**3<=8000000,"expression budget")
    for n in g["features"]:
        for k,x in n.get("params",{}).items():
            if k in ("height","width","depth","radius"):check(.01<=x<=20,"primitive dimension")
    return g,{"body_height_m":float(h),"studs":len(studs),"cavity_width_depth_m":inner.tolist(),"cavity_depth_m":float(depth),"expression_visits":visits}
def field(g,q):
    nodes={x["id"]:x for x in g["features"]}
    def f(k,p):
        x=nodes[k];o=x["op"];a=x.get("params",{});c=x.get("inputs",[])
        if o=="box":
            v=np.abs(p)-np.array([a["width"],a["depth"],a["height"]])/2
            return np.linalg.norm(np.maximum(v,0),axis=-1)+np.minimum(np.max(v,axis=-1),0)
        if o=="cylinder":
            v=np.stack([np.linalg.norm(p[...,:2],axis=-1)-a["radius"],abs(p[...,2])-a["height"]/2],axis=-1)
            return np.linalg.norm(np.maximum(v,0),axis=-1)+np.minimum(np.max(v,axis=-1),0)
        if o=="translate":return f(c[0],p-np.array([a[i] for i in "xyz"]))
        if o=="scale":return a["factor"]*f(c[0],p/a["factor"])
        A=f(c[0],p);B=f(c[1],p);return np.minimum(A,B) if o=="union" else np.maximum(A,-B)
    return f(g["root"],q)
def mesh(g,v,step):
    lo=v.min(0)-step*2;hi=v.max(0)+step*2;axes=[np.arange(a,b+step,step) for a,b in zip(lo,hi)]
    check(np.prod([len(a) for a in axes])<2000000,"grid budget")
    arr=np.empty(tuple(map(len,axes)),np.float32)
    X,Y=np.meshgrid(axes[0],axes[1],indexing="ij")
    for i,z in enumerate(axes[2]):arr[:,:,i]=field(g,np.stack((X,Y,np.full_like(X,z)),-1))
    pv,pf,_,_=marching_cubes(arr,level=0,spacing=(step,)*3,allow_degenerate=False)
    return pv+lo,pf[:,::-1]
def sample(v,f,n,seed):
    tri=v[f];a=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)
    rng=np.random.default_rng(seed);t=tri[rng.choice(len(f),n,p=a/a.sum())];u=rng.random((n,2));u[u.sum(1)>1]=1-u[u.sum(1)>1];return t[:,0]+u[:,0,None]*(t[:,1]-t[:,0])+u[:,1,None]*(t[:,2]-t[:,0])
def metric(v,f,pv,pf):
    a=sample(v,f,40000,209);b=sample(pv,pf,40000,210);x=cKDTree(a).query(b)[0];y=cKDTree(b).query(a)[0]
    return {"sampled_symmetric_rmse_mm":float(np.sqrt((np.mean(x*x)+np.mean(y*y))/2)*1000),"coverage_within_0p3mm":float(min(np.mean(x<=.0003),np.mean(y<=.0003)))}
def obj(path,v,f):
    path.write_text("# Derived from LDraw CC BY 4.0; source attribution accompanies archive\n"+"".join("v %.9f %.9f %.9f\n"%tuple(x) for x in v)+"".join("f %d %d %d\n"%tuple(x+1) for x in f))
def main(root,out,lane):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for id,a,v,f,row in read(root):
        refs=occurrences(a);d=out/id;d.mkdir();(d/"attribution.json").write_text(json.dumps(a,indent=2));(d/"recognized-references.json").write_text(json.dumps(refs,indent=2))
        if lane=="ports":
            ports=[dict(id=f"port{i}",kind=x["name"],position_m=x["center"],source_path=x["path"],source_sha256=x["source"],status="REFERENCE_ANCHOR_ONLY") for i,x in enumerate(refs) if x["name"] in ("p/stud.dat","p/stud2.dat","p/peghole.dat")]
            (d/"ports.json").write_text(json.dumps(ports,indent=2))
            rows.append({"id":id,"reference_anchors":len(ports),"status":"PROPOSAL_NOT_MATING_PROOF"});continue
        if id not in IDS:rows.append({"id":id,"status":"HELD_COMPLEX_SHAPE"});continue
        g,params=graph(id,v,refs);(d/"graph.json").write_text(json.dumps(g,indent=2))
        pv,pf=mesh(g,v,.0002);m=metric(v,f,pv,pf)
        obj(d/"reference.obj",v,f);obj(d/"candidate.obj",pv,pf)
        rows.append({"id":id,"parameters":params,"features":len(g["features"]),"comparison":m,"status":"NATIVE_SCHEMA_CANDIDATE_NOT_VALIDATED","mesh_step_m":.0002})
    (out/"receipt.json").write_text(json.dumps({"lane":lane,"source":"R208 exact official library closures","scope":"reference-only, no actual native engine, topology or physical mating proof","results":rows},indent=2))
    print(json.dumps(rows))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
