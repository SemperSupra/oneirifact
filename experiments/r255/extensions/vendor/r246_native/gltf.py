"""Small exact-source glTF transport helpers; no skin-weight reduction."""
import json,struct,hashlib,copy
import numpy as np
def sha(b):return hashlib.sha256(b).hexdigest()
def parse(raw):
    tag,v,total=struct.unpack_from("<4sII",raw);assert (tag,v,total)==(b"glTF",2,len(raw))
    n,tag=struct.unpack_from("<I4s",raw,12);assert tag==b"JSON"
    size,tag=struct.unpack_from("<I4s",raw,20+n);assert tag==b"BIN\0" and 28+n+size==len(raw)
    return json.loads(raw[20:20+n]),bytearray(raw[28+n:])
def read(d,b,i):
    a=d["accessors"][i];v=d["bufferViews"][a["bufferView"]];assert "sparse" not in a and "byteStride" not in v
    width={"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4,"MAT4":16}[a["type"]]
    dt={5121:"u1",5123:"<u2",5125:"<u4",5126:"<f4"}[a["componentType"]]
    return np.frombuffer(b,dtype=dt,count=a["count"]*width,offset=v.get("byteOffset",0)+a.get("byteOffset",0)).reshape(-1,width).copy()
def add(d,b,a,kind="VEC3",component=5126,target=None,bounds=False):
    a=np.ascontiguousarray(a);b.extend(b"\0"*(-len(b)%4));off=len(b);b.extend(a.tobytes());view={"buffer":0,"byteOffset":off,"byteLength":a.nbytes}
    if target:view["target"]=target
    j=len(d["bufferViews"]);d["bufferViews"].append(view);r={"bufferView":j,"componentType":component,"count":len(a),"type":kind}
    if bounds:r.update(min=a.min(0).reshape(-1).tolist(),max=a.max(0).reshape(-1).tolist())
    k=len(d["accessors"]);d["accessors"].append(r);return k
def encode(d,b):
    b.extend(b"\0"*(-len(b)%4));d["buffers"][0]["byteLength"]=len(b)
    j=json.dumps(d,separators=(",",":"),allow_nan=False).encode();j+=b" "*(-len(j)%4)
    return struct.pack("<4sII",b"glTF",2,28+len(j)+len(b))+struct.pack("<I4s",len(j),b"JSON")+j+struct.pack("<I4s",len(b),b"BIN\0")+b
def matrix(q,t=(0,0,0)):
    q=np.array(q,float);q/=np.linalg.norm(q);x,y,z,w=q
    R=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
    M=np.eye(4);M[:3,:3]=R;M[:3,3]=t;return M
def worlds(d):
    parents={c:i for i,n in enumerate(d["nodes"]) for c in n.get("children",[])}
    cache={}
    def get(i):
        if i in cache:return cache[i]
        n=d["nodes"][i];M=np.array(n["matrix"],float).reshape(4,4).T if "matrix" in n else matrix(n.get("rotation",[0,0,0,1]),n.get("translation",[0,0,0]))
        cache[i]=get(parents[i])@M if i in parents else M;return cache[i]
    return np.array([get(i) for i in range(163)]),parents

