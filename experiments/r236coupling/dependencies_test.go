package coupling

import (
 "encoding/json"
 "os"
 "path/filepath"
 "reflect"
 "testing"
)

func TestLayerRevisionTransactions(t *testing.T) {
 s:=fixture()
 base:=get(t,s)
 cases:=[]struct{name string;edit func(*Source);changed []string}{
  {"pose",func(q *Source){q.Pose.HingeDegrees=60},[]string{"bone-distal","muscle-proxy"}},
  {"distal-length",func(q *Source){q.Shape.Distal=.32},[]string{"bone-distal","muscle-proxy"}},
  {"muscle-volume",func(q *Source){q.Shape.MuscleVolume=.0001},[]string{"muscle-proxy"}},
  {"organ-size",func(q *Source){q.Shape.OrganDimensions[0]=.04},[]string{"organ-proxy"}},
  {"cavity-size",func(q *Source){q.Shape.CavityDimensions[0]=.08},[]string{"cavity-proxy","organ-proxy"}},
  {"attachment",func(q *Source){q.Shape.AttachmentOffset=.09},[]string{"muscle-proxy","cavity-proxy","organ-proxy"}},
  {"proximal-length",func(q *Source){q.Shape.Proximal=.4},[]string{"bone-proximal","bone-distal","muscle-proxy","cavity-proxy","organ-proxy"}},
  {"no-op",func(q *Source){},[]string{}},
 }
 reports:=map[string]ChangeSet{}
 for _,c:=range cases {
  t.Run(c.name,func(t *testing.T){
   next:=s;c.edit(&next)
   result,changes,e:=Update(s,base,next);if e!=nil{t.Fatal(e)}
   if !reflect.DeepEqual(changes.Changed,c.changed){t.Fatalf("changed %v want %v",changes.Changed,c.changed)}
   if len(changes.Changed)+len(changes.Reused)!=len(base.Layers){t.Fatal("incomplete layer inventory")}
   for i,l:=range result.Layers {
    if l.Revision==base.Layers[i].Revision {
     if !reflect.DeepEqual(l,base.Layers[i]){t.Fatal("reuse is not byte-equivalent")}
    }
   }
   if e=Verify(next,result);e!=nil{t.Fatal(e)}
   if c.name!="no-op"&&Verify(next,base)==nil{t.Fatal("stale whole result accepted")}
   reports[c.name]=changes
  })
 }
 bad:=s;bad.Shape.OrganDimensions[0]=.1
 if r,c,e:=Update(s,base,bad);e==nil||len(r.Layers)!=0||len(c.Changed)!=0{t.Fatal("invalid next source not atomic")}
 altered:=get(t,s);altered.Layers[0].Geometry.Vertices[0][0]+=.001
 if _,_,e:=Update(s,altered,s);e==nil{t.Fatal("tampered predecessor accepted")}
 if out:=os.Getenv("DEPENDENCY_OUTPUT");out!=""{
  if e:=os.Mkdir(out,0755);e!=nil{t.Fatal(e)}
  b,e:=json.MarshalIndent(reports,"","  ");if e!=nil{t.Fatal(e)}
  if e=os.WriteFile(filepath.Join(out,"dependency-receipt.json"),b,0644);e!=nil{t.Fatal(e)}
 }
}
