// Exercise the exact shipped exterior kernel. This does not introduce organ motion.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';

const [folder, output] = process.argv.slice(2);
if (!folder || !output || fs.existsSync(output)) throw Error('fresh output directory required');
fs.mkdirSync(output, {recursive:true});
const core = await import(pathToFileURL(path.resolve(folder, 'core.mjs')));
const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const stable = x => Array.isArray(x) ? x.map(stable) : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map(k => [k,stable(x[k])])) : x;
const bytes = x => Buffer.from(JSON.stringify(stable(x))+'\n');
const readArray = (name,T) => {const b=fs.readFileSync(path.join(folder,name)); return new T(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength));};
const basis=readArray('data/basis.bin',Float32Array), faces=readArray('data/faces.bin',Uint32Array);
const rig=JSON.parse(fs.readFileSync(path.join(folder,'data/rig.json')));
const files=['core.mjs','data/basis.bin','data/faces.bin','data/rig.json'];
const sourceHashes=Object.fromEntries(files.map(f=>[f,sha(fs.readFileSync(path.join(folder,f)))]));
function bounds(q) {const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];for(let i=0;i<q.length;i++){lo[i%3]=Math.min(lo[i%3],q[i]);hi[i%3]=Math.max(hi[i%3],q[i]);}return [lo,hi];}
function delta(q,b) {let max=0,sum=0,moved=0;for(let i=0;i<q.length;i+=3){const d=Math.hypot(q[i]-b[i],q[i+1]-b[i+1],q[i+2]-b[i+2]);max=Math.max(max,d);sum+=d*d;if(d>1e-7)moved++;}return {max_m:max,rms_m:Math.sqrt(sum/(q.length/3)),vertices_over_0_1_micrometre:moved};}
const report={schema:'oneirifact.actual-exterior-organ-propagation-audit/v1',source_hashes:sourceHashes,source_release_sha256:'5f3d2d1126dce81b813f25f392ae3d9571fe35f69d69de89939bcfcfabe61ff4',source_main_commit:'5608261f29fe42e651e7de68c4eb43fe50e30344',cases:[],internal_geometry_function:'NOT_IMPLEMENTED_IN_SHIPPED_KERNEL',mass_parameter_semantics:'mass_morph is a dimensionless exterior-shape coefficient, not kilograms',limits:'Actual exterior generation and exports only. An unchanged separate source atlas is not an evaluated coupled organ result.'};
const witnesses=new Set(['baseline','common-height_m-high','common-mass_morph-high','common-age_years-high','common-spine_flexion_deg-high','regional-abdomen-high']);
for(const sex of ['male','female']) {
 const original=core.preset(sex).shape,baseline=core.evaluate(original,basis,rig);
 const variants=[['baseline',structuredClone(original),null]];
 for(const [key,range] of Object.entries(core.bounds)) for(const [index,label] of [[0,'low'],[1,'high']]) {const s=structuredClone(original);s.common[key]=range[index];variants.push([`common-${key}-${label}`,s,`common.${key}`]);}
 for(const key of core.keys) for(const [value,label] of [[0,'low'],[1,'high']]) {const s=structuredClone(original);s.regional[key]=value;variants.push([`regional-${key}-${label}`,s,`regional.${key}`]);}
 const d=path.join(output,sex);fs.mkdirSync(d);
 for(const [name,s,field] of variants) {
  const q=core.evaluate(s,basis,rig),again=core.evaluate(s,basis,rig);
  if(!(q instanceof Float32Array) || q.length!==13380*3 || q.some(x=>!Number.isFinite(x))) throw Error('invalid actual kernel output');
  const qb=Buffer.from(q.buffer,q.byteOffset,q.byteLength);
  if(!qb.equals(Buffer.from(again.buffer,again.byteOffset,again.byteLength))) throw Error('nondeterministic actual kernel output');
  const specBytes=bytes(s),id=`${sex}/${name}`;fs.writeFileSync(path.join(d,name+'-spec.json'),specBytes);fs.writeFileSync(path.join(d,name+'-positions.f32'),qb);
  const row={id,sex,field,spec_file:id+'-spec.json',position_file:id+'-positions.f32',morphology_revision:sha(specBytes),exterior_geometry_sha256:sha(qb),source_hashes:sourceHashes,bounds_m:bounds(q),displacement_from_baseline:delta(q,baseline),returned_type:'Float32Array',returned_visible_vertices:13380,returned_internal_organ_ids:[],internal_geometry_status:'NOT_GENERATED',organ_parameter_propagation:'NOT_IMPLEMENTED',actual_coupled_organ_meshes:0};
  if(witnesses.has(name)) {const glb=core.glb(q,faces);fs.writeFileSync(path.join(d,name+'.glb'),glb);row.glb_file=id+'.glb';row.glb_sha256=sha(glb);const dv=new DataView(glb.buffer,glb.byteOffset,glb.byteLength),json=JSON.parse(new TextDecoder().decode(glb.slice(20,20+dv.getUint32(12,true))));row.actual_export={mesh_count:json.meshes.length,node_count:json.nodes.length,skin_count:(json.skins||[]).length,animation_count:(json.animations||[]).length};if(json.meshes.length!==1 || (json.skins||[]).length || (json.animations||[]).length)throw Error('unexpected shipped export schema');}
  report.cases.push(row);
 }
 // Explicit anatomical configuration does not invent internal organs or alter exterior.
 const config=structuredClone(original);config.anatomical_configuration=sex==='male'?'female_reference':'male_reference';
 const other=core.evaluate(config,basis,rig);if(!Buffer.from(other.buffer).equals(Buffer.from(baseline.buffer)))throw Error('configuration unexpectedly changes exterior');
}
fs.writeFileSync(path.join(output,'faces.u32'),Buffer.from(faces.buffer,faces.byteOffset,faces.byteLength));
fs.writeFileSync(path.join(output,'morphology-audit.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({cases:report.cases.length,actually_changed:report.cases.filter(r=>r.displacement_from_baseline.max_m>0).length,organ_function:report.internal_geometry_function}));
