"""Known-truth orthographic depth reconstruction experiment, not real LiDAR.
Metric coordinates, analytic ray intersections, held-out camera, editable
primitive candidates. No imported images, user data, private code or CPE.
"""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import zlib

N=81
STEP=.05
AXES=((1,0,0),(0,1,0),(0,0,1))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def mul(a,k):return tuple(x*k for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def norm(a):return math.sqrt(dot(a,a))
def unit(a):return mul(a,1/norm(a))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def require(ok,msg):
    if not ok:raise RuntimeError(msg)

TRUTH=(
    {"kind":"box","center":[.2,-.15,.1],"size":[1.4,.9,1.2]},
    {"kind":"cylinder","center":[-.15,.1,.15],"radius":.65,"height":1.3},
)
def intersect(model,origin,direction):
    o=sub(origin,model["center"]);d=direction
    if model["kind"]=="box":
        lo,hi=-math.inf,math.inf
        for x,v,w in zip(o,d,model["size"]):
            h=w/2
            if abs(v)<1e-12:
                if abs(x)>h+1e-9:return None
            else:
                a,b=sorted(((-h-x)/v,(h-x)/v))
                lo=max(lo,a);hi=min(hi,b)
        return lo if 0<=lo<=hi+1e-9 else None
    r,h=model["radius"],model["height"]/2
    hits=[]
    a=d[0]**2+d[1]**2;b=2*(o[0]*d[0]+o[1]*d[1]);c=o[0]**2+o[1]**2-r*r
    if a>1e-12 and b*b-4*a*c>=-1e-9:
        for t in ((-b-math.sqrt(max(0,b*b-4*a*c)))/(2*a),(-b+math.sqrt(max(0,b*b-4*a*c)))/(2*a)):
            if t>=0 and abs(o[2]+t*d[2])<=h+1e-9:hits.append(t)
    if abs(d[2])>1e-12:
        for z in (-h,h):
            t=(z-o[2])/d[2]
            if t>=0 and (o[0]+t*d[0])**2+(o[1]+t*d[1])**2<=r*r+1e-9:hits.append(t)
    return min(hits) if hits else None

def capture(model,normal):
    n=unit(normal);up=(0,0,1) if abs(n[2])<.9 else (0,1,0)
    u=unit(cross(up,n));v=cross(n,u);direction=mul(n,-1)
    depths=[];points=[]
    for y in range(N):
        for x in range(N):
            origin=add(mul(n,4),add(mul(u,(x-(N-1)/2)*STEP),mul(v,(y-(N-1)/2)*STEP)))
            t=intersect(model,origin,direction);depths.append(t)
            if t is not None:points.append(add(origin,mul(direction,t)))
    return {"direction":list(n),"u":list(u),"v":list(v),"depths":depths,"points":points}

def surface_error(model,p):
    q=sub(p,model["center"])
    if model["kind"]=="box":
        a=[abs(x)-w/2 for x,w in zip(q,model["size"])]
        return abs(min(max(a),0)+norm(tuple(max(x,0) for x in a)))
    a=math.hypot(q[0],q[1])-model["radius"];b=abs(q[2])-model["height"]/2
    return abs(min(max(a,b),0)+math.hypot(max(a,0),max(b,0)))

def fit(views):
    require(len(views)>=3 and all(any(abs(dot(v["direction"],a))>.999 for v in views) for a in AXES),"insufficient calibrated coverage")
    points=[p for v in views for p in v["points"]]
    require(len(points)>100,"insufficient depth observations")
    bounds=[(min(p[i] for p in points),max(p[i] for p in points)) for i in range(3)]
    center=[(a+b)/2 for a,b in bounds];size=[b-a for a,b in bounds]
    require(min(size)>STEP,"degenerate fit")
    candidates=[{"kind":"box","center":center,"size":size},
                {"kind":"cylinder","center":center,"radius":(size[0]+size[1])/4,"height":size[2]}]
    scores=[math.sqrt(sum(surface_error(c,p)**2 for p in points)/len(points)) for c in candidates]
    idx=min(range(2),key=scores.__getitem__)
    require(scores[idx]<.02 and abs(scores[0]-scores[1])>.005,"ambiguous or poor fit")
    return candidates[idx],scores

def png(path,views):
    # Three held-out views: truth, fit, pixel-level depth difference.
    a,b=views
    rows=[]
    for y in range(N-1,-1,-1):
        row=bytearray(b"\0")
        for panel in range(3):
            for x in range(N):
                i=y*N+x;t=a[i];p=b[i]
                if panel<2:
                    d=(t,p)[panel];value=0 if d is None else max(25,min(255,int(220-(d-3)*65)))
                    row.extend((value,int(value*.85),int(value*.7)) if d is not None else (20,30,45))
                else:
                    err=0 if t is None and p is None else 1 if t is None or p is None else min(1,abs(t-p)/STEP)
                    row.extend((int(240*err),int(150*(1-err)),int(80*(1-err))))
        rows.append(row)
    def chunk(k,d):return struct.pack(">I",len(d))+k+d+struct.pack(">I",zlib.crc32(k+d))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",N*3,N,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(b"".join(rows)))+chunk(b"IEND",b""))
def ply(path,views):
    pts=[p for v in views for p in v["points"]]
    path.write_text("ply\nformat ascii 1.0\nelement vertex "+str(len(pts))+"\nproperty float x\nproperty float y\nproperty float z\nend_header\n"+"".join(" ".join(f"{x:.7f}" for x in p)+"\n" for p in pts))
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    receipts=[]
    for truth in TRUTH:
        kind=truth["kind"];views=[capture(truth,a) for a in AXES]
        try:fit(views[:1])
        except RuntimeError:pass
        else:raise RuntimeError("single view incorrectly admitted")
        candidate,scores=fit(views)
        require(candidate["kind"]==kind,"wrong primitive classification")
        holdout=capture(truth,(1,-1,.7))["depths"];pred=capture(candidate,(1,-1,.7))["depths"]
        overlap=sum(t is not None and p is not None for t,p in zip(holdout,pred))
        union=sum(t is not None or p is not None for t,p in zip(holdout,pred))
        rmse=math.sqrt(sum((t-p)**2 for t,p in zip(holdout,pred) if t is not None and p is not None)/overlap)
        iou=overlap/union
        require(iou>.95 and rmse<.025,"held-out geometry error")
        ply(out/(kind+"-observations.ply"),views)
        (out/(kind+"-candidate.json")).write_text(json.dumps({"schema":"synthetic-primitive-candidate/v1","units":"m","model":candidate,"status":"candidate_not_foundry_graph","unobserved_surfaces":"inferred","truth_used_for_evaluation_only":True},indent=2)+"\n")
        png(out/(kind+"-heldout.png"),(holdout,pred))
        receipts.append({"kind":kind,"observed_points":sum(len(v["points"]) for v in views),"surface_rmse_candidates_m":scores,"heldout_depth_rmse_m":rmse,"heldout_silhouette_iou":iou,"single_view_rejected":True})
    receipt={"schema":"synthetic-depth-fit/v1","scope":"analytic metric orthographic synthetic data, not real photographs or LiDAR","source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"results":receipts,"files":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt))
if __name__=="__main__":run(Path(sys.argv[1]))
