"""Literature-constrained idealized gland morphology, not patient anatomy.
All dimensions are millimetres in editable local source; exports metres.
No inferred placement within full-body references and no native-engine claim.
"""
import sys,json,hashlib,math
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image,ImageDraw,ImageFont

SOURCES={
"parathyroid":"https://pmc.ncbi.nlm.nih.gov/articles/PMC11009140/",
"pineal":"https://pmc.ncbi.nlm.nih.gov/articles/PMC5661140/",
"vestibular":"https://www.ncbi.nlm.nih.gov/books/NBK557803/",
"vestibular_uncertainty":"https://academic.oup.com/smr/article/13/4/687/8158370",
"bulbourethral":"https://pubs.rsna.org/radiology/doi/10.1148/rg.220099",
"bulbourethral_shape":"https://www.imaios.cn/en/e-anatomy/anatomical-structures/bulbourethral-gland-1541222184"}
def sha(b):return hashlib.sha256(b).hexdigest()
def specs(sex):
    out=[]
    for side in ("left","right"):
        for level in ("superior","inferior"):
            out.append({"id":side+"_"+level+"_parathyroid","type":"ovoid","dimensions_mm":[3.,1.,5.],"lobulation":.035,"source":SOURCES["parathyroid"],"evidence":"Typical 5 x 3 x 1 mm ovoid gland; four glands chosen as idealized adult variant.","assumptions":"Local Z longitudinal, X transverse, Y thickness; subtle surface contour modeled, not measured.","attachment":"Posterior thyroid, "+side+" "+level+" region; world placement not resolved."})
    out.append({"id":"pineal_gland","type":"tapered_ovoid","dimensions_mm":[4.,4.,7.],"lobulation":.04,"source":SOURCES["pineal"],"evidence":"Pine-cone-like midline gland, typical 5–8 mm anteroposterior diameter.","assumptions":"7 mm long axis with 4 mm secondary axes chosen as a shape hypothesis; axes not fitted to imaging.","attachment":"Posterior third ventricle above tectal plate; exact landmark and axis mapping required."})
    family="greater_vestibular" if sex=="female" else "bulbourethral"
    size=[4.,4.,5.] if sex=="female" else [6.,6.,7.]
    length=20. if sex=="female" else 25.
    for side in ("left","right"):
        out.append({"id":side+"_"+family+"_gland","type":"ovoid","dimensions_mm":size,"lobulation":.08,"source":SOURCES["vestibular" if sex=="female" else "bulbourethral_shape"],"evidence":"Paired small ovoid or lobulated accessory gland; vestibular typical 5 mm, bulbourethral pea-sized.","assumptions":"Secondary axes and lobulation are idealized modeling choices. Normal anatomy varies; vestibular descriptions have limited direct morphometric evidence.","attachment":"Posterolateral vaginal introitus" if sex=="female" else "Posterolateral membranous urethra within deep perineal region"})
        out.append({"id":side+"_"+family+"_duct","type":"hollow_duct","length_mm":length,"outer_radius_mm":.55,"inner_radius_mm":.30,"curvature_rad":.45,"source":SOURCES["vestibular" if sex=="female" else "bulbourethral_shape"],"evidence":"Typical described duct length 20 mm (vestibular) or approximately 25 mm (bulbourethral).","assumptions":"Lumen radius, wall thickness and gently curved trajectory are unmeasured geometric hypotheses, not anatomical observations.","attachment":"Gland-to-vestibule opening" if sex=="female" else "Gland-to-spongy urethra opening"})
    return out
def gland(s):
    # Smooth lobulated radial surface with poles, no duplicate polar vertices.
    n=64;k=40;v=[[0,0,-1.]];f=[]
    for j in range(1,k):
        t=math.pi*j/k
        for i in range(n):
            p=2*math.pi*i/n
            a=1+s["lobulation"]*(.65*math.cos(5*p+1.5*t)+.35*math.cos(3*p-4*t))*math.sin(t)**2
            taper=(.85+.24*math.cos(t)) if s["type"]=="tapered_ovoid" else 1
            v.append([a*taper*math.sin(t)*math.cos(p),a*taper*math.sin(t)*math.sin(p),-math.cos(t)])
    v.append([0,0,1.]);top=len(v)-1
    for i in range(n):j=(i+1)%n;f.append([0,1+j,1+i]);f.append([top,1+(k-2)*n+i,1+(k-2)*n+j])
    for t in range(k-2):
        a=1+t*n;b=a+n
        for i in range(n):
            j=(i+1)%n;f.extend([[a+i,a+j,b+j],[a+i,b+j,b+i]])
    v=np.array(v);span=np.ptp(v,axis=0);v=(v-(v.max(0)+v.min(0))/2)*np.array(s["dimensions_mm"])/span
    m=trimesh.Trimesh(v*.001,np.array(f),process=False)
    if m.volume<0:m.invert()
    assert m.is_watertight and m.is_winding_consistent and m.volume>0
    return m
def duct(s):
    n=48;k=41;theta=s["curvature_rad"];L=s["length_mm"];R=L/theta
    v=[];f=[]
    for radius in (s["outer_radius_mm"],s["inner_radius_mm"]):
        for j in range(k):
            a=theta*j/(k-1);c=np.array([R*(1-math.cos(a)),0,R*math.sin(a)])
            u=np.array([math.cos(a),0,-math.sin(a)]);w=np.array([0,1,0])
            for i in range(n):
                t=2*math.pi*i/n;v.append(c+radius*(u*math.cos(t)+w*math.sin(t)))
    o=k*n
    for j in range(k-1):
        for i in range(n):
            x=j*n+i;y=j*n+(i+1)%n;a=x+n;b=y+n
            f.extend([[x,y,b],[x,b,a],[o+x,o+b,o+y],[o+x,o+a,o+b]])
    for i in range(n):
        j=(i+1)%n;a=(k-1)*n+i;b=(k-1)*n+j
        f.extend([[i,o+j,j],[i,o+i,o+j],[a,b,o+b],[a,o+b,o+a]])
    m=trimesh.Trimesh(np.array(v)*.001,np.array(f),process=False)
    if m.volume<0:m.invert()
    assert m.is_watertight and m.is_winding_consistent and m.volume>0
    # Euler zero (one lumen), not a solid cylinder falsely labeled hollow.
    assert m.euler_number==0
    return m
def plot(meshes,out,sex):
    w,h=1280,860;im=Image.new("RGB",(w,h),"#17232f");d=ImageDraw.Draw(im)
    title=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",23);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
    d.text((16,13),sex.title()+" | literature-constrained local anatomical models",font=title,fill="white")
    d.text((16,45),"True mesh render; magnified per panel; dimensions in mm. Body placement unqualified.",font=font,fill="#bfccd8")
    for j,(s,m) in enumerate(meshes):
        x=16+(j%3)*420;y=82+(j//3)*250
        d.rectangle((x,y,x+403,y+235),outline="#4f6070")
        d.text((x+8,y+8),s["id"].replace("_"," "),font=font,fill="white")
        # Project in oblique view to reveal the surface, not only silhouette.
        rot=trimesh.transformations.euler_matrix(.25,.48,-.25)[:3,:3];v=m.vertices@rot.T
        span=np.ptp(v,axis=0);sc=min(180/max(span[0],1e-7),160/max(span[2],1e-7))
        q=v-(v.max(0)+v.min(0))/2;xy=np.column_stack((x+201+q[:,0]*sc,y+120-q[:,2]*sc))
        normals=np.cross(v[m.faces[:,1]]-v[m.faces[:,0]],v[m.faces[:,2]]-v[m.faces[:,0]])
        normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-30)
        for i in np.argsort(v[m.faces,1].mean(1)):
            light=.45+.55*abs(normals[i]@np.array([.3,.9,.316]))
            base=(199,165,105) if s["type"]=="hollow_duct" else (191,116,133)
            d.polygon([tuple(x) for x in xy[m.faces[i]]],fill=tuple(int(z*light) for z in base))
        if s["type"]=="hollow_duct":label=f"Length {s['length_mm']:.0f}; lumen diameter {2*s['inner_radius_mm']:.1f} (assumed)"
        else:label=" × ".join(f"{x:g}" for x in s["dimensions_mm"])
        d.text((x+8,y+211),label,font=font,fill="#d5dde6")
    im.save(out/"model-review.png")
def main(sex,out):
    out.mkdir(parents=True,exist_ok=False);models=[];rows=[];scene=trimesh.Scene()
    for s in specs(sex):
        m=duct(s) if s["type"]=="hollow_duct" else gland(s);d=out/s["id"];d.mkdir()
        (d/"source.json").write_text(json.dumps({"schema":"oneirifact.research_anatomy_candidate/v0.1","sex":sex,"units":"mm","frame":"unregistered organ-local","parameters":s,"status":"RESEARCH_MODEL_NOT_NATIVE"},indent=2))
        m.export(d/"model.obj");m.export(d/"model.glb")
        if s["type"]!="hollow_duct":assert np.max(abs(m.extents*1000-np.array(s["dimensions_mm"])))<1e-8
        else:
            expected=math.pi*(s["outer_radius_mm"]**2-s["inner_radius_mm"]**2)*s["length_mm"]
            assert abs(m.volume*1e9/expected-1)<.02
        rows.append({"id":s["id"],"parameters":s,"triangles":len(m.faces),"dimensions_mm":(m.extents*1000).tolist(),"volume_mm3":float(m.volume*1e9),"watertight":bool(m.is_watertight),"consistent_winding":bool(m.is_winding_consistent),"euler":int(m.euler_number),"mesh_sha256":sha((d/"model.glb").read_bytes()),"status":"RESEARCH_CANDIDATE_PLACEMENT_AND_ANATOMICAL_REVIEW_HELD"})
        models.append((s,m))
        # An inspection arrangement, explicitly not anatomical placement.
        mat=np.eye(4);mat[0,3]=(len(models)-1)%3*.045;mat[2,3]=-((len(models)-1)//3)*.045
        m.visual=trimesh.visual.ColorVisuals(mesh=m,vertex_colors=[191,116,133,255] if s["type"]!="hollow_duct" else [199,165,105,255])
        scene.add_geometry(m,node_name=s["id"],geom_name=s["id"],transform=mat)
    (out/"inspection-arrangement.glb").write_bytes(scene.export(file_type="glb"))
    plot(models,out,sex)
    (out/"receipt.json").write_text(json.dumps({"sex":sex,"models":rows,"source_references":SOURCES,"scope":"Original research-constrained local morphological hypotheses. No patient model, donor equivalence, anatomy admission, native Oneirifact source or verified integration. Four parathyroids typical variant; shape and duct radii inferred as stated."},indent=2))
    print("R224_MODELS",json.dumps({"sex":sex,"models":len(rows),"watertight":sum(x["watertight"] for x in rows),"lumen_topology":sum(x["euler"]==0 for x in rows),"triangles":sum(x["triangles"] for x in rows)}))
if __name__=="__main__":main(sys.argv[1],Path(sys.argv[2]))
