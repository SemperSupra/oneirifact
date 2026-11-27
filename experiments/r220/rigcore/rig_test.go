package rigcore
import("testing";"math";"encoding/json";"os")
func fixture()Rig{return Rig{Schema:"oneirifact.rig/v0.1",Joints:[]Joint{{ID:"root",Axis:Vec{0,0,1}},{ID:"hinge",Parent:"root",Offset:Vec{0,0,1},Axis:Vec{0,1,0},MinDeg:-90,MaxDeg:90},{ID:"tip",Parent:"hinge",Offset:Vec{0,0,1},Axis:Vec{1,0,0}}}}}
func near(a,b Vec)bool{return norm(sub(a,b))<1e-10}
func TestRigSourceAndPose(t *testing.T){
 r:=fixture();rev,err:=r.Revision();if err!=nil{t.Fatal(err)};e,err:=Compile(r,Pose{rev,map[string]float64{"hinge":90}});if err!=nil{t.Fatal(err)}
 rigid:=Binding{Kind:"rigid",A:"tip"};v,err:=e.Point(Vec{0,0,2},rigid);if err!=nil||!near(v,Vec{1,0,1}){t.Fatal(v,err)}
 pivot,err:=e.Point(Vec{0,0,1},Binding{Kind:"rigid",A:"hinge"});if err!=nil||!near(pivot,Vec{0,0,1}){t.Fatal(pivot,err)}
 b:=Binding{Kind:"linear_ramp",A:"root",B:"hinge",Axis:Vec{0,0,1},Start:0,End:2}
 rest,err:=Compile(r,Pose{rev,nil});if err!=nil{t.Fatal(err)}
 for _,p:=range []Vec{{.1,0,0},{.1,0,1},{.1,0,2}}{q,err:=rest.Point(p,b);if err!=nil||!near(q,p){t.Fatal(q,err)}}
 for _,bad:=range []Pose{{"stale",nil},{rev,map[string]float64{"hinge":91}},{rev,map[string]float64{"unknown":1}},{rev,map[string]float64{"hinge":math.NaN()}}}{if _,err:=Compile(r,bad);err==nil{t.Fatal("invalid pose admitted")}}
 invalid:=r;invalid.Joints=append([]Joint(nil),r.Joints...);invalid.Joints[1].Parent="tip";if invalid.Validate()==nil{t.Fatal("cycle admitted")}
 if _,err:=e.Point(Vec{},Binding{Kind:"rigid",A:"missing"});err==nil{t.Fatal("missing joint admitted")}
 if _,err:=e.Point(Vec{},Binding{Kind:"linear_ramp",A:"root",B:"hinge",Axis:Vec{0,0,1},Start:1,End:1});err==nil{t.Fatal("bad field admitted")}
 // Demonstrate that LBS does not preserve volume: a 90-degree equal
 // blend contracts the rotation plane; it is not a tissue solver.
 q,err:=e.Point(Vec{1,0,1},b);if err!=nil||!near(q,Vec{.5,0,.5}){t.Fatal(q,err)}
 a,_:=IsochoricStretch(Vec{1,0,0},Vec{},1.5);c,_:=IsochoricStretch(Vec{0,0,1},Vec{},1.5);det:=a[0]*a[0]*c[2];if math.Abs(det-1)>1e-12{t.Fatal(det)}
 if _,err:=IsochoricStretch(Vec{},Vec{},0);err==nil{t.Fatal("invalid stretch admitted")}
 if path:=os.Getenv("R220_RIG_RECEIPT");path!=""{raw,err:=json.MarshalIndent(map[string]any{"rig":r,"rig_revision":rev,"tip_posed":v,"pivot":pivot,"blend_witness":q,"isochoric_determinant":det,"scope":"shared rig kernel only; no native Foundry, collision or tissue qualification"},"","  ");if err!=nil{t.Fatal(err)};if err=os.WriteFile(path,raw,0600);err!=nil{t.Fatal(err)}}
}
