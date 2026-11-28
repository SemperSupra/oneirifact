// Shared adult numerical geometry; mode and presentation are explicit authoring policy.
export const keys=["shoulder","upper_arm","thigh","calf","back","pectoral","abdomen","hip_width","hip_depth","upper_leg_length","lower_leg_length"];
export const bounds={age_years:[25,90],height_m:[1.45,2],muscularity:[0,1],mass_morph:[0,1],torso_depth:[0,1],torso_width:[0,1],torso_length:[0,1],torso_vshape:[0,1],spine_flexion_deg:[-10,20]};
export const base={age_years:30,height_m:1.68,muscularity:.85,mass_morph:.55,torso_depth:0,torso_width:0,torso_length:0,torso_vshape:.2,spine_flexion_deg:0};
const strength={shoulder:.55,upper_arm:.45,thigh:.55,calf:.5,back:.5,pectoral:.25,abdomen:.6};
export function preset(sex="female"){if(!["female","male"].includes(sex))throw Error("Invalid preset");return {schema:"oneirifact.shared-human-design/v1",mode:"binary",gender:sex==="male"?"man":"woman",presentation:sex==="male"?"masculine":"feminine",linked:true,shape:{schema:"oneirifact.shared-adult-morphology/v1",common:{...base},appearance_mix:sex==="male"?1:0,regional:Object.fromEntries(keys.map(k=>[k,strength[k]||0])),anatomical_configuration:sex+"_reference"}}}
function exact(x,ks){return x&&typeof x==="object"&&!Array.isArray(x)&&Object.keys(x).length===ks.length&&ks.every(k=>Object.hasOwn(x,k))}
function inRange(x,a,b){return typeof x==="number"&&Number.isFinite(x)&&x>=a&&x<=b}
export function validateShape(s){if(!exact(s,["schema","common","appearance_mix","regional","anatomical_configuration"])||s.schema!=="oneirifact.shared-adult-morphology/v1"||!exact(s.common,Object.keys(bounds))||!exact(s.regional,keys)||!inRange(s.appearance_mix,0,1)||!["UNSPECIFIED","female_reference","male_reference"].includes(s.anatomical_configuration))throw Error("Invalid shape specification");for(const [k,[a,b]] of Object.entries(bounds))if(!inRange(s.common[k],a,b))throw Error("Invalid "+k);for(const k of keys)if(!inRange(s.regional[k],0,1))throw Error("Invalid "+k);return s}
export function validateDesign(d){if(!exact(d,["schema","mode","gender","presentation","linked","shape"])||d.schema!=="oneirifact.shared-human-design/v1"||!["binary","advanced"].includes(d.mode)||typeof d.linked!=="boolean")throw Error("Invalid configuration");validateShape(d.shape);const genders=d.mode==="binary"?["man","woman"]:["man","woman","nonbinary","unspecified"];const presentations=d.mode==="binary"?["masculine","feminine"]:["masculine","feminine","blended"];if(!genders.includes(d.gender)||!presentations.includes(d.presentation))throw Error("Mode forbids selected gender or presentation");if(d.presentation!=="blended"&&d.shape.appearance_mix!==(d.presentation==="masculine"?1:0))throw Error("Presentation and appearance coefficient disagree");if(d.mode==="binary"&&d.linked&&d.presentation!==(d.gender==="man"?"masculine":"feminine"))throw Error("Linked preset mismatch");if(d.linked&&(!["man","woman"].includes(d.gender)||d.presentation!==(d.gender==="man"?"masculine":"feminine")))throw Error("Linked preset mismatch");return d}
export function transition(d,patch){validateDesign(d);const q=JSON.parse(JSON.stringify(d));for(const k of Object.keys(patch))if(!["mode","gender","presentation","linked","mix","anatomy"].includes(k))throw Error("Unknown operation");if("mode"in patch)q.mode=patch.mode;if("gender"in patch)q.gender=patch.gender;if("linked"in patch)q.linked=patch.linked;if("presentation"in patch){q.presentation=patch.presentation;q.linked=false}if("mix"in patch){q.shape.appearance_mix=patch.mix;q.presentation="blended";q.linked=false}if(q.linked&&["man","woman"].includes(q.gender))q.presentation=q.gender==="man"?"masculine":"feminine";if(q.presentation!=="blended")q.shape.appearance_mix=q.presentation==="masculine"?1:0;if("anatomy"in patch)q.shape.anatomical_configuration=patch.anatomy;return validateDesign(q)}
export function evaluate(spec,data,rig){
 validateShape(spec);const s=spec.common,N=rig.vertex_count,V=rig.visible,L=N*3;if(data.length!==32*L||V!==13380||rig.bones.length!==163||JSON.stringify(rig.regional_keys)!==JSON.stringify(keys))throw Error("Invalid basis");
 const a=(s.age_years-25)/65,m=s.muscularity,w=s.mass_morph,t=spec.appearance_mix;
 const c=[1];for(const sex of [1-t,t])for(const age of [1-a,a])for(const k of [1,m*(1-w),m*w,(1-m)*(1-w)])c.push(sex*age*k);
 c.push(s.torso_depth,s.torso_width,s.torso_length,s.torso_vshape,...keys.map(k=>spec.regional[k]));
 const raw=new Float64Array(L);for(let k=0;k<c.length;k++)if(c[k])for(let i=0;i<L;i++)raw[i]+=c[k]*data[k*L+i];
 let lo=Infinity,hi=-Infinity;for(let i=0;i<V;i++){lo=Math.min(lo,raw[3*i+2]);hi=Math.max(hi,raw[3*i+2])}
 const scale=s.height_m/(hi-lo),q=new Float64Array(L);for(let i=0;i<N;i++){q[3*i]=raw[3*i]*scale;q[3*i+1]=(raw[3*i+2]-lo)*scale;q[3*i+2]=-raw[3*i+1]*scale}
 // All five spine rotations use common rest-world X; composing about the
 // refitted rest joint centres is equivalent to the R232 local-bone rotations.
 const transforms=[],angle=s.spine_flexion_deg*Math.PI/900;
 for(const b of rig.bones){
   const p=b.parent<0?[0,0,0]:transforms[b.parent];let [theta,ty,tz]=p;
   if(b.flex){let y=0,z=0;for(const i of b.head){y+=q[3*i+1];z+=q[3*i+2]}y/=b.head.length;z/=b.head.length;
     const cy=Math.cos(angle),sy=Math.sin(angle),dy=y-(cy*y-sy*z),dz=z-(sy*y+cy*z),cp=Math.cos(theta),sp=Math.sin(theta);
     ty+=cp*dy-sp*dz;tz+=sp*dy+cp*dz;theta+=angle;}
   transforms.push([theta,ty,tz]);
 }
 const out=new Float32Array(V*3);for(let i=0;i<V;i++){let y=0,z=0;const x=q[3*i],qy=q[3*i+1],qz=q[3*i+2];for(const [j,wgt] of rig.weights[i]){const [t,dy,dz]=transforms[j],c=Math.cos(t),s=Math.sin(t);y+=wgt*(c*qy-s*qz+dy);z+=wgt*(s*qy+c*qz+dz)}out[3*i]=x;out[3*i+1]=y;out[3*i+2]=z}return out;
}
export function glb(pos,faces){
 const normals=new Float32Array(pos.length),lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
 for(let i=0;i<pos.length;i++){let k=i%3;lo[k]=Math.min(lo[k],pos[i]);hi[k]=Math.max(hi[k],pos[i])}
 for(let i=0;i<faces.length;i+=3){let a=faces[i]*3,b=faces[i+1]*3,c=faces[i+2]*3;let ux=pos[b]-pos[a],uy=pos[b+1]-pos[a+1],uz=pos[b+2]-pos[a+2],vx=pos[c]-pos[a],vy=pos[c+1]-pos[a+1],vz=pos[c+2]-pos[a+2];let x=uy*vz-uz*vy,y=uz*vx-ux*vz,z=ux*vy-uy*vx;for(let j of [a,b,c]){normals[j]+=x;normals[j+1]+=y;normals[j+2]+=z}}
 for(let i=0;i<normals.length;i+=3){let n=Math.hypot(normals[i],normals[i+1],normals[i+2])||1;for(let k=0;k<3;k++)normals[i+k]/=n}
 const arrays=[pos,normals,faces],views=[],size=arrays.reduce((s,a)=>s+a.byteLength,0);let offset=0;for(let i=0;i<arrays.length;i++){views.push({buffer:0,byteOffset:offset,byteLength:arrays[i].byteLength,target:i===2?34963:34962});offset+=arrays[i].byteLength}
 const j={asset:{version:"2.0",generator:"Oneirifact adult design prototype"},scene:0,scenes:[{nodes:[0]}],nodes:[{mesh:0}],meshes:[{primitives:[{attributes:{POSITION:0,NORMAL:1},indices:2,material:0}]}],materials:[{doubleSided:true,pbrMetallicRoughness:{baseColorFactor:[.61,.69,.75,1],metallicFactor:0,roughnessFactor:.9}}],buffers:[{byteLength:size}],bufferViews:views,accessors:[{bufferView:0,componentType:5126,count:pos.length/3,type:"VEC3",min:lo,max:hi},{bufferView:1,componentType:5126,count:pos.length/3,type:"VEC3"},{bufferView:2,componentType:5125,count:faces.length,type:"SCALAR"}]};
 const raw=new TextEncoder().encode(JSON.stringify(j)),n=(raw.length+3)&~3,out=new Uint8Array(28+n+size),d=new DataView(out.buffer);
 for(const [i,v] of [[0,0x46546c67],[4,2],[8,out.length],[12,n],[16,0x4e4f534a],[20+n,size],[24+n,0x004e4942]])d.setUint32(i,v,true);
 out.fill(32,20,20+n);out.set(raw,20);offset=28+n;for(const a of arrays){out.set(new Uint8Array(a.buffer,a.byteOffset,a.byteLength),offset);offset+=a.byteLength}return out;
}