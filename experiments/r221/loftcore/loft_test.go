package loftcore
import("testing";"math")
func fixture()Source{return Source{Schema:"oneirifact.section_loft/v0.1",Name:"elliptical closed sweep",Frame:[3]Vec{{1,0,0},{0,1,0},{0,0,1}},Sides:64,Sections:[]Section{{Z:0,Radii:[2]float64{.03,.02}},{Z:.1,Radii:[2]float64{.03,.02}},{Z:.2,Radii:[2]float64{.03,.02}}}}}
func TestSectionLoft(t *testing.T){
 s:=fixture();a,err:=Generate(s);if err!=nil{t.Fatal(err)};if len(a)!=384{t.Fatal(len(a))}
 volume:=0.;edges:=map[[2]Vec]int{};for _,q:=range a{volume+=dot(q[0],cross(q[1],q[2]))/6;for i:=0;i<3;i++{edges[[2]Vec{q[i],q[(i+1)%3]}]++}}
 for e,n:=range edges{if n!=1||edges[[2]Vec{e[1],e[0]}]!=1{t.Fatal("edge not oppositely paired")}}
 want:=math.Pi*.03*.02*.2;if volume<=0||math.Abs(volume/want-1)>.002{t.Fatal(volume,want)}
 rev,_:=s.Revision();s.Sections[1].Radii[0]=.04;next,_:=s.Revision();if next==rev{t.Fatal("edit not reflected")}
 for _,bad:=range []func(*Source){func(s *Source){s.Frame[2][2]=-1},func(s *Source){s.Sections[1].Z=0},func(s *Source){s.Sections[0].Radii[0]=0},func(s *Source){s.Sections[0].Z=math.NaN()},func(s *Source){s.Sides=100}}{q:=fixture();bad(&q);if _,err:=Generate(q);err==nil{t.Fatal("invalid source admitted")}}
}
