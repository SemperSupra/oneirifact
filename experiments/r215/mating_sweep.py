"""Sample the insertion path of actual LDraw references; not continuous collision proof."""
import hashlib,json,sys,zipfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"r214"))
from mating_sections import mesh,section,obj

def run(inp,out):
    out.mkdir(parents=True)
    raw=inp.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=="3c69e2c331af0b4035f511f0cbb3ce69d41482d0477b9c3cc8f3e2d754eab60d"
    with zipfile.ZipFile(inp) as z:
        base,bf=mesh(z,"3001");upper,uf=mesh(z,"3003")
        for id in ("3001","3003"):
            for name in z.namelist():
                if name.startswith(id+"/source/") or name==id+"/ATTRIBUTION.json":
                    p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
    dx=.1;dz=.2
    x=np.arange(-26+.037,26,dx);y=np.arange(-10+.023,10,dx)
    # Shared offset avoids the mesh vertex planes on the 0.2 mm lattice.
    ticks=list(range(-50,11))
    B={k:section(base,bf,k*dz+.073,x,y) for k in ticks}
    U={k:section(upper,uf,k*dz+.073,x,y) for k in ticks}
    empty=np.zeros((len(y),len(x)),bool);allvalid=np.ones(len(y),bool)
    results=[]
    for offset in (0,4,8):
        cells=int(round(offset/dx));rows=[]
        for k in range(68,37,-1):
            volume=0.;maximum=0.;unknown=0;sections=0
            for q,(a,av) in B.items():
                c,cv=U.get(q-k,(empty,allvalid))
                shifted=np.zeros_like(c)
                if cells:shifted[:,cells:]=c[:,:-cells]
                else:shifted=c
                valid=av&cv;overlap=a&shifted&valid[:,None]
                area=float(overlap.sum()*dx*dx)
                volume+=area*dz;maximum=max(maximum,area);unknown+=int((~valid).sum());sections+=1
            rows.append({"translation_z_mm":round(k*dz,3),"sampled_overlap_volume_mm3":volume,"maximum_section_overlap_mm2":maximum,"ambiguous_rows":unknown,"sections":sections})
        results.append({"offset_x_mm":offset,"path":rows})
        obj(out/("nominal-offset-"+str(offset)+".obj"),[("base_3001",base,bf),("upper_3003",upper+np.array([offset,0,9.6]),uf)])
    at=lambda i,z:next(r for r in results[i]["path"] if r["translation_z_mm"]==z)
    assert at(0,9.6)["sampled_overlap_volume_mm3"]<.01
    assert at(1,9.6)["sampled_overlap_volume_mm3"]>10
    assert at(0,7.6)["sampled_overlap_volume_mm3"]>10
    assert all(r["ambiguous_rows"]==0 for s in results for r in s["path"])
    receipt={"scope":"Discrete sampled reference mesh overlap across insertion poses; no certified solid topology, continuous collision, physical fit or native Foundry acceptance","source_sha256":hashlib.sha256(raw).hexdigest(),"grid_mm":[dx,dx,dz],"z_pose_step_mm":dz,"section_offset_mm":.073,"results":results}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2))
    im=Image.new("RGB",(1140,720),"#18212c");d=ImageDraw.Draw(im)
    title=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",25);small=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",17)
    d.text((25,20),"LDraw insertion-path diagnostic | actual 3001 + 3003 meshes",font=title,fill="white")
    d.text((25,60),"Sampled overlap volume, 0.1 × 0.1 × 0.2 mm grid; 31 insertion poses per offset",font=small,fill="#b9c8d8")
    left,top,right,bottom=90,145,1090,600
    ymax=max(r["sampled_overlap_volume_mm3"] for s in results for r in s["path"])*1.08
    for i in range(6):
        yy=bottom-(bottom-top)*i/5;d.line((left,yy,right,yy),fill="#405064");d.text((15,yy-10),f"{ymax*i/5:.0f}",font=small,fill="white")
    def px(z):return left+(13.6-z)/6*(right-left)
    def py(v):return bottom-v/ymax*(bottom-top)
    for i,z in enumerate([13.6,12.6,11.6,10.6,9.6,8.6,7.6]):
        xx=px(z);d.line((xx,top,xx,bottom),fill="#304052");d.text((xx-20,bottom+12),str(z),font=small,fill="white")
    d.line((px(9.6),top,px(9.6),bottom),fill="#e3d2a6",width=2)
    d.text((px(9.6)-74,110),"Nominal seating",font=small,fill="#e3d2a6")
    for i,(s,color) in enumerate(zip(results,("#76d7b1","#e9ae62","#79aee8"))):
        pts=[(px(r["translation_z_mm"]),py(r["sampled_overlap_volume_mm3"])) for r in s["path"]]
        d.line(pts,fill=color,width=4)
        xx=105+i*300;d.line((xx,665,xx+35,665),fill=color,width=4);d.text((xx+43,654),f"X offset {s['offset_x_mm']} mm",font=small,fill="white")
    d.text((430,632),"Upper translation Z (mm)",font=small,fill="white")
    im.save(out/"insertion-path.png")
    print("R215_SWEEP",json.dumps({"nominal":[at(i,9.6) for i in range(3)],"deep":at(0,7.6),"poses":sum(len(s["path"]) for s in results)}))
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
