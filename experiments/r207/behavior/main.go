// Deterministic microchip reference: typed bool input, bounded timer and actuator output.
// Runtime state is separate from immutable source. No physical device control.
package main
import("crypto/sha256";"encoding/json";"fmt";"os";"path/filepath";"reflect";"strings")
type Chip struct{Schema string; HoldTicks int; Actuator string}
type State struct{Tick,Remaining int; Open bool}
type Input struct{Presence bool}
func step(c Chip,s State,in Input)(State,error){
    if c.Schema!="microchip-reference/v1"||c.HoldTicks<1||c.HoldTicks>100||c.Actuator!="door-hinge"||s.Tick<0||s.Tick>=10000||s.Remaining<0||s.Remaining>c.HoldTicks||s.Open!=(s.Remaining>0){return s,fmt.Errorf("invalid state or definition")}
    s.Tick++
    if in.Presence{s.Remaining=c.HoldTicks}else if s.Remaining>0{s.Remaining--}
    s.Open=s.Remaining>0
    return s,nil
}
func must(ok bool,s string){if !ok{panic(s)}}
func replay(c Chip,inputs []Input)[]State{states:=[]State{{}};for _,in:=range inputs{s,e:=step(c,states[len(states)-1],in);must(e==nil,"step");states=append(states,s)};return states}
func main(){
    c:=Chip{"microchip-reference/v1",3,"door-hinge"}
    inputs:=[]Input{{false},{true},{false},{false},{true},{false},{false},{false},{false}}
    raw,_:=json.Marshal(c);before:=sha256.Sum256(raw);trace:=replay(c,inputs);must(reflect.DeepEqual(trace,replay(c,inputs)),"replay")
    want:=[]bool{false,false,true,true,true,true,true,true,false,false};for i,s:=range trace{must(s.Open==want[i],"timer trace")}
    bad:=c;bad.HoldTicks=0;s,e:=step(bad,trace[1],Input{});must(e!=nil&&s==trace[1],"invalid definition atomicity")
    s,e=step(c,State{Tick:1,Remaining:999,Open:true},Input{});must(e!=nil&&s.Remaining==999,"invalid state")
    raw,_=json.Marshal(c);must(sha256.Sum256(raw)==before,"source drift")
    dir:=os.Args[1];os.MkdirAll(dir,0755)
    receipt:=map[string]any{"scope":"standalone deterministic timer/door logic, not a general graph evaluator or physical simulation","definition":c,"source_sha256":fmt.Sprintf("%x",before),"inputs":inputs,"trace":trace,"checks":[]string{"timer sequence","deterministic replay","invalid definition rejected atomically","invalid state rejected","source immutable"}}
    data,_:=json.MarshalIndent(receipt,"","  ");must(os.WriteFile(filepath.Join(dir,"receipt.json"),data,0644)==nil,"receipt")
    var b strings.Builder;b.WriteString(`<svg xmlns="http://www.w3.org/2000/svg" width="900" height="390" viewBox="0 0 900 390"><rect width="900" height="390" fill="#18212c"/><g font-family="sans-serif" fill="white"><text x="25" y="35" font-size="23">R207 — executed microchip signal trace</text><text x="25" y="65">Presence → retriggerable timer → door actuator</text><text x="25" y="122">Presence</text><text x="25" y="216">Timer</text><text x="25" y="310">Door open</text></g>`)
    for i,s:=range trace{ x:=150+i*69;presence:=i>0&&inputs[i-1].Presence;for j,on:=range []bool{presence,s.Remaining>0,s.Open}{color:="#334357";if on{color="#68c6a5"};fmt.Fprintf(&b,`<rect x="%d" y="%d" width="62" height="48" rx="4" fill="%s"/>`,x,85+j*94,color)};fmt.Fprintf(&b,`<g fill="white" font-family="sans-serif" font-size="13" text-anchor="middle"><text x="%d" y="206">%d</text><text x="%d" y="352">t%d</text></g>`,x+31,s.Remaining,x+31,s.Tick)}
    b.WriteString("</svg>");must(os.WriteFile(filepath.Join(dir,"trace.svg"),[]byte(b.String()),0644)==nil,"svg")
    fmt.Println("R207_BEHAVIOR_PASS",string(data))
}
