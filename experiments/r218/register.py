"""R218 actual atlas-to-MakeHuman fit comparison. Research, not medical anatomy.
Compare height-only baseline and a shared, slice-envelope warp. No independent
organ repositioning or clipping. Preserve topology and source identities.
"""
import sys,hashlib,json,zipfile,io
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
import trimesh
from PIL import Image,ImageDraw,ImageFont
PINS={
"male":("fd63861d5cd8bab550c282f5490e36bb57f0ca5a45999f88f120b1bcc5fa615f","980678a8639ef26849a9c0ace5dfece3807dd535ff68664058092b52e863c01a"),
"female":("bfc5e4d5c64d48f4c764ed502aec9af5841c3962a1e6e0a961e752eaf78644e4","8125975af5baea4c9b98f2eebd95221448189244325dfbdd0909c64caa83106c")}
def sha(b):return hashlib.sha256(b).hexdigest()
def checked(path,h):
    assert sha(path.read_bytes())==h,"source digest"
    return zipfile.ZipFile(path)
def load(raw,fmt):
    m=trimesh.load(io.BytesIO(raw),file_type=fmt,force="scene",process=False)
    return m.to_geometry()
def obj(path,m):
    path.write_text("# Research derivative in metric Z-up; see attribution\n"+"".join("v %.9f %.9f %.9f\n"%tuple(v) for v in m.vertices)+"".join("f %d %d %d\n"%tuple(f+1) for f in m.faces))
R=np.array([[1.,0,0,0],[0,0,-1.,0],[0,1.,0,0],[0,0,0,1.]])
def sample(m,n,seed):
    t=m.vertices[m.faces];a=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)
    rng=np.random.default_rng(seed);t=t[rng.choice(len(t),n,p=a/a.sum())];u=rng.random((n,2));u[u.sum(1)>1]=1-u[u.sum(1)>1]
    return t[:,0]+u[:,0,None]*(t[:,1]-t[:,0])+u[:,1,None]*(t[:,2]-t[:,0])
def envelope(m,levels):
    # Actual triangle/plane intersections. Fit only the central trunk/head,
    # not the arm pose. Quantiles of segment endpoints are a heuristic.
    lo,hi=m.bounds;h=hi[2]-lo[2];rows=[]
    for f in levels:
        seg=trimesh.intersections.mesh_plane(m,[0,0,1],[0,0,lo[2]+f*h])
        q=seg.reshape(-1,3);q=q[abs(q[:,0])<.14*h]
        assert len(q)>12,"section insufficient"
        a,b=np.quantile(q[:,:2],[.02,.98],axis=0)
        rows.append(np.r_[.5*(a+b),.5*(b-a)])
    return np.array(rows)
def warp_factory(src,dst,knots,ss,tt):
    slo,shi=src.bounds;tlo,thi=dst.bounds;sh=shi[2]-slo[2];th=thi[2]-tlo[2]
    ratio=np.clip(tt[:,2:]/ss[:,2:],.65,1.4)
    # Interpolate center and positive widths on the organ-bearing region.
    a=PchipInterpolator(knots,ss[:,:2],axis=0);b=PchipInterpolator(knots,tt[:,:2],axis=0);c=PchipInterpolator(knots,ratio,axis=0)
    def warp(v):
        f=(v[:,2]-slo[2])/sh;g=np.clip(f,knots[0],knots[-1])
        xy=b(g)+(v[:,:2]-a(g))*c(g)
        return np.column_stack((xy,tlo[2]+f*th))
    def affine(v):
        q=(v-(slo+shi)/2)*th/sh+(tlo+thi)/2
        return q
    return affine,warp,ratio
def contains(target,p):
    # Two independent non-axis-aligned rays, using actual target triangles.
    # Trimesh ray engine parity is a diagnostic; disagreements are ambiguous.
    result=[]
    for d in (np.array([1.,.173,.271]),np.array([-.193,1.,.311])):
        d=d/np.linalg.norm(d);orig=p+1e-8*d
        hits,ray,tri=target.ray.intersects_location(orig,np.tile(d,(len(p),1)),multiple_hits=True)
        count=np.bincount(ray,minlength=len(p))
        result.append(count%2==1)
    a,b=result
    return {"samples":len(p),"inside_agree":int((a&b).sum()),"outside_agree":int((~a&~b).sum()),"ambiguous":int((a!=b).sum())}
def projection(out,target,orgs,sex):
    im=Image.new("RGB",(1200,840),"#17212b");d=ImageDraw.Draw(im);title=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",24);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",17)
    d.text((20,14),sex.title()+" | actual organ registration into MakeHuman body",font=title,fill="white")
    d.text((20,48),"Shared deformation only; clinical accuracy and organ collisions not established",font=font,fill="#b9cad8")
    lo,hi=target.bounds;scale=680/(hi[2]-lo[2]);colors=["#d87879","#7eb4df","#c7a06d","#b49bd6","#73c2b1","#e5bf84","#c68eaa"]
    for i,(label,method) in enumerate(orgs.items()):
        for axis in (0,1):
            x0=i*600+axis*300;cx=x0+150;cy=780;c=(lo[axis]+hi[axis])/2
            def project(v):return np.column_stack((cx+(v[:,axis]-c)*scale,cy-(v[:,2]-lo[2])*scale))
            q=project(target.vertices)
            for f in target.faces:d.polygon([tuple(q[k]) for k in f],fill="#344958")
            for j,(name,m) in enumerate(method.items()):
                p=project(sample(m,1400,218+j))
                for x,y in p:d.ellipse((x-1,y-1,x+1,y+1),fill=colors[j%len(colors)])
            d.text((x0+10,84),label+" / "+("front" if axis==0 else "side"),font=font,fill="white")
    im.save(out/"registration.png")
def main(body,atlas,out,sex):
    out.mkdir(parents=True,exist_ok=False)
    with checked(body,PINS[sex][0]) as bz,checked(atlas,PINS[sex][1]) as az:
        target=load(bz.read("body-reference.obj"),"obj")
        source=load(az.read("skin-reference.glb"),"glb");source.apply_transform(R)
        source.merge_vertices();target.merge_vertices()
        assert target.is_watertight,"target must be closed for parity screen"
        br=json.loads(bz.read("receipt.json"));ar=json.loads(az.read("receipt.json"))
        assert br["sex_variant"]==sex and ar["sex"]==sex
        knots=np.array([.47,.51,.55,.59,.63,.67,.71,.75,.79,.83,.87,.91,.95,.98])
        ss=envelope(source,knots);tt=envelope(target,knots);affine,warp,ratios=warp_factory(source,target,knots,ss,tt)
        # Distinct interleaved cross sections; these are geometric proxies,
        # not independently annotated anatomical landmarks.
        test=(knots[:-1]+knots[1:])/2;sh=source.extents[2];th=target.extents[2];sr=envelope(source,test);tr=envelope(target,test)
        scores={}
        for label,fn in (("height_only",affine),("section_warp",warp)):
            pts=[];goal=[]
            for f,a,b in zip(test,sr,tr):
                for sign in ((1,0),(-1,0),(0,1),(0,-1)):
                    pts.append([*(a[:2]+a[2:]*sign),source.bounds[0,2]+f*sh]);goal.append([*(b[:2]+b[2:]*sign),target.bounds[0,2]+f*th])
            e=fn(np.array(pts))-np.array(goal)
            scores[label]={"interleaved_envelope_rmse_mm":float(np.sqrt(np.mean(np.sum(e*e,axis=1)))*1000)}
        groups={};rows=[]
        for label,fn in (("height_only",affine),("section_warp",warp)):
            folder=out/label;folder.mkdir();groups[label]={}
            scene=trimesh.Scene()
            for row in ar["organs"]:
                name=row["organ"];m=load(az.read("organs/"+name+".obj"),"obj")
                before=m.vertices.copy();faces=m.faces.copy();m.vertices=fn(before)
                assert np.array_equal(faces,m.faces) and np.isfinite(m.vertices).all()
                p=sample(m,384,218)
                c=contains(target,p)
                e=np.linalg.norm(m.vertices-before,axis=1)
                area0=trimesh.triangles.area(before[faces]).sum();area1=m.area
                rows.append({"method":label,"organ":name,"triangles":len(faces),"containment":c,"surface_area_ratio":float(area1/area0),"source_topology_preserved":True,"max_displacement_m":float(e.max())})
                m.visual=trimesh.visual.ColorVisuals(mesh=m,vertex_colors=np.tile([180,108,110,255],(len(m.vertices),1)))
                scene.add_geometry(m.copy(),node_name=name,geom_name=name);groups[label][name]=m
            ghost=target.copy();ghost.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name="skin_context",baseColorFactor=[160,180,200,45],alphaMode="BLEND",doubleSided=True,metallicFactor=0.0,roughnessFactor=1.0))
            scene.add_geometry(ghost,node_name="skin_context",geom_name="skin_context");scene.apply_transform(np.linalg.inv(R))
            (folder/"body-with-organs.glb").write_bytes(scene.export(file_type="glb"))
        # Never admit an organ from a partial sample, even when all samples inside.
        for label in groups:
            a=[r["containment"] for r in rows if r["method"]==label]
            scores[label]["sample_inside_fraction"]=sum(x["inside_agree"] for x in a)/sum(x["samples"] for x in a)
            scores[label]["outside_samples"]=sum(x["outside_agree"] for x in a)
            scores[label]["ambiguous_samples"]=sum(x["ambiguous"] for x in a)
        projection(out,target,groups,sex)
        (out/"ATTRIBUTION.txt").write_bytes(az.read("ATTRIBUTION.txt")+b"\nR218: registered derivatives to adult MakeHuman CC0 mesh (source: https://github.com/makehumancommunity/makehuman); normalized height and central cross-section warps. Original source archives retained separately.\n")
        (out/"HRA-LICENSE.txt").write_bytes(az.read("HRA-LICENSE.txt"))
        (out/"MakeHuman-LICENSE.ASSETS.md").write_bytes(bz.read("source/LICENSE.ASSETS.md"))
        (out/"registration.json").write_text(json.dumps({"sex":sex,"source_archive_sha256":PINS[sex],"knots_normalized_height":knots.tolist(),"source_envelopes":ss.tolist(),"target_envelopes":tt.tolist(),"clamped_xy_ratios":ratios.tolist(),"scores":scores,"organs":rows,"status":"GEOMETRIC_REGISTRATION_CANDIDATE_HELD","scope":"Two ray parity sample diagnostic, nonclinical. No anatomical landmark validation, complete containment, self/inter-organ collision, biological deformation or native engine proof."},indent=2))
        print("R218_REGISTRATION",json.dumps({"sex":sex,"scores":scores,"organs":len(ar["organs"])}))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4])
