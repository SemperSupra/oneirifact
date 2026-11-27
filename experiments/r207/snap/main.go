// Standalone reference: discrete orthogonal connector alignment and immutable proposals.
package main

import ("encoding/json";"fmt";"math";"os";"path/filepath";"reflect";"crypto/sha256")
type V [3]int
type Port struct{ID,Family,Role string; Center V; Normal V; Radius,Depth int}
type Piece struct{ID string; Origin V; QuarterTurns int; Ports []Port}
type Link struct{A,B string}
type Scene struct{Revision int; Pieces []Piece; Links []Link}
type Proposal struct{Base int; BaseHash string; Moving,Fixed,MovingPort,FixedPort string; Origin V; QuarterTurns int}
func add(a,b V)V{return V{a[0]+b[0],a[1]+b[1],a[2]+b[2]}}
func neg(a V)V{return V{-a[0],-a[1],-a[2]}}
func rot(a V,k int)V{for i:=0;i<(k%4+4)%4;i++{a=V{-a[1],a[0],a[2]}};return a}
func find(s Scene,id string)(Piece,bool){for _,p:=range s.Pieces{if p.ID==id{return p,true}};return Piece{},false}
func port(p Piece,id string)(Port,bool){for _,q:=range p.Ports{if q.ID==id{return q,true}};return Port{},false}
func occupied(s Scene,key string)bool{for _,l:=range s.Links{if l.A==key||l.B==key{return true}};return false}
func hash(s Scene)string{b,_:=json.Marshal(s);return fmt.Sprintf("%x",sha256.Sum256(b))}
func propose(s Scene,m,f,mp,fp string,k int)(Proposal,error){
    a,ok:=find(s,m);c,ok2:=find(s,f);if !ok||!ok2||m==f||k<0||k>3{return Proposal{},fmt.Errorf("invalid instance or orientation")}
    x,ok:=port(a,mp);y,ok2:=port(c,fp);if !ok||!ok2{return Proposal{},fmt.Errorf("missing port")}
    for _,l:=range s.Links{if l.A==m+"/"+mp||l.B==m+"/"+mp||l.A==f+"/"+fp||l.B==f+"/"+fp{return Proposal{},fmt.Errorf("occupied port")}}
    // For this first fixture moving a connected piece is unsupported.
    for _,l:=range s.Links{for _,key:=range []string{l.A,l.B}{for _,p:=range a.Ports{if key==m+"/"+p.ID{return Proposal{},fmt.Errorf("moving constrained piece")}}}}
    if x.Family!=y.Family||!((x.Role=="peg"&&y.Role=="socket")||(x.Role=="socket"&&y.Role=="peg")){return Proposal{},fmt.Errorf("incompatible interface")}
    peg,socket:=x,y;if x.Role=="socket"{peg,socket=y,x}
    if peg.Radius<=0||socket.Radius<peg.Radius||socket.Radius-peg.Radius>150||socket.Depth<peg.Depth||peg.Depth<=0{return Proposal{},fmt.Errorf("dimension mismatch")}
    if rot(x.Normal,k)!=neg(rot(y.Normal,c.QuarterTurns)){return Proposal{},fmt.Errorf("opposed normals required")}
    o:=add(add(c.Origin,rot(y.Center,c.QuarterTurns)),neg(rot(x.Center,k)))
    return Proposal{s.Revision,hash(s),m,f,mp,fp,o,k},nil
}
func apply(s Scene,p Proposal)(Scene,error){
    if p.Base!=s.Revision||p.BaseHash!=hash(s){return s,fmt.Errorf("stale proposal")}
    q,e:=propose(s,p.Moving,p.Fixed,p.MovingPort,p.FixedPort,p.QuarterTurns);if e!=nil||q!=p{return s,fmt.Errorf("invalid proposal")}
    out:=s;out.Pieces=append([]Piece(nil),s.Pieces...);out.Links=append([]Link(nil),s.Links...)
    for i:=range out.Pieces{if out.Pieces[i].ID==p.Moving{out.Pieces[i].Origin=p.Origin;out.Pieces[i].QuarterTurns=p.QuarterTurns}}
    out.Links=append(out.Links,Link{p.Moving+"/"+p.MovingPort,p.Fixed+"/"+p.FixedPort});out.Revision++;return out,nil
}
func fixture()Scene{return Scene{1,[]Piece{{"base",V{0,0,0},0,[]Port{{"top","stud-v1","peg",V{4000,4000,4800},V{0,0,1},2400,1800}}},{"upper",V{22000,0,15000},0,[]Port{{"bottom","stud-v1","socket",V{4000,4000,-4800},V{0,0,-1},2470,2000}}}},nil}}
func must(ok bool,msg string){if !ok{panic(msg)}}
func main(){
    s:=fixture();p,e:=propose(s,"upper","base","bottom","top",0);must(e==nil,"propose");out,e:=apply(s,p);must(e==nil,"commit");must(out.Pieces[1].Origin==V{0,0,9600},"alignment");must(s.Pieces[1].Origin==V{22000,0,15000}&&s.Revision==1,"source mutated");q,e:=apply(out,p);must(e!=nil&&reflect.DeepEqual(q,out),"stale");
    _,e=propose(out,"upper","base","bottom","top",0);must(e!=nil,"occupied")
    bad:=fixture();bad.Pieces[1].Ports[0].Radius=2000;_,e=propose(bad,"upper","base","bottom","top",0);must(e!=nil,"wrong radius")
    bad=fixture();bad.Pieces[1].Ports[0].Family="rail";_,e=propose(bad,"upper","base","bottom","top",0);must(e!=nil,"wrong family")
    bad=fixture();bad.Pieces[1].Ports[0].Normal=V{0,0,1};_,e=propose(bad,"upper","base","bottom","top",0);must(e!=nil,"wrong normal")
    tamper:=p;tamper.Origin[0]++;_,e=apply(s,tamper);must(e!=nil,"tamper")
    r,e:=propose(s,"upper","base","bottom","top",1);must(e==nil&&r.Origin==V{8000,0,9600},"quarter turn")
    _=math.Pi
    dir:=os.Args[1];os.MkdirAll(dir,0755);receipt:=map[string]any{"scope":"orthogonal port reference; no collision, multiport constraints, physical fit or native Foundry admission","unit":"micrometre","before":s,"proposal":p,"after":out,"rotated_proposal":r,"checks":[]string{"alignment","source immutable","stale rejected","occupied rejected","radius rejected","family rejected","normal rejected","tamper rejected","quarter turn"}}
    data,_:=json.MarshalIndent(receipt,"","  ");must(os.WriteFile(filepath.Join(dir,"receipt.json"),data,0644)==nil,"write")
    svg:=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 360" width="760" height="360"><rect width="760" height="360" fill="#18212c"/><g fill="white" font-family="sans-serif"><text x="25" y="30" font-size="20">R207 — connector alignment witness</text><text x="25" y="63">Before — independent instances</text><text x="410" y="63">After — matched local port frames</text></g><g stroke="#aec4da" stroke-width="2"><rect x="65" y="240" width="175" height="75" fill="#527fba"/><rect x="125" y="220" width="38" height="20" fill="#527fba"/><rect x="170" y="105" width="175" height="75" fill="#bd8053"/><path d="M230 180v-20h38v20" fill="#18212c"/><path d="M144 220L249 180" stroke="#f1c575" stroke-dasharray="5 5"/><rect x="475" y="240" width="175" height="75" fill="#527fba"/><rect x="475" y="165" width="175" height="75" fill="#bd8053"/><path d="M535 240v-20h38v20" fill="#527fba"/><circle cx="554" cy="240" r="5" fill="#6fe3b2"/></g><g fill="white" font-family="sans-serif" font-size="13"><text x="65" y="338">Initial placement</text><text x="475" y="338">Matched reference: 9.6 mm center offset</text></g></svg>`
    must(os.WriteFile(filepath.Join(dir,"alignment.svg"),[]byte(svg),0644)==nil,"svg")
    fmt.Println("R207_SNAP_PASS",string(data))
}
