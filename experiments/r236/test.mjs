import assert from "node:assert/strict";import {readFile} from "node:fs/promises";import {preset,transition,validateDesign,evaluate,glb} from "./core.mjs";
const root=process.argv[2],buf=async n=>{const b=await readFile(root+"/"+n);return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength)},basis=new Float32Array(await buf("basis.bin")),faces=new Uint32Array(await buf("faces.bin")),rig=JSON.parse(await readFile(root+"/rig.json","utf8")),refs=JSON.parse(await readFile(root+"/witness.json","utf8"));
let max=0;for(const r of refs){const p=evaluate(r.spec,basis,rig);assert.equal(p.length,r.positions.length);let err=0;for(let i=0;i<p.length;i++)err=Math.max(err,Math.abs(p[i]-r.positions[i]));assert(err<2e-6,r.id+" "+err);max=Math.max(max,err);assert.equal(new DataView(glb(p,faces).buffer).getUint32(0,true),0x46546c67)}
const d=preset(),saved=JSON.stringify(d);assert.throws(()=>transition(d,{mix:.4}));assert.throws(()=>transition(d,{gender:"nonbinary"}));assert.equal(JSON.stringify(d),saved);
const a=transition(d,{mode:"advanced"}),b=transition(a,{mix:.4}),c=transition(b,{gender:"nonbinary"});assert.throws(()=>transition(c,{mode:"binary"}));assert.equal(c.shape.anatomical_configuration,d.shape.anatomical_configuration);
const e=transition(c,{mode:"binary",gender:"man",presentation:"masculine"});assert.equal(e.shape.appearance_mix,1);assert.equal(e.shape.anatomical_configuration,"female_reference");
assert.deepEqual(e,validateDesign(JSON.parse(JSON.stringify(e))));assert.deepEqual(e.shape.common,d.shape.common);assert.deepEqual(e.shape.regional,d.shape.regional);
const f=transition(e,{anatomy:"male_reference"});assert.deepEqual(evaluate(e.shape,basis,rig),evaluate(f.shape,basis,rig));
assert.throws(()=>validateDesign({...d,shape:{...d.shape,common:{...d.shape.common,age_years:12}}}));
console.log("R236_SHARED_PARITY_PASS",refs.length,max,"BINARY_MODE_NEGATIVES_PASS");
