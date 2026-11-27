package main
import("encoding/json";"fmt";"os";"bufio";"oneirifact-section-loft/loftcore")
func run()error{
 if len(os.Args)!=3{return fmt.Errorf("usage: loft source.json output.obj")}
 f,err:=os.Open(os.Args[1]);if err!=nil{return err};defer f.Close();dec:=json.NewDecoder(f);dec.DisallowUnknownFields();var s loftcore.Source;if err=dec.Decode(&s);err!=nil{return err}
 tris,err:=loftcore.Generate(s);if err!=nil{return err}
 out,err:=os.Create(os.Args[2]);if err!=nil{return err};defer out.Close();w:=bufio.NewWriter(out)
 fmt.Fprintln(w,"# Oneirifact shared section_loft kernel; metric coordinates")
 ids:=map[loftcore.Vec]int{};faces:=make([][3]int,len(tris))
 for i,t:=range tris{for j,v:=range t{n,ok:=ids[v];if !ok{n=len(ids)+1;ids[v]=n;fmt.Fprintf(w,"v %.12g %.12g %.12g\n",v[0],v[1],v[2])};faces[i][j]=n}}
 for _,f:=range faces{fmt.Fprintf(w,"f %d %d %d\n",f[0],f[1],f[2])};if err=w.Flush();err!=nil{return err}
 rev,err:=s.Revision();if err!=nil{return err};fmt.Println(rev);return nil
}
func main(){if err:=run();err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}}
