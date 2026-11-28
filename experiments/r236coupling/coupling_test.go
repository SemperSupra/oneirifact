package coupling
import("testing";"math";"encoding/json";"os";"path/filepath")
func fixture()Source{return Source{"oneirifact.synthetic-layer-coupling/v1",Shape{.3,.25,.02,.08,.00008,Vec{.035,.025,.025},Vec{.07,.05,.05}},Pose{0}}}
func near(t *testing.T,a,b,tol float64){t.Helper();if math.Abs(a-b)>tol{t.Fatalf("%g != %g tolerance %g",a,b,tol)}}
func get(t *testing.T,s Source)Result{t.Helper();r,e:=Build(s);if e!=nil{t.Fatal(e)};if e=Verify(s,r);e!=nil{t.Fatal(e)};return r}
func TestCoupledGeometry(t *testing.T){
 s:=fixture();base:=get(t,s);s.Pose.HingeDegrees=75;posed:=get(t,s)
 for _,i:=range []int{0,3,4}{if base.Layers[i].Revision!=posed.Layers[i].Revision{t.Fatal("unaffected layer changed",i)}}
 for _,i:=range []int{1,2}{if base.Layers[i].Revision==posed.Layers[i].Revision{t.Fatal("affected layer stale",i)}}
 for _,r:=range []Result{base,posed}{
  p,d,m,c,o:=r.Layers[0],r.Layers[1],r.Layers[2],r.Layers[3],r.Layers[4]
  if p.Anchors[1]!=d.Anchors[0]{t.Fatal("joint continuity")}
  near(t,norm(sub(p.Anchors[1],p.Anchors[0])),s.Shape.Proximal,1e-12)
  near(t,norm(sub(d.Anchors[1],d.Anchors[0])),s.Shape.Distal,1e-12)
  near(t,Volume(p.Geometry),s.Shape.Proximal*s.Shape.BoneWidth*s.Shape.BoneWidth,1e-12)
  near(t,Volume(d.Geometry),s.Shape.Distal*s.Shape.BoneWidth*s.Shape.BoneWidth,1e-12)
  near(t,Volume(m.Geometry),s.Shape.MuscleVolume,1e-12)
  near(t,Volume(o.Geometry),s.Shape.OrganDimensions[0]*s.Shape.OrganDimensions[1]*s.Shape.OrganDimensions[2],1e-12)
  for _,v:=range o.Geometry.Vertices{for k:=0;k<3;k++{if math.Abs(v[k]-c.Anchors[0][k])>=s.Shape.CavityDimensions[k]/2{t.Fatal("containment")}}}
 }
 if norm(sub(posed.Layers[2].Anchors[1],base.Layers[2].Anchors[1]))<.05{t.Fatal("distal attachment did not follow")}
 q:=s;q.Shape.Proximal=.4;q.Shape.Distal=.31;changed:=get(t,q)
 near(t,changed.Layers[1].Anchors[0][0],.4,1e-12)
 near(t,norm(sub(changed.Layers[1].Anchors[1],changed.Layers[1].Anchors[0])),.31,1e-12)
 for i:=range changed.Layers{if changed.Layers[i].Revision==posed.Layers[i].Revision{t.Fatal("rest revision not propagated",i)}}
 near(t,Volume(changed.Layers[2].Geometry),q.Shape.MuscleVolume,1e-12)
 if Verify(q,posed)==nil{t.Fatal("stale result accepted")}
 tamper:=get(t,q);tamper.Layers[2]=posed.Layers[2];if Verify(q,tamper)==nil{t.Fatal("mixed revision accepted")}
 tamper=get(t,q);tamper.Layers[4].Geometry.Vertices[0][0]+=.001;if Verify(q,tamper)==nil{t.Fatal("changed geometry accepted")}
 if Verify(s,get(t,s))!=nil{t.Fatal("deterministic replay")}
 if out:=os.Getenv("COUPLING_OUTPUT");out!=""{
  if e:=os.Mkdir(out,0755);e!=nil{t.Fatal(e)}
  for _,item:=range []struct{name string;s Source;r Result}{{"rest",fixture(),base},{"posed",s,posed},{"resized",q,changed}}{
   b,e:=json.MarshalIndent(struct{Source Source;Result Result}{item.s,item.r},"","  ");if e!=nil{t.Fatal(e)}
   if e=os.WriteFile(filepath.Join(out,item.name+".json"),b,0644);e!=nil{t.Fatal(e)}
   if e=os.WriteFile(filepath.Join(out,item.name+".obj"),OBJ(item.r),0644);e!=nil{t.Fatal(e)}
  }
 }
}
func TestNegativeSources(t *testing.T){
 for _,edit:=range []func(*Source){func(s *Source){s.Shape.Distal=0},func(s *Source){s.Pose.HingeDegrees=180},func(s *Source){s.Shape.MuscleVolume=math.NaN()},func(s *Source){s.Shape.OrganDimensions[0]=.1},func(s *Source){s.Schema="unknown"}}{s:=fixture();edit(&s);if _,e:=Build(s);e==nil{t.Fatal("invalid source admitted")}}
}
