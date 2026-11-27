"""Reference-only LDraw section overlap diagnostic, not a fit/collision certificate."""
import hashlib,json,zipfile,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

def mesh(z,id):
    v=[];f=[]
    for line in z.read(id+"/part.obj").decode().splitlines():
        t=line.split()
        if t and t[0]=="v":v.append([float(x)*1000 for x in t[1:]])
        if t and t[0]=="f":f.append([int(x)-1 for x in t[1:]])
    return np.array(v),np.array(f)
def section(v,f,z,x,y):
    # Cross section segments from individual triangles, independent of BFC winding.
    # Half-open row crossing, deduplicate equal crossings, reject odd crossings.
    seg=[]
    for t in v[f]:
        p=[]
        for a,b in zip(t,np.roll(t,-1,axis=0)):
            if (a[2]<z<b[2]) or (b[2]<z<a[2]):
                p.append((a+(b-a)*(z-a[2])/(b[2]-a[2]))[:2])
        if len(p)==2:seg.append(p)
    occ=np.zeros((len(y),len(x)),bool);valid=np.ones(len(y),bool)
    for j,yy in enumerate(y):
        hits=[]
        for a,b in seg:
            if min(a[1],b[1])<=yy<max(a[1],b[1]):
                hits.append(a[0]+(b[0]-a[0])*(yy-a[1])/(b[1]-a[1]))
        hits=sorted(set(round(t,7) for t in hits))
        if len(hits)%2:valid[j]=False;continue
        for lo,hi in zip(hits[::2],hits[1::2]):occ[j]|=(x>lo)&(x<hi)
    return occ,valid
def obj(path,parts):
    s=[];offset=1
    for name,v,f in parts:
        s.append("o "+name)
        s.extend("v %.9f %.9f %.9f"%tuple(p/1000) for p in v)
        s.extend("f %d %d %d"%tuple(t+offset) for t in f);offset+=len(v)
    path.write_text("\n".join(s)+"\n")
def run(inp,out):
    out.mkdir(parents=True)
    raw=inp.read_bytes();assert hashlib.sha256(raw).hexdigest()=="3c69e2c331af0b4035f511f0cbb3ce69d41482d0477b9c3cc8f3e2d754eab60d"
    with zipfile.ZipFile(inp) as z:
        base,bf=mesh(z,"3001");upper,uf=mesh(z,"3003")
        for id in ("3001","3003"):
            for path in z.namelist():
                if path.startswith(id+"/source/") or path==id+"/ATTRIBUTION.json":
                    p=out/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(path))
    x=np.arange(-18+.037,18,.1);y=np.arange(-10+.023,10,.1)
    h=-upper[:,2].min();rows=[];images=[]
    for name,shift in (("nominal",(0,0,h)),("half_pitch",(4,0,h)),("deep",(0,0,h-2))):
        u=upper+shift;obj(out/(name+".obj"),[("base_3001",base,bf),("upper_3003",u,uf)])
        results=[]
        for zz in (-.713,.313,.813,1.313,2.313):
            a,av=section(base,bf,zz,x,y);c,cv=section(u,uf,zz,x,y);valid=av&cv;overlap=a&c&valid[:,None]
            results.append({"z_mm":zz,"valid_rows":int(valid.sum()),"rows":len(y),"overlap_area_mm2":float(overlap.sum()*.01),"sampled_base_area_mm2":float((a&valid[:,None]).sum()*.01),"sampled_upper_area_mm2":float((c&valid[:,None]).sum()*.01)})
            if zz==.813:
                rgb=np.full((len(y),len(x),3),[23,33,44],np.uint8);rgb[a]=[92,149,209];rgb[c]=[224,177,88];rgb[overlap]=[229,86,80];rgb[~valid]=[95,95,95];images.append((name,rgb,results[-1]))
        rows.append({"name":name,"upper_translation_mm":list(shift),"sections":results})
    im=Image.new("RGB",(1140,400),"#18212c");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",21);small=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
    d.text((16,12),"Actual LDraw 3001 + 3003 | horizontal section at z=0.813 mm",font=font,fill="white")
    d.text((16,44),"Blue: base • gold: upper • red: sampled overlap • gray: ambiguous row",font=small,fill="#b9c8d8")
    for i,(name,rgb,m) in enumerate(images):
        x0=14+375*i;d.text((x0,82),name,font=font,fill="white");im.paste(Image.fromarray(rgb[::-1]),(x0,120));d.text((x0,333),f"Sampled overlap {m['overlap_area_mm2']:.2f} mm²",font=small,fill="white");d.text((x0,355),f"Valid rows {m['valid_rows']}/{m['rows']}",font=small,fill="white")
    im.save(out/"sections.png")
    receipt={"scope":"LDraw nominal reference mesh parity sections; duplicate crossings collapsed, odd rows excluded; no watertightness, tolerance, continuous collision or clutch-fit guarantee","source_sha256":hashlib.sha256(raw).hexdigest(),"grid_mm":.1,"results":rows}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
if __name__=="__main__":run(Path(sys.argv[1]),Path(sys.argv[2]))
