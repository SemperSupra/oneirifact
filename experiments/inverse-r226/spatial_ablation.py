"""Original synthetic CSG spatial-holdout ablation; independent of Foundry.
Topology-conditioned selection receives an explicit whole-object topology prior,
not a blind inference claim. All new fitting uses only the observed region.
"""
import sys,json,zipfile,hashlib,time,resource,copy
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from skimage.measure import marching_cubes
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"inverse-r203"))
import sequence_bakeoff as old

PIN="18466d8357a5eaae05032efa54aa55cad5cb651b0623cbb5e1663c6c6cf1c237"
def load(path):
    assert hashlib.sha256(path.read_bytes()).hexdigest()==PIN
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        return json.loads(z.read("receipt.json"))
def grid(p,n):
    q=np.linspace(-1.15,1.15,n)
    x=np.stack(np.meshgrid(q,q,q,indexing="ij"),-1).reshape(-1,3)
    return old.eval_program(p,x).reshape((n,n,n))
def topology(p):
    return [old.topo(grid(p,n)<0) for n in (32,64)]
def metrics(p,x,y):
    q=old.eval_program(p,x)<0
    return {"iou":old.score(q,y),"precision":float((q&y).sum()/max(q.sum(),1)),"recall":float((q&y).sum()/max(y.sum(),1))}
def mesh(p,n):
    a=grid(p,n);assert a.min()<0<a.max()
    assert min(a[0].min(),a[-1].min(),a[:,0].min(),a[:,-1].min(),a[:,:,0].min(),a[:,:,-1].min())>0
    v,f,_,_=marching_cubes(a,0,spacing=(2.3/(n-1),)*3,allow_degenerate=False)
    v=v-1.15
    ed=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
    _,c=np.unique(ed,axis=0,return_counts=True)
    return v,f,{"vertices":len(v),"triangles":len(f),"boundary_edges":int((c==1).sum()),"nonmanifold_edges":int((c>2).sum()),"euler":len(v)-len(c)+len(f)}
def export(path,v,f):
    path.write_text("".join("v %.8f %.8f %.8f\n"%tuple(a) for a in v)+"".join("f %d %d %d\n"%tuple(a+1) for a in f))
def render(v,f,angle):
    # Orthographic actual triangle painter; no claim of exact occlusion.
    a,b=angle
    R=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])
    T=np.array([[1,0,0],[0,np.cos(b),-np.sin(b)],[0,np.sin(b),np.cos(b)]])
    p=v@R.T@T.T;xy=p[:,[0,2]]*62+np.array([90,85]);xy[:,1]=170-xy[:,1]
    im=Image.new("RGB",(180,170),"#17232f");d=ImageDraw.Draw(im)
    norm=np.cross(p[f[:,1]]-p[f[:,0]],p[f[:,2]]-p[f[:,0]])
    norm/=np.maximum(np.linalg.norm(norm,axis=1)[:,None],1e-20)
    for i in np.argsort(p[f,1].mean(axis=1)):
        lit=.40+.60*abs(norm[i]@np.array([.3,.9,.316]))
        d.polygon([tuple(a) for a in xy[f[i]]],fill=tuple(int(z*lit) for z in (153,202,217)))
    return im
def sample(rng,n,held):
    # Spatially disjoint block; no samples from the withheld x slab for new search.
    x=rng.uniform(-1.15,1.15,(n,3))
    x[:,0]=rng.uniform(.22,1.15,n) if held else rng.uniform(-1.15,.22,n)
    return x
def run(archive,out):
    start=time.monotonic();out.mkdir(parents=True,exist_ok=False)
    prev=load(archive);oldrows={x["fixture"]:x for x in prev["results"]}
    pool=old.library();rng=np.random.default_rng(226)
    tr=sample(rng,6000,False);va=sample(rng,12000,False);te=sample(rng,40000,True);seen=sample(rng,12000,False)
    results=[];im=Image.new("RGB",(920,900),"#17232f");d=ImageDraw.Draw(im)
    d.text((10,10),"Spatial holdout x > 0.22 | reference / fixed R203 / score-first / topology-first",fill="white")
    for i,(name,truth) in enumerate(old.fixtures().items()):
        t=time.monotonic();prior=topology(truth)
        oldrow=oldrows[name];fixed=next(x["program"] for x in oldrow["metrics"] if x["pipeline"]==oldrow["chosen"])
        y=old.eval_program(truth,tr)<0;yv=old.eval_program(truth,va)<0;yt=old.eval_program(truth,te)<0;ys=old.eval_program(truth,seen)<0
        single=old.search(tr,y,pool,1,1);greedy=old.search(tr,y,pool,1,3);beam=old.search(tr,y,pool,8,3)
        variants={"single":single,"single-refine":old.refine(single,tr,y),"greedy":greedy,"beam":beam,"beam-refine":old.refine(beam,tr,y)}
        # Include a distinct two-node beam sequence; all proposals share the same observations.
        two=old.search(tr,y,pool,8,2);variants["two-refine"]=old.refine(two,tr,y)
        candidates=[]
        for tag,p in variants.items():
            topo=topology(p);candidates.append({"name":tag,"program":p,"validation":metrics(p,va,yv),"topology":topo,"topology_match":topo==prior,"nodes":len(p)})
        rank=lambda x:(x["validation"]["iou"],-x["nodes"],x["name"])
        score_first=max(candidates,key=rank);eligible=[x for x in candidates if x["topology_match"]]
        topo_first=max(eligible,key=rank) if eligible else None
        # Selection complete before any held-out score. Fixed prior saw entire volume
        # in R203 training and is a comparison-only upper reference, not a fair holdout.
        for row in candidates:
            row["heldout"]=metrics(row["program"],te,yt)
            row["seen_test"]=metrics(row["program"],seen,ys)
        comparison={"reference":truth,"fixed-r203":fixed,"score-first":score_first["program"]}
        if topo_first:comparison["topology-first"]=topo_first["program"]
        meshrows={}
        for j,tag in enumerate(("reference","fixed-r203","score-first","topology-first")):
            x=210+j*176;y0=40+i*212
            if tag not in comparison:
                d.text((x,y0+70),"NO ELIGIBLE",fill="white");continue
            p=comparison[tag];v,f,m=mesh(p,64);v32,f32,m32=mesh(p,32)
            export(out/f"{name}-{tag}-64.obj",v,f);export(out/f"{name}-{tag}-32.obj",v32,f32)
            meshrows[tag]={"grid32":m32,"grid64":m,"heldout":metrics(p,te,yt),"topology":topology(p)}
            im.paste(render(v,f,(.56,.34)),(x,y0))
            d.text((x+4,y0+172),tag+"\nIoU "+format(meshrows[tag]["heldout"]["iou"],".4f"),fill="white")
        d.text((8,65+i*212),name+"\nheld-out slab\nnot observed",fill="white")
        # Preserve all candidates and prior/selected programs for exact reconstruction.
        row={"fixture":name,"topology_prior":prior,"candidates":candidates,"selected_score_first":score_first["name"],"selected_topology_first":topo_first["name"] if topo_first else None,"programs":comparison,"meshes":meshrows,"elapsed_s":time.monotonic()-t}
        results.append(row)
        (out/f"{name}-receipt.json").write_text(json.dumps(row,indent=2))
    im.save(out/"spatial-comparison.png")
    receipt={"schema":"oneirifact.r226.spatial-ablation/v1","baseline_sha256":PIN,"split":{"train":6000,"validation":12000,"seen_test":12000,"heldout":40000,"heldout_x_gt":.22,"seed":226},"topology_prior":"Explicit complete-reference cubical counts at 32 and 64; not inferred from incomplete data","fixed_baseline":"R203 fit saw full region; comparison only, not a fair new holdout","render":"Actual marching-cubes triangles, shared orthographic view/scale, approximate painter occlusion","scope":"Original synthetic known grammar, no native engine, no clinical geometry or real scan","elapsed_s":time.monotonic()-start,"peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,"results":results}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2))
    print("R226_RESULT",json.dumps({"elapsed_s":receipt["elapsed_s"],"peak_rss_kib":receipt["peak_rss_kib"],"results":[{"fixture":r["fixture"],"score":r["selected_score_first"],"topo":r["selected_topology_first"],"metrics":{k:{"iou":round(v["heldout"]["iou"],5),"topo":v["topology"]==r["topology_prior"],"mesh64":v["grid64"]} for k,v in r["meshes"].items()}} for r in results]}))
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
