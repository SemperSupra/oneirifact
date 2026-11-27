"""Independent numerical mesh bakeoff; original public-safe fixtures.
No private Foundry source or engine execution. Compare common discretization
methods against analytic geometry with explicit resource and topology gates.
"""
import json,math,sys,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy.ndimage import label
from skimage.measure import marching_cubes

FIXTURES={
 "disk":{"radius":3.5,"height":.04},
 "shell":{"radius":.016,"height":.0096,"inner_radius":.0144,"roof":.0016}
}
def field(q,d):
    r=np.linalg.norm(q[...,:2],axis=-1);z=q[...,2];R=d["radius"];h=d["height"]
    outer=np.maximum(r-R,np.abs(z)-h/2)
    if "inner_radius" not in d:return outer
    t=d["roof"];cavity=np.maximum(r-d["inner_radius"],np.maximum(z-(h/2-t),-h/2-.01-z))
    return np.maximum(outer,-cavity)
def analytic(d,n=96):
    R,h=d["radius"],d["height"];a=np.arange(n)*2*np.pi/n
    if "inner_radius" in d:
        r=d["inner_radius"];t=d["roof"]
        # Closed material boundary, ring order: outside bottom/top, inside roof/bottom.
        rings=[(R,-h/2),(R,h/2),(r,h/2-t),(r,-h/2)]
        v=np.array([[rr*np.cos(x),rr*np.sin(x),z] for rr,z in rings for x in a]+[[0,0,h/2],[0,0,h/2-t]])
        f=[]
        def join(i,j):
            for k in range(n):
                l=(k+1)%n;f.extend([(i*n+k,i*n+l,j*n+l),(i*n+k,j*n+l,j*n+k)])
        join(0,1);join(2,3);join(3,0)
        for k in range(n):
            l=(k+1)%n;f.extend([(n+k,n+l,4*n),(2*n+l,2*n+k,4*n+1)])
    else:
        v=np.array([[R*np.cos(x),R*np.sin(x),z] for z in (-h/2,h/2) for x in a]+[[0,0,-h/2],[0,0,h/2]])
        f=[]
        for k in range(n):
            l=(k+1)%n;f.extend([(k,l,n+l),(k,n+l,n+k),(l,k,2*n),(n+k,n+l,2*n+1)])
    return v,np.array(f),{"samples":0,"pitch_m":None}
def grid(d,method):
    R,h=d["radius"],d["height"];lo=np.array([-R,-R,-h/2]);hi=-lo
    base=max(2*R,h)/28
    if method=="uniform":step=np.full(3,base)
    else:
        # Preserve at least eight samples through the thinnest specified dimension.
        # Refuse instead of exceeding the independent sample budget.
        thin=min(h,d.get("roof",h),R-d.get("inner_radius",0))
        step=np.array([min(base,thin/3) if "inner_radius" in d else base]*2+[min(base,thin/8)])
    n=np.ceil((hi-lo)/step).astype(int)+4
    if np.prod(n)>2_000_000:return None,None,{"status":"HELD_BUDGET","samples":int(np.prod(n)),"pitch_m":step.tolist()}
    origin=lo-2*step
    axes=[origin[i]+(np.arange(n[i])+.5)*step[i] for i in range(3)]
    q=np.stack(np.meshgrid(*axes,indexing="ij"),-1);val=field(q,d);a=val<0
    rec={"samples":int(a.size),"pitch_m":step.tolist(),"occupied":int(a.sum()),"occupied_components":int(label(a)[1])}
    if not a.any():return None,None,rec
    if method=="uniform":
        vs=[];fs=[];idx={}
        for cell in np.argwhere(a):
            for axis in range(3):
                for side in (0,1):
                    nb=cell.copy();nb[axis]+=2*side-1
                    if np.all((nb>=0)&(nb<n)) and a[tuple(nb)]:continue
                    k,l=[i for i in range(3) if i!=axis];ids=[]
                    for u,w in [(0,0),(1,0),(1,1),(0,1)]:
                        p=cell.copy();p[axis]+=side;p[k]+=u;p[l]+=w;key=tuple(p)
                        if key not in idx:idx[key]=len(vs);vs.append(origin+p*step)
                        ids.append(idx[key])
                    if (axis==1)==bool(side):ids.reverse()
                    fs.extend([ids[:3],[ids[0],ids[2],ids[3]]])
        return np.array(vs),np.array(fs),rec
    # Scalar-field interpolation, not an exact BRep. Compare separately.
    v,f,_,_=marching_cubes(val.astype(np.float32),0,spacing=tuple(step),allow_degenerate=False)
    v+=origin+step/2
    return v,f[:,::-1],rec
def metrics(v,f,d):
    if v is None:return {"status":"EMPTY_OR_HELD"}
    t=v[f];vol=float(abs(np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6))
    truth=math.pi*d["radius"]**2*d["height"]-math.pi*d.get("inner_radius",0)**2*(d["height"]-d.get("roof",0))
    edges=np.sort(np.concatenate((f[:,[0,1]],f[:,[1,2]],f[:,[2,0]])),axis=1);_,counts=np.unique(edges,axis=0,return_counts=True)
    thickness=float(np.ptp(v[:,2]))
    return {"status":"MESH","triangles":len(f),"thickness_m":thickness,"thickness_error_pct":abs(thickness/d["height"]-1)*100,"volume_error_pct":abs(vol/truth-1)*100,"open_edges":int((counts==1).sum()),"nonmanifold_edges":int((counts>2).sum())}
def writeobj(path,v,f):
    path.write_text("".join("v %.10g %.10g %.10g\n"%tuple(p) for p in v)+"".join("f %d %d %d\n"%tuple(t+1) for t in f))
def visual(out,d,meshes,rows,family):
    im=Image.new("RGB",(1260,760),"#18212c");draw=ImageDraw.Draw(im)
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",25);small=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",17)
    draw.text((24,18),"R213 | "+family+" — actual numerical mesh outputs",font=font,fill="white")
    draw.text((24,55),"Shared coordinate scale per row; section profile uses 10x vertical magnification",font=small,fill="#b3c7d7")
    colors=[(190,115,86),(114,182,211),(110,203,161)]
    for i,((v,f),m,color) in enumerate(zip(meshes,rows,colors)):
        x=20+i*415;draw.rectangle((x,100,x+400,730),outline="#526477")
        draw.text((x+14,116),m["method"],font=font,fill="white")
        if v is None:draw.text((x+24,260),"NO MESH",font=font,fill="#e6ab92");continue
        p=v.copy();p[:,2]*=10;scale=340/(2*d["radius"])
        a,b=np.radians([24,32]);R=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])@np.array([[1,0,0],[0,np.cos(b),-np.sin(b)],[0,np.sin(b),np.cos(b)]])
        # Display actual top projection, then a true scaled side silhouette.
        q=v@R;t=q[f];xy=np.stack((x+200+q[:,0]*scale,290-q[:,1]*scale),axis=1)
        normals=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-15);s=.38+.62*np.abs(normals@np.array([.2,.4,.894]))
        for j in np.argsort(t[:,:,2].mean(1)):draw.polygon([tuple(p) for p in xy[f[j]]],fill=tuple(int(c*s[j]) for c in color))
        # Side bounds, same horizontal scale and 10x vertical (cap magnification for shell).
        mx=min(10, .6*d["radius"]/max(d["height"],1e-12));z=v[:,2]*scale*mx
        draw.rectangle((x+200+v[:,0].min()*scale,520-z.max(),x+200+v[:,0].max()*scale,520-z.min()),outline=color,width=3)
        draw.text((x+14,560),f"Side extent (vertical ×{mx:.2g})",font=small,fill="white")
        draw.text((x+14,595),f"{m['triangles']:,} triangles",font=small,fill="white")
        draw.text((x+14,625),f"Thickness error {m['thickness_error_pct']:.3f}%",font=small,fill="white")
        draw.text((x+14,655),f"Volume error {m['volume_error_pct']:.3f}%",font=small,fill="white")
        draw.text((x+14,685),f"Open/nonmanifold {m['open_edges']}/{m['nonmanifold_edges']}",font=small,fill="white")
    im.save(out/"comparison.png")
def main(family,out):
    out.mkdir(parents=True,exist_ok=False);d=FIXTURES[family];rows=[];meshes=[]
    for method in ("uniform","anisotropic","analytic"):
        start=time.monotonic();v,f,rec=analytic(d) if method=="analytic" else grid(d,method)
        m={"method":method,**rec,**metrics(v,f,d),"seconds":time.monotonic()-start};rows.append(m);meshes.append((v,f))
        if v is not None:writeobj(out/(method+".obj"),v,f)
    # Analytic polygonal reference must retain exact axial thickness, closed edges,
    # and converge in volume; no claim of exact curved surfaces.
    a=rows[-1];assert a["status"]=="MESH" and a["thickness_error_pct"]<1e-6 and a["volume_error_pct"]<.1 and a["open_edges"]==0 and a["nonmanifold_edges"]==0
    if family=="disk":assert rows[0]["status"]=="EMPTY_OR_HELD" and rows[1]["status"]=="MESH"
    visual(out,d,meshes,rows,family)
    (out/"receipt.json").write_text(json.dumps({"fixture":family,"dimensions_m":d,"scope":"independent reference methods, not native Oneirifact; analytic uses 96-segment polygon; surface topology counts only; no manufacturing claim","results":rows},indent=2))
    print(json.dumps(rows))
if __name__=="__main__":main(sys.argv[1],Path(sys.argv[2]))
