// Oneirifact graph source-first OpenSCAD emission (R96)
// source revision: sha256:289f0bb58ee6a1501f5a130eaf75d369357a70380222656829ae61eee46c7b26
// SCAD units: meters, Z-up; $fn is tessellation only
module of_f0() {
  cube([0.6379999999999999, 0.15800000000000003, 0.095999999999999988], center=true);
}
module of_f1() {
  cube([0.60799999999999987, 0.12800000000000003, 0.084999999999999992], center=true);
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
  translate([-0.28000000000000003, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f6() {
  union() { of_f3(); of_f5(); }
}
module of_f7() {
  translate([-0.28000000000000003, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f8() {
  union() { of_f6(); of_f7(); }
}
module of_f9() {
  translate([-0.20000000000000001, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f10() {
  union() { of_f8(); of_f9(); }
}
module of_f11() {
  translate([-0.20000000000000001, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f12() {
  union() { of_f10(); of_f11(); }
}
module of_f13() {
  translate([-0.12, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f14() {
  union() { of_f12(); of_f13(); }
}
module of_f15() {
  translate([-0.12, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f16() {
  union() { of_f14(); of_f15(); }
}
module of_f17() {
  translate([-0.040000000000000001, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f18() {
  union() { of_f16(); of_f17(); }
}
module of_f19() {
  translate([-0.040000000000000001, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f20() {
  union() { of_f18(); of_f19(); }
}
module of_f21() {
  translate([0.040000000000000001, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f22() {
  union() { of_f20(); of_f21(); }
}
module of_f23() {
  translate([0.040000000000000001, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f24() {
  union() { of_f22(); of_f23(); }
}
module of_f25() {
  translate([0.12, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f26() {
  union() { of_f24(); of_f25(); }
}
module of_f27() {
  translate([0.12, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f28() {
  union() { of_f26(); of_f27(); }
}
module of_f29() {
  translate([0.20000000000000001, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f30() {
  union() { of_f28(); of_f29(); }
}
module of_f31() {
  translate([0.20000000000000001, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f32() {
  union() { of_f30(); of_f31(); }
}
module of_f33() {
  translate([0.28000000000000003, -0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f34() {
  union() { of_f32(); of_f33(); }
}
module of_f35() {
  translate([0.28000000000000003, 0.040000000000000001, 0.056000000000000001]) of_f4();
}
module of_f36() {
  union() { of_f34(); of_f35(); }
}
module of_f37() {
  cylinder(h=0.083000000000000004, r=0.032000000000000001, center=true, $fn=64);
}
module of_f38() {
  cylinder(h=0.086999999999999994, r=0.023999999999999997, center=true, $fn=64);
}
module of_f39() {
  difference() { of_f37(); of_f38(); }
}
module of_f40() {
  translate([-0.23999999999999999, 0, -0.0064999999999999997]) of_f39();
}
module of_f41() {
  union() { of_f36(); of_f40(); }
}
module of_f42() {
  cylinder(h=0.083000000000000004, r=0.032000000000000001, center=true, $fn=64);
}
module of_f43() {
  cylinder(h=0.086999999999999994, r=0.023999999999999997, center=true, $fn=64);
}
module of_f44() {
  difference() { of_f42(); of_f43(); }
}
module of_f45() {
  translate([-0.16, 0, -0.0064999999999999997]) of_f44();
}
module of_f46() {
  union() { of_f41(); of_f45(); }
}
module of_f47() {
  cylinder(h=0.083000000000000004, r=0.032000000000000001, center=true, $fn=64);
}
module of_f48() {
  cylinder(h=0.086999999999999994, r=0.023999999999999997, center=true, $fn=64);
}
module of_f49() {
  difference() { of_f47(); of_f48(); }
}
module of_f50() {
  translate([-0.080000000000000002, 0, -0.0064999999999999997]) of_f49();
}
module of_f51() {
  union() { of_f46(); of_f50(); }
}
module of_f52() {
  cylinder(h=0.083000000000000004, r=0.032000000000000001, center=true, $fn=64);
}
module of_f53() {
  cylinder(h=0.086999999999999994, r=0.023999999999999997, center=true, $fn=64);
}
module of_f54() {
  difference() { of_f52(); of_f53(); }
}
module of_f55() {
  translate([0, 0, -0.0064999999999999997]) of_f54();
}
module of_f56() {
  union() { of_f51(); of_f55(); }
}
module of_f57() {
  cylinder(h=0.083000000000000004, r=0.032000000000000001, center=true, $fn=64);
}
module of_f58() {
  cylinder(h=0.086999999999999994, r=0.023999999999999997, center=true, $fn=64);
}
module of_f59() {
  difference() { of_f57(); of_f58(); }
}
module of_f60() {
  translate([0.080000000000000002, 0, -0.0064999999999999997]) of_f59();
}
module of_f61() {
  union() { of_f56(); of_f60(); }
}
module of_f62() {
  cylinder(h=0.083000000000000004, r=0.032000000000000001, center=true, $fn=64);
}
module of_f63() {
  cylinder(h=0.086999999999999994, r=0.023999999999999997, center=true, $fn=64);
}
module of_f64() {
  difference() { of_f62(); of_f63(); }
}
module of_f65() {
  translate([0.16, 0, -0.0064999999999999997]) of_f64();
}
module of_f66() {
  union() { of_f61(); of_f65(); }
}
module of_f67() {
  cylinder(h=0.083000000000000004, r=0.032000000000000001, center=true, $fn=64);
}
module of_f68() {
  cylinder(h=0.086999999999999994, r=0.023999999999999997, center=true, $fn=64);
}
module of_f69() {
  difference() { of_f67(); of_f68(); }
}
module of_f70() {
  translate([0.23999999999999999, 0, -0.0064999999999999997]) of_f69();
}
module of_f71() {
  union() { of_f66(); of_f70(); }
}
module of_f72() {
  scale([0.10000000000000001, 0.10000000000000001, 0.10000000000000001]) of_f71();
}
of_f72();
