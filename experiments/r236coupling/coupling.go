// Original synthetic layered articulation fixture; no anatomical donor or
// clinical properties. The dependency contract is reusable beyond humans.
package coupling

import (
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "fmt"
 "math"
)

type Vec [3]float64
func add(a,b Vec) Vec {return Vec{a[0]+b[0],a[1]+b[1],a[2]+b[2]}}
func sub(a,b Vec) Vec {return Vec{a[0]-b[0],a[1]-b[1],a[2]-b[2]}}
func mul(a Vec,s float64) Vec {return Vec{a[0]*s,a[1]*s,a[2]*s}}
func dot(a,b Vec) float64 {return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]}
func cross(a,b Vec) Vec {return Vec{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]}}
func norm(a Vec) float64 {return math.Sqrt(dot(a,a))}
func unit(a Vec) Vec {return mul(a,1/norm(a))}
type Shape struct {
 Proximal float64 // metres
 Distal float64
 BoneWidth float64
 AttachmentOffset float64
 MuscleVolume float64 // m^3; prescribed idealized value
 OrganDimensions Vec
 CavityDimensions Vec
}
type Pose struct {HingeDegrees float64}
type Source struct {Schema string;Shape Shape;Pose Pose}
type Mesh struct {Vertices []Vec;Faces [][3]int}
type Layer struct {
 ID string
 Policy string
 Dependencies []string
 Revision string
 Geometry Mesh
 Anchors []Vec
}
type Result struct {
 Schema string
 SourceDigest string
 RestDigest string
 PoseDigest string
 Layers []Layer
}
func digest(x any) string {b,e:=json.Marshal(x);if e!=nil {panic(e)};h:=sha256.Sum256(b);return hex.EncodeToString(h[:])}
func finite(x,lo,hi float64)bool{return !math.IsNaN(x)&&!math.IsInf(x,0)&&x>=lo&&x<=hi}
func Validate(s Source)error{
 a:=s.Shape
 if s.Schema!="oneirifact.synthetic-layer-coupling/v1"||!finite(a.Proximal,.2,.6)||!finite(a.Distal,.2,.6)||!finite(a.BoneWidth,.008,.03)||!finite(a.AttachmentOffset,.05,.12)||!finite(a.MuscleVolume,1e-5,2e-4)||!finite(s.Pose.HingeDegrees,-45,100){return errors.New("source domain")}
 for i:=0;i<3;i++ {if !finite(a.OrganDimensions[i],.005,.06)||!finite(a.CavityDimensions[i],.02,.12)||a.OrganDimensions[i]>=a.CavityDimensions[i] {return errors.New("organ containment")}}
 if a.CavityDimensions[0]>=a.Proximal*.8{return errors.New("cavity exceeds segment")}
 return nil
}
// A right-handed rectangular prism. Its signed volume is analytic.
func box(center,x,y,z Vec,dim Vec)Mesh{
 vs:=make([]Vec,0,8)
 for _,k:=range [][3]float64{{-1,-1,-1},{1,-1,-1},{1,1,-1},{-1,1,-1},{-1,-1,1},{1,-1,1},{1,1,1},{-1,1,1}}{
  p:=center
  for i,u:=range []Vec{x,y,z}{p=add(p,mul(u,k[i]*dim[i]/2))}
  vs=append(vs,p)
 }
 return Mesh{vs,[][3]int{{0,2,1},{0,3,2},{4,5,6},{4,6,7},{0,1,5},{0,5,4},{1,2,6},{1,6,5},{2,3,7},{2,7,6},{3,0,4},{3,4,7}}}
}
func prism(a,b Vec,w,h float64)Mesh{d:=sub(b,a);x:=unit(d);z:=Vec{0,0,1};y:=cross(z,x);return box(mul(add(a,b),.5),x,y,z,Vec{norm(d),w,h})}
func Volume(m Mesh)float64{v:=0.;for _,f:=range m.Faces{v+=dot(m.Vertices[f[0]],cross(m.Vertices[f[1]],m.Vertices[f[2]]))/6};return v}
func layer(id,policy string,deps []string,g Mesh,a []Vec)Layer{
 l:=Layer{ID:id,Policy:policy,Dependencies:append([]string(nil),deps...),Geometry:g,Anchors:a}
 l.Revision=digest(l)
 return l
}
func field(name string,value any) string {return digest(struct{Name string;Value any}{name,value})}
func Build(s Source)(Result,error){
 if e:=Validate(s);e!=nil{return Result{},e}
 h:=s.Shape;theta:=s.Pose.HingeDegrees*math.Pi/180
 rest,pose:=digest(h),digest(s.Pose)
 out:=Result{Schema:"oneirifact.synthetic-layer-result/v1",SourceDigest:digest(s),RestDigest:rest,PoseDigest:pose}
 origin:=Vec{};j:=Vec{h.Proximal,0,0};x:=Vec{math.Cos(theta),math.Sin(theta),0};y:=Vec{-math.Sin(theta),math.Cos(theta),0};z:=Vec{0,0,1}
 tip:=add(j,mul(x,h.Distal))
 // Rigid geometry and attachment identities are independently materialized.
 p:=layer("bone-proximal","rigid-rest",[]string{field("proximal_length",h.Proximal),field("bone_width",h.BoneWidth)},prism(origin,j,h.BoneWidth,h.BoneWidth),[]Vec{origin,j})
 d:=layer("bone-distal","rigid-pose",[]string{field("distal_length",h.Distal),pose,p.Revision},prism(j,tip,h.BoneWidth,h.BoneWidth),[]Vec{j,tip})
 // Anchors are defined in each segment's local frame, not mesh vertex indices.
 a:=Vec{h.Proximal*.2,h.AttachmentOffset,0}
 b:=add(add(j,mul(x,h.Distal*.8)),mul(y,h.AttachmentOffset))
 length:=norm(sub(b,a));if length<.02{return Result{},errors.New("degenerate attachment path")}
 w:=math.Sqrt(h.MuscleVolume/length)
 t:=layer("muscle-proxy","prescribed-volume-prism",[]string{field("attachment_offset",h.AttachmentOffset),field("muscle_volume",h.MuscleVolume),p.Revision,d.Revision},prism(a,b,w,w),[]Vec{a,b})
 // Organ surrogate is an independently sized rigid carried compartment.
 c:=Vec{h.Proximal*.5,-h.AttachmentOffset,0};ux,uy:=Vec{1,0,0},Vec{0,1,0}
 cavity:=layer("cavity-proxy","rigid-carried-cavity",[]string{field("attachment_offset",h.AttachmentOffset),field("cavity_dimensions",h.CavityDimensions),p.Revision},box(c,ux,uy,z,h.CavityDimensions),[]Vec{c})
 organ:=layer("organ-proxy","rigid-carried-organ",[]string{field("organ_dimensions",h.OrganDimensions),cavity.Revision},box(c,ux,uy,z,h.OrganDimensions),[]Vec{c})
 out.Layers=[]Layer{p,d,t,cavity,organ}
 return out,nil
}
// Verify exact recomputation from source, not caller-provided hashes alone.
// A downstream mixed-revision or altered coordinate is never accepted.
func Verify(s Source,out Result)error{
 want,e:=Build(s);if e!=nil{return e}
 if digest(want)!=digest(out){return errors.New("stale or altered layer graph")}
 return nil
}
func OBJ(r Result)[]byte{
 text:="# original synthetic layered geometry; metres\n";offset:=1
 for _,l:=range r.Layers{
  text+=fmt.Sprintf("o %s\n",l.ID)
  for _,p:=range l.Geometry.Vertices{text+=fmt.Sprintf("v %.12g %.12g %.12g\n",p[0],p[1],p[2])}
  for _,f:=range l.Geometry.Faces{text+=fmt.Sprintf("f %d %d %d\n",offset+f[0],offset+f[1],offset+f[2])}
  offset+=len(l.Geometry.Vertices)
 }
 return []byte(text)
}

// ChangeSet describes exact content reuse, not an assertion of reduced compute.
// Build and Verify recompute the complete bounded result before commit.
type ChangeSet struct { PreviousSource string; NextSource string; Changed []string; Reused []string }
func Update(previous Source,old Result,next Source)(Result,ChangeSet,error){
 if err:=Verify(previous,old);err!=nil{return Result{},ChangeSet{},err}
 result,err:=Build(next);if err!=nil{return Result{},ChangeSet{},err}
 if err=Verify(next,result);err!=nil{return Result{},ChangeSet{},err}
 revisions:=map[string]string{}
 for _,l:=range old.Layers{revisions[l.ID]=l.Revision}
 changes:=ChangeSet{PreviousSource:old.SourceDigest,NextSource:result.SourceDigest,Changed:[]string{},Reused:[]string{}}
 for _,l:=range result.Layers{
  if revisions[l.ID]==l.Revision{changes.Reused=append(changes.Reused,l.ID)}else{changes.Changed=append(changes.Changed,l.ID)}
 }
 return result,changes,nil
}
