// Oneirifact graph source-first OpenSCAD emission (R96)
// source revision: sha256:18051a3ea5a011a58ed0947d369db7b563ecb8d950a76e202c049b0ab5e68a36
// SCAD units: meters, Z-up; $fn is tessellation only
module of_f0() {
  cube([0.38, 0.71999999999999997, 0.029999999999999999], center=true);
}
module of_f1() {
  scale([0.10000000000000001, 0.10000000000000001, 0.10000000000000001]) of_f0();
}
of_f1();
