// Package rigcore implements deterministic, geometry-independent rigid and
// linear-blend articulation. It does not implement physical tissue simulation.
package rigcore

import (
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "fmt"
 "math"
 "regexp"
)

type Vec [3]float64
type Joint struct {
 ID string `json:"id"`
 Parent string `json:"parent,omitempty"`
 Offset Vec `json:"rest_offset_m"`
 Axis Vec `json:"hinge_axis"`
 MinDeg float64 `json:"min_deg"`
 MaxDeg float64 `json:"max_deg"`
}
type Rig struct {
 Schema string `json:"schema"`
 Joints []Joint `json:"joints"`
}
type Pose struct {
 RigRevision string `json:"rig_revision"`
 Degrees map[string]float64 `json:"degrees"`
}
// A binding lives in the rest coordinate frame, not in a generated mesh's
// vertex numbering. A two-joint ramp is the first bounded field implementation.
type Binding struct {
 Kind string `json:"kind"`
 A string `json:"joint_a"`
 B string `json:"joint_b,omitempty"`
 Origin Vec `json:"origin_m"`
 Axis Vec `json:"axis"`
 Start float64 `json:"start_m"`
 End float64 `json:"end_m"`
}
type transform struct { R [3][3]float64; T Vec }
type Evaluator struct { joint map[string]transform }
var validID=regexp.MustCompile("^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
func finite(x float64) bool {return !math.IsNaN(x)&&!math.IsInf(x,0)}
func valid(v Vec) bool {for _,x:=range v{if !finite(x)||math.Abs(x)>1000{return false}};return true}
func dot(a,b Vec)float64{return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]}
func norm(a Vec)float64{return math.Sqrt(dot(a,a))}
func sub(a,b Vec)Vec{return Vec{a[0]-b[0],a[1]-b[1],a[2]-b[2]}}
func add(a,b Vec)Vec{return Vec{a[0]+b[0],a[1]+b[1],a[2]+b[2]}}
func scale(a Vec,s float64)Vec{return Vec{a[0]*s,a[1]*s,a[2]*s}}
func identity()transform{return transform{R:[3][3]float64{{1,0,0},{0,1,0},{0,0,1}}}}
func (a transform) rotate(v Vec)Vec{return Vec{dot(a.R[0],v),dot(a.R[1],v),dot(a.R[2],v)}}
func (a transform) point(v Vec)Vec{return add(a.rotate(v),a.T)}
func (a transform) then(b transform)transform{
 c:=transform{T:a.point(b.T)}
 for i:=0;i<3;i++{for j:=0;j<3;j++{for k:=0;k<3;k++{c.R[i][j]+=a.R[i][k]*b.R[k][j]}}};return c
}
func (a transform) inv()transform{
 b:=transform{};for i:=0;i<3;i++{for j:=0;j<3;j++{b.R[i][j]=a.R[j][i]}}
 b.T=scale(b.rotate(a.T),-1);return b
}
func rotation(axis Vec,deg float64)transform{
 x,y,z:=axis[0],axis[1],axis[2];t:=deg*math.Pi/180;c,s:=math.Cos(t),math.Sin(t);u:=1-c
 return transform{R:[3][3]float64{{c+x*x*u,x*y*u-z*s,x*z*u+y*s},{y*x*u+z*s,c+y*y*u,y*z*u-x*s},{z*x*u-y*s,z*y*u+x*s,c+z*z*u}}}
}
// Ordered parent-first tree. Zero is the rest pose and must be legal.
func (r Rig) Validate()error{
 if r.Schema!="oneirifact.rig/v0.1"||len(r.Joints)<1||len(r.Joints)>256{return fmt.Errorf("invalid rig schema or size")}
 seen:=map[string]bool{}
 for i,j:=range r.Joints{
  if !validID.MatchString(j.ID)||seen[j.ID]||!valid(j.Offset)||!valid(j.Axis)||math.Abs(norm(j.Axis)-1)>1e-8||!finite(j.MinDeg)||!finite(j.MaxDeg)||j.MinDeg>0||j.MaxDeg<0||j.MinDeg< -360||j.MaxDeg>360{return fmt.Errorf("invalid joint %s",j.ID)}
  if (i==0&&j.Parent!="")||(i>0&&!seen[j.Parent]){return fmt.Errorf("invalid parent order %s",j.ID)}
  seen[j.ID]=true
 }
 return nil
}
func (r Rig) Revision()(string,error){if err:=r.Validate();err!=nil{return "",err};b,err:=json.Marshal(r);if err!=nil{return "",err};h:=sha256.Sum256(b);return hex.EncodeToString(h[:]),nil}
func Compile(r Rig,p Pose)(Evaluator,error){
 rev,err:=r.Revision();if err!=nil{return Evaluator{},err};if p.RigRevision!=rev{return Evaluator{},fmt.Errorf("stale rig revision")}
 rest:=map[string]transform{};posed:=map[string]transform{};e:=Evaluator{joint:map[string]transform{}}
 for _,j:=range r.Joints{
  angle:=p.Degrees[j.ID];if !finite(angle)||angle<j.MinDeg||angle>j.MaxDeg{return Evaluator{},fmt.Errorf("joint limit %s",j.ID)}
  a,b:=identity(),rotation(j.Axis,angle);a.T=j.Offset;b.T=j.Offset
  if j.Parent!=""{a=rest[j.Parent].then(a);b=posed[j.Parent].then(b)}
  rest[j.ID]=a;posed[j.ID]=b;e.joint[j.ID]=b.then(a.inv())
 }
 for id:=range p.Degrees{if _,ok:=e.joint[id];!ok{return Evaluator{},fmt.Errorf("unknown pose joint %s",id)}}
 return e,nil
}
func (e Evaluator) ValidateBinding(b Binding)error{
 if _,ok:=e.joint[b.A];!ok{return fmt.Errorf("unknown joint A")}
 if b.Kind=="rigid"{if b.B!=""||b.Origin!=(Vec{})||b.Axis!=(Vec{})||b.Start!=0||b.End!=0{return fmt.Errorf("unexpected rigid field")};return nil}
 if b.Kind!="linear_ramp"||b.A==b.B||!valid(b.Axis)||math.Abs(norm(b.Axis)-1)>1e-8||!valid(b.Origin)||!finite(b.Start)||!finite(b.End)||b.End-b.Start<1e-6||math.Abs(b.Start)>1000||math.Abs(b.End)>1000{return fmt.Errorf("invalid binding")}
 if _,ok:=e.joint[b.B];!ok{return fmt.Errorf("unknown joint B")};return nil
}
func (e Evaluator) Point(v Vec,b Binding)(Vec,error){
 if !valid(v){return Vec{},fmt.Errorf("invalid point")};if err:=e.ValidateBinding(b);err!=nil{return Vec{},err}
 a:=e.joint[b.A].point(v);if b.Kind=="rigid"{return a,nil}
 t:=math.Max(0,math.Min(1,(dot(sub(v,b.Origin),b.Axis)-b.Start)/(b.End-b.Start)));t=t*t*(3-2*t)
 return add(scale(a,1-t),scale(e.joint[b.B].point(v),t)),nil
}
// Artistic local uniaxial stretch with transverse compensation. Determinant
// equals 1, but not a constitutive law, contact solver or tissue model.
func IsochoricStretch(v,center Vec,stretch float64)(Vec,error){
 if !valid(v)||!valid(center)||!finite(stretch)||stretch<.5||stretch>2{return Vec{},fmt.Errorf("invalid stretch")}
 q:=sub(v,center);r:=1/math.Sqrt(stretch);return add(center,Vec{q[0]*r,q[1]*r,q[2]*stretch}),nil
}
