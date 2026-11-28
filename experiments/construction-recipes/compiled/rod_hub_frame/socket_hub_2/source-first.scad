// Oneirifact graph source-first OpenSCAD emission (R96)
// source revision: sha256:c0963c38662b98bb55fbeebd90a85ae3d9b25b7472df2c3a75435064e6d2efd4
// SCAD units: meters, Z-up; $fn is tessellation only
module of_f0() {
  sphere(r=0.059999999999999998, $fn=64);
}
module of_f1() {
  cylinder(h=0.074999999999999997, r=0.017999999999999999, center=true, $fn=64);
}
module of_f2() {
  rotate([0, 90, -119.99999999999999]) of_f1();
}
module of_f3() {
  translate([-0.02, -0.034641016151377546, 0]) of_f2();
}
module of_f4() {
  difference() { of_f0(); of_f3(); }
}
module of_f5() {
  cylinder(h=0.074999999999999997, r=0.017999999999999999, center=true, $fn=64);
}
module of_f6() {
  rotate([0, 90, -60.000000000000007]) of_f5();
}
module of_f7() {
  translate([0.02, -0.034641016151377546, 0]) of_f6();
}
module of_f8() {
  difference() { of_f4(); of_f7(); }
}
module of_f9() {
  cylinder(h=0.074999999999999997, r=0.017999999999999999, center=true, $fn=64);
}
module of_f10() {
  rotate([0, 35.264389682754654, -90]) of_f9();
}
module of_f11() {
  translate([0, -0.023094010767585035, 0.032659863237109045]) of_f10();
}
module of_f12() {
  difference() { of_f8(); of_f11(); }
}
module of_f13() {
  scale([0.10000000000000001, 0.10000000000000001, 0.10000000000000001]) of_f12();
}
of_f13();
