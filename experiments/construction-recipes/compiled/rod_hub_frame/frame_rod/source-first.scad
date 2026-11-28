// Oneirifact graph source-first OpenSCAD emission (R96)
// source revision: sha256:91de11281ee0ca72128f9ecec6aa2623832f233052be8dbc6f3fa0473aa28be9
// SCAD units: meters, Z-up; $fn is tessellation only
module of_f0() {
  cylinder(h=0.56999999999999995, r=0.016, center=true, $fn=64);
}
module of_f1() {
  scale([0.10000000000000001, 0.10000000000000001, 0.10000000000000001]) of_f0();
}
of_f1();
