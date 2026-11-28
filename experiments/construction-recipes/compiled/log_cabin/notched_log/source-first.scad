// Oneirifact graph source-first OpenSCAD emission (R96)
// source revision: sha256:33e8153b932e2d91ed841b628992587f6f0509b34339bca32328719a6d7b35ae
// SCAD units: meters, Z-up; $fn is tessellation only
module of_f0() {
  cube([0.64000000000000001, 0.080000000000000002, 0.080000000000000002], center=true);
}
module of_f1() {
  cube([0.083999999999999991, 0.10000000000000001, 0.041999999999999996], center=true);
}
module of_f2() {
  translate([-0.23999999999999999, 0, -0.020999999999999998]) of_f1();
}
module of_f3() {
  difference() { of_f0(); of_f2(); }
}
module of_f4() {
  translate([0.23999999999999999, 0, -0.020999999999999998]) of_f1();
}
module of_f5() {
  difference() { of_f3(); of_f4(); }
}
module of_f6() {
  scale([0.10000000000000001, 0.10000000000000001, 0.10000000000000001]) of_f5();
}
of_f6();
