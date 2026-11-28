// Oneirifact graph source-first OpenSCAD emission (R96)
// source revision: sha256:7ffd0f316da4bb467f7dea06d593933caac874483a799015a96f592cf5a2888f
// SCAD units: meters, Z-up; $fn is tessellation only
module of_f0() {
  cube([0.15800000000000003, 0.15800000000000003, 0.095999999999999988], center=true);
}
module of_f1() {
  cube([0.12800000000000003, 0.12800000000000003, 0.084999999999999992], center=true);
}
module of_f2() {
  translate([0, 0, -0.0094999999999999998]) of_f1();
}
module of_f3() {
  difference() { of_f0(); of_f2(); }
}
module of_f4() {
  cylinder(h=0.02, r=0.023999999999999997, center=true, $fn=64);
}
module of_f5() {
  translate([-0.040000000000000001, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f6() {
  union() { of_f3(); of_f5(); }
}
module of_f7() {
  translate([-0.040000000000000001, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f8() {
  union() { of_f6(); of_f7(); }
}
module of_f9() {
  translate([0.040000000000000001, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f10() {
  union() { of_f8(); of_f9(); }
}
module of_f11() {
  translate([0.040000000000000001, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f12() {
  union() { of_f10(); of_f11(); }
}
module of_f13() {
  cylinder(h=0.083000000000000004, r=0.032000000000000001, center=true, $fn=64);
}
module of_f14() {
  cylinder(h=0.086999999999999994, r=0.023999999999999997, center=true, $fn=64);
}
module of_f15() {
  difference() { of_f13(); of_f14(); }
}
module of_f16() {
  translate([0, 0, -0.0064999999999999997]) of_f15();
}
module of_f17() {
  union() { of_f12(); of_f16(); }
}
module of_f18() {
  scale([0.10000000000000001, 0.10000000000000001, 0.10000000000000001]) of_f17();
}
of_f18();
