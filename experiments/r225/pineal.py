"""Recover actual existing pineal source meshes; no new anatomical geometry."""
import sys,hashlib,json,zipfile,io
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont
PINS={"male":"18c2089c2878a6729515754795779fd34b59e887809646d45fa84d829e6906d9","female":"513163f8e9cfee7ba3867a5b9f0c5b17f893114061d74ec3d4f43ec12b1e1542","research-male":"cfe28cd8f51f32b32dddf090f64fba883e5406a54f507bf7e95dad66d6bb9d6f","research-female":"1763e99163aa20c3b5928d391314193f29f1771ed00dd5efce4eda3a9599a428"}
def checked(p,k):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    assert h.hexdigest()==PINS[k]
    return zipfile.ZipFile(p)
def load(b):return trimesh.load(io.BytesIO(b),file_type="glb",force="scene",process=False)
def drawmesh(im,rect,meshes,center,scale,axis):
    d=ImageDraw.Draw(im);x,y,w,h=rect;axes=[i for i in range(3) if i!=axis]
    vs=[];fs=[];colors=[];offset=0
    for m,c in meshes:
        v=m.vertices-center;vs.append(v);fs.append(m.faces+offset);offset+=len(v);colors.extend([c]*len(m.faces))
    v=np.concatenate(vs);f=np.concatenate(fs);xy=np.column_stack((x+w/2+v[:,axes[0]]*scale,y+h/2-v[:,axes[1]]*scale))
    t=v[f];n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);n=n/np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-30)
    for j in np.argsort(t[:,:,axis].mean(1)):
        shade=.45+.55*abs(n[j,axis]);d.polygon([tuple(p) for p in xy[f[j]]],fill=tuple(int(c*shade) for c in colors[j]))
def main(inp,out):
    out.mkdir(parents=True,exist_ok=False);rows=[];display=[]
    for sex in ("male","female"):
        with checked(inp/(sex+".zip"),sex) as z, checked(inp/("research-"+sex+".zip"),"research-"+sex) as rz:
            inv=json.loads(z.read("inventory.json"))
            if sex=="male":
                selected=[r for r in inv if r["id"]=="FJ1795" and ["FMA62033","pineal body"] in r["concepts"]]
                assert len(selected)==1
            else:
                selected=[r for r in inv if r["source_node"] in {"Allen_pineal_body_L","Allen_pineal_body_R"}]
                assert len(selected)==2
            sc=load(z.read("baseline.glb"));dest=trimesh.Scene();models=[]
            for r in selected:
                mat,g=sc.graph[r["id"]];m=sc.geometry[g].copy();m.apply_transform(mat)
                assert np.isfinite(m.vertices).all()
                dest.add_geometry(m,node_name=r["id"],geom_name=r["id"])
                models.append(m)
            raw=dest.export(file_type="glb");(out/(sex+"-pineal-reference.glb")).write_bytes(raw)
            check=load(raw);err=0.
            for r,m in zip(selected,models):
                mat,g=check.graph[r["id"]];q=check.geometry[g];v=trimesh.transform_points(q.vertices,mat)
                assert m.faces.shape==q.faces.shape
                err=max(err,float(np.max(np.linalg.norm(m.vertices[m.faces]-v[q.faces],axis=2))))
            assert err<2e-7
            ref=np.concatenate([m.vertices for m in models]);bounds=np.array([ref.min(0),ref.max(0)])
            candidate=load(rz.read("pineal_gland/model.glb")).to_geometry()
            # Comparison-only coordinate recenter, no scale or claimed
            # anatomical correspondence of axes between local hypothesis and atlas.
            display.append((sex,models,bounds,candidate))
            rows.append({"sex":sex,"source_nodes":[r["id"] for r in selected],"triangles":sum(len(m.faces) for m in models),"bounds_m":bounds.tolist(),"dimensions_mm":((bounds[1]-bounds[0])*1000).tolist(),"transport_max_error_m":err,"candidate_dimensions_mm":(candidate.extents*1000).tolist(),"sha256":hashlib.sha256(raw).hexdigest(),"status":"EXACT_BASELINE_SUBSET_REFERENCE_ONLY","scope":"Preserve named subregions; no union, shape fitting, independent anatomical admission or native generation. Allen brain reference does not establish sex-specific donor morphology."})
            (out/(sex+"-attribution.txt")).write_bytes(z.read("ATTRIBUTION.txt"))
    im=Image.new("RGB",(1200,690),"#17232f");d=ImageDraw.Draw(im);title=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",23);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
    d.text((18,12),"Pineal reference recovery | actual meshes, no geometric substitution",font=title,fill="white")
    d.text((18,46),"Tan/blue: donor components. Green: prior research model. Same scale within each sex; axes not registered.",font=font,fill="#becbd7")
    for i,(sex,ms,bb,c) in enumerate(display):
        y=80+i*298;d.text((15,y+8),sex.title()+" reference",font=title,fill="white");d.text((810,y+8),"Research hypothesis",font=title,fill="white")
        center=bb.mean(0);cc=c.bounds.mean(0);scale=190/max(float(np.ptp(bb,axis=0).max()),float(c.extents.max()))
        for j,axis in enumerate((2,0)):
            drawmesh(im,(j*390+12,y+32,375,235),[(m,[(212,169,113),(125,174,212)][k%2]) for k,m in enumerate(ms)],center,scale,axis)
        drawmesh(im,(792,y+32,390,235),[(c,(98,190,153))],cc,scale,1)
        d.text((15,y+269),"Source bounds (mm): "+ " × ".join(f"{x:.2f}" for x in (bb[1]-bb[0])*1000),font=font,fill="#d0dae3")
    im.save(out/"pineal-comparison.png")
    (out/"receipt.json").write_text(json.dumps({"results":rows,"scope":"Exact donor mesh subset extraction. Existing research models kept for comparison, not added to baseline."},indent=2))
    print("R225_PINEAL",json.dumps(rows))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
