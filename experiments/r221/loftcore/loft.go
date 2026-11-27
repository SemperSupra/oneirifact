// Package loftcore is an original, dependency-free procedural section primitive.
// It generates closed, elliptical-section surfaces from editable metric source.
// It is not a hollow organ, generalized branching tube, or a tissue solver.
package loftcore

import (
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "fmt"
 "math"
 "strings"
)
type Vec [3]float64
type Tri [3]Vec
type Section struct {
 Z float64 `json:"z_m"`
 Center [2]float64 `json:"center_m"`
 Radii [2]float64 `json:"radii_m"`
}
type Source struct {
 Schema string `json:"schema"`
 Name string `json:"name"`
 Origin Vec `json:"origin_m"`
 Frame [3]Vec `json:"frame_columns"`
 Sides int `json:"sides"`
 Sections []Section `json:"sections"`
}
func finite(x float64)bool{return !math.IsNaN(x)&&!math.IsInf(x,0)}
func dot(a,b Vec)float64{return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]}
func cross(a,b Vec)Vec{return Vec{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]}}
func sub(a,b Vec)Vec{return Vec{a[0]-b[0],a[1]-b[1],a[2]-b[2]}}
func good(x float64)bool{return finite(x)&&math.Abs(x)<=20}
func (s Source) Validate()error{
 if s.Schema!="oneirifact.section_loft/v0.1"||len(s.Name)==0||len(s.Name)>100||strings.ContainsAny(s.Name,"\r\n\t")||s.Sides<12||s.Sides>96||s.Sides%4!=0||len(s.Sections)<2||len(s.Sections)>64{return fmt.Errorf("invalid source or tessellation budget")}
 for _,x:=range s.Origin{if !good(x){return fmt.Errorf("invalid origin")}}
 for i,a:=range s.Frame{for _,x:=range a{if !finite(x){return fmt.Errorf("nonfinite frame")}};if math.Abs(dot(a,a)-1)>1e-8{return fmt.Errorf("nonunit frame")};for j:=0;j<i;j++{if math.Abs(dot(a,s.Frame[j]))>1e-8{return fmt.Errorf("nonorthogonal frame")}}}
 if math.Abs(dot(cross(s.Frame[0],s.Frame[1]),s.Frame[2])-1)>1e-8{return fmt.Errorf("left-handed frame")}
 for i,q:=range s.Sections{
  if !good(q.Z)||(i>0&&q.Z-s.Sections[i-1].Z<1e-6){return fmt.Errorf("unordered section")}
  for j:=0;j<2;j++{if !good(q.Center[j])||!finite(q.Radii[j])||q.Radii[j]<1e-5||q.Radii[j]>20{return fmt.Errorf("invalid section extent")}}
 }
 return nil
}
func (s Source) Revision()(string,error){if err:=s.Validate();err!=nil{return "",err};b,err:=json.Marshal(s);if err!=nil{return "",err};h:=sha256.Sum256(b);return "sha256:"+hex.EncodeToString(h[:]),nil}
func (s Source) point(p Vec)Vec{v:=s.Origin;for k:=0;k<3;k++{for j:=0;j<3;j++{v[k]+=s.Frame[j][k]*p[j]}};return v}
func Generate(s Source)([]Tri,error){
 if err:=s.Validate();err!=nil{return nil,err}
 rings:=make([][]Vec,len(s.Sections))
 for i,q:=range s.Sections{rings[i]=make([]Vec,s.Sides);for j:=0;j<s.Sides;j++{a:=2*math.Pi*float64(j)/float64(s.Sides);rings[i][j]=s.point(Vec{q.Center[0]+q.Radii[0]*math.Cos(a),q.Center[1]+q.Radii[1]*math.Sin(a),q.Z})}}
 out:=make([]Tri,0,2*len(rings)*s.Sides)
 for i:=1;i<len(rings);i++{a,b:=rings[i-1],rings[i];for j:=0;j<s.Sides;j++{k:=(j+1)%s.Sides;out=append(out,Tri{a[j],a[k],b[k]},Tri{a[j],b[k],b[j]})}}
 first,last:=s.Sections[0],s.Sections[len(rings)-1];lo:=s.point(Vec{first.Center[0],first.Center[1],first.Z});hi:=s.point(Vec{last.Center[0],last.Center[1],last.Z})
 for j:=0;j<s.Sides;j++{k:=(j+1)%s.Sides;out=append(out,Tri{lo,rings[0][k],rings[0][j]},Tri{hi,rings[len(rings)-1][j],rings[len(rings)-1][k]})}
 for _,t:=range out{a:=cross(sub(t[1],t[0]),sub(t[2],t[0]));if dot(a,a)<1e-30{return nil,fmt.Errorf("degenerate triangle")}}
 return out,nil
}
