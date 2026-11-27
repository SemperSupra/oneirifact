"""Bounded importer for selected official LDraw .dat parts, not native Foundry source.
Retain exact dependency closure, attribution and transform hierarchy.
Geometry-only previews; no manufacturer tolerances or connection qualification.
"""
import concurrent.futures as cf
import hashlib,json,math,sys,zipfile
from pathlib import Path,PurePosixPath
from PIL import Image,ImageDraw,ImageFont

FAMILIES={"basic":["3001","3003","3004","3005","3020","3022"],"special":["3039","3700","3068b","3002"]}
def sha(b):return hashlib.sha256(b).hexdigest()
def must(ok,msg):
    if not ok:raise ValueError(msg)
def mv(m,v):return tuple(sum(m[i][j]*v[j] for j in range(3)) for i in range(3))
def mm(a,b):return tuple(tuple(sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)) for i in range(3))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def det(m):
    a,b,c=m
    return a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
I=((1,0,0),(0,1,0),(0,0,1))
def xyz(v):return (v[0]*.0004,v[2]*.0004,-v[1]*.0004)
def numbers(t):
    n=tuple(float(x) for x in t);must(all(math.isfinite(x) and abs(x)<1e7 for x in n),"nonfinite or excessive coordinate");return n
class Library:
    def __init__(self,z):
        self.z=z;self.index={}
        for i in z.infolist():
            key=i.filename.replace("\\","/").lower()
            if key.startswith("ldraw/"):key=key[6:]
            if i.is_dir():continue
            must(key not in self.index,"ambiguous library name")
            self.index[key]=i
    def read(self,k):
        i=self.index[k];must(i.file_size<=4*1024*1024,"file budget")
        return self.z.read(i)
    def lookup(self,name):
        n=name.replace("\\","/").lower()
        p=PurePosixPath(n);must(not p.is_absolute() and ".." not in p.parts and ":" not in n and n.endswith(".dat"),"unsafe reference")
        for k in ("parts/"+n,"p/"+n,n):
            if k in self.index:return k
        raise ValueError("missing dependency "+n)
    def part(self,id):
        used={}; faces=[]; calls=0; tree=[]
        def walk(k,M,T,invert,stack):
            nonlocal calls
            calls+=1;must(calls<=10000 and len(stack)<32 and k not in stack,"expansion/cycle budget")
            raw=self.read(k)
            try:s=raw.decode("utf-8")
            except UnicodeDecodeError:s=raw.decode("cp1252")
            lines=s.splitlines()
            license_=next((l.strip() for l in lines if l.strip().startswith("0 !LICENSE")),"")
            must("CC BY 4.0" in license_ or "CC0" in license_ or "CC BY 2.0" in license_ or "CCAL version 2.0" in license_,"unreviewed license "+k+" "+license_)
            if k not in used:
                used[k]={"sha256":sha(raw),"title":lines[0] if lines else "", "author":next((l for l in lines if l.startswith("0 Author:")),""),"license":license_,"raw":raw,"references":[]}
            winding=False;pending=False;refs=[]
            for l in lines:
                t=l.split()
                if not t:continue
                typ=t[0]
                if typ=="0":
                    if len(t)>1 and t[1] in ("!TEXMAP","!DATA","FILE","NOFILE"):raise ValueError("unsupported texture/MPD "+k)
                    if len(t)>2 and t[1]=="BFC":
                        if "CW" in t[2:]:winding=True
                        if "CCW" in t[2:]:winding=False
                        if "INVERTNEXT" in t[2:]:pending=True
                    continue
                if typ=="1":
                    must(len(t)>=15,"short subfile")
                    n=numbers(t[2:14]);A=tuple(n[i:i+3] for i in (3,6,9));d=det(A);must(abs(d)>1e-12,"singular transform")
                    target=self.lookup(" ".join(t[14:]));ref={"file":target,"translation_ldu":n[:3],"matrix":A,"color":t[1],"invert_next":pending}
                    refs.append(ref)
                    walk(target,mm(M,A),add(T,mv(M,n[:3])),invert^pending,stack+[k]);pending=False
                elif typ in ("3","4"):
                    count=int(typ);must(len(t)==2+3*count,"bad face")
                    n=numbers(t[2:]);v=[xyz(add(T,mv(M,n[i:i+3]))) for i in range(0,len(n),3)]
                    flip=winding^invert^(det(M)<0)
                    for a,b,c in ((0,1,2),) if count==3 else ((0,1,2),(0,2,3)):
                        faces.append((v[a],v[c],v[b]) if flip else (v[a],v[b],v[c]))
                    must(len(faces)<=250000,"face budget")
                elif typ not in ("2","5"):raise ValueError("unsupported command "+typ)
            must(not pending,"dangling INVERTNEXT")
            used[k]["references"]=refs
        root="parts/"+id+".dat";walk(root,I,(0,0,0),False,[])
        must(faces,"empty part")
        return root,used,faces,calls

def obj(path,faces):
    vertices={};ix=[]
    for tri in faces:
        row=[]
        for v in tri:
            key=tuple(round(x,9) for x in v)
            if key not in vertices:vertices[key]=len(vertices)+1
            row.append(vertices[key])
        if len(set(row))==3:ix.append(row)
    path.write_text("# LDraw-derived geometry; see ATTRIBUTION.json and source/\n"+"".join("v %.9f %.9f %.9f\n"%v for v in vertices)+"".join("f %d %d %d\n"%tuple(f) for f in ix))
    return len(vertices),len(ix)
def view(im,rect,faces,color,below=False):
    x,y,w,h=rect
    points=[p for tri in faces for p in tri]
    center=tuple((min(p[i] for p in points)+max(p[i] for p in points))/2 for i in range(3))
    a,b=math.radians(35),math.radians(-55 if below else 55)
    def project(p):
        X,Y,Z=(p[i]-center[i] for i in range(3));u=X*math.cos(a)-Y*math.sin(a);v=X*math.sin(a)+Y*math.cos(a)
        return (u,v*math.cos(b)-Z*math.sin(b),v*math.sin(b)+Z*math.cos(b))
    projected=[tuple(project(p) for p in tri) for tri in faces]
    allp=[p for t in projected for p in t]
    sc=min(w*.87/max(max(p[0] for p in allp)-min(p[0] for p in allp),1e-9),h*.87/max(max(p[1] for p in allp)-min(p[1] for p in allp),1e-9))
    d=ImageDraw.Draw(im)
    for t in sorted(projected,key=lambda q:sum(p[2] for p in q)):
        u=tuple(t[1][i]-t[0][i] for i in range(3));v=tuple(t[2][i]-t[0][i] for i in range(3))
        n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]);l=math.sqrt(sum(q*q for q in n))
        if l<1e-20:continue
        light=.4+.6*abs(sum(n[i]*q for i,q in enumerate((.3,.4,.866)))/l)
        d.polygon([(x+w/2+p[0]*sc,y+h/2-p[1]*sc) for p in t],fill=tuple(int(c*light) for c in color))
def runpart(zip_path,id,out):
    with zipfile.ZipFile(zip_path) as z:
        lib=Library(z);root,used,faces,calls=lib.part(id)
        dest=out/id;dest.mkdir()
        for k,v in used.items():
            p=dest/"source"/k;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v.pop("raw"))
        legal=[]
        for k in sorted(lib.index):
            if "/" not in k and ("license" in k or "careadme" in k):
                raw=lib.read(k);(dest/"source"/k).write_bytes(raw);legal.append({"file":k,"sha256":sha(raw)})
        must(legal,"missing library legal records")
        (dest/"ATTRIBUTION.json").write_text(json.dumps({"upstream":"https://library.ldraw.org/updates","download":"https://library.ldraw.org/library/updates/complete.zip","part":root,"modifications":"expanded affine references, triangulated quads, mapped to metres/Z-up; edge/conditional lines and color omitted; illustrative two-sided rendering","files":used,"legal":legal},indent=2))
        nv,nf=obj(dest/"part.obj",faces)
        pts=[p for tri in faces for p in tri]
        lo=[min(p[i] for p in pts) for i in range(3)];hi=[max(p[i] for p in pts) for i in range(3)]
        row={"id":id,"title":used[root]["title"],"dependencies":len(used),"expansions":calls,"vertices":nv,"triangles":nf,"bounds_m":[lo,hi],"extent_mm":[round((b-a)*1000,4) for a,b in zip(lo,hi)],"source_root_sha256":used[root]["sha256"],"status":"REFERENCE_MESH_NOT_NATIVE","license":used[root]["license"]}
        im=Image.new("RGB",(760,440),"#18212c");d=ImageDraw.Draw(im);font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",21)
        d.text((15,12),id+" | "+used[root]["title"][2:65],font=font,fill="white")
        view(im,(10,50,365,340),faces,(210,76,65));view(im,(385,50,365,340),faces,(210,76,65),True)
        d.text((115,407),"Top / side",font=font,fill="white");d.text((495,407),"Underside",font=font,fill="white")
        im.save(dest/"preview.png");(dest/"receipt.json").write_text(json.dumps(row,indent=2));return row
def main():
    path=Path(sys.argv[1]);family=sys.argv[2];out=Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
    result=[]
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        jobs={pool.submit(runpart,path,id,out):id for id in FAMILIES[family]}
        for f in cf.as_completed(jobs):
            try:result.append(f.result())
            except Exception as e:result.append({"id":jobs[f],"status":"HELD","reason":str(e)})
    result.sort(key=lambda x:x["id"])
    (out/"manifest.json").write_text(json.dumps({"family":family,"library_zip_sha256":sha(path.read_bytes()),"unit_mapping":"1 LDU = 0.0004 m, x/z/-y","results":result},indent=2))
    print(json.dumps(result))
    must(all(r["status"]=="REFERENCE_MESH_NOT_NATIVE" for r in result),"one or more parts held")
if __name__=="__main__":main()
