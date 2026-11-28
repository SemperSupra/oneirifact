/* Bounded original glTF consumer. All skin influence sets remain intact. */
export const IDENTITY=new Float64Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);
export function multiply(a,b,out=new Float64Array(16)){
  for(let c=0;c<4;c++)for(let r=0;r<4;r++)out[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];return out;
}
export function trs(t,q,s){
  const [x,y,z,w]=q,[sx,sy,sz]=s,xx=x*x,yy=y*y,zz=z*z,xy=x*y,xz=x*z,yz=y*z,wx=w*x,wy=w*y,wz=w*z;
  return new Float64Array([(1-2*(yy+zz))*sx,2*(xy+wz)*sx,2*(xz-wy)*sx,0,2*(xy-wz)*sy,(1-2*(xx+zz))*sy,2*(yz+wx)*sy,0,2*(xz+wy)*sz,2*(yz-wx)*sz,(1-2*(xx+yy))*sz,0,...t,1]);
}
export function slerp(a,b,t){
  let dot=a.reduce((s,x,i)=>s+x*b[i],0),other=Array.from(b);if(dot<0){dot=-dot;other=other.map(x=>-x)}dot=Math.min(1,Math.max(-1,dot));
  let q;if(dot>.9995)q=a.map((x,i)=>x+(other[i]-x)*t);else{const angle=Math.acos(dot),d=Math.sin(angle),u=Math.sin((1-t)*angle)/d,v=Math.sin(t*angle)/d;q=a.map((x,i)=>u*x+v*other[i])}
  const length=Math.hypot(...q);return q.map(x=>x/length);
}
const TYPES={5120:[Int8Array,1],5121:[Uint8Array,1],5122:[Int16Array,2],5123:[Uint16Array,2],5125:[Uint32Array,4],5126:[Float32Array,4]};
const WIDTH={SCALAR:1,VEC2:2,VEC3:3,VEC4:4,MAT4:16};
const require=(ok,message)=>{if(!ok)throw Error(message)};
export class MotionModel{
  constructor(buffer){
    const v=new DataView(buffer);require(v.byteLength>=28&&v.getUint32(0,true)===0x46546c67&&v.getUint32(4,true)===2&&v.getUint32(8,true)===v.byteLength,'Unsupported or incomplete GLB');
    const n=v.getUint32(12,true);require(v.getUint32(16,true)===0x4e4f534a,'Missing GLB JSON');this.doc=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,n)));
    const p=20+n;require(v.getUint32(p+4,true)===0x004e4942&&p+8+v.getUint32(p,true)===buffer.byteLength,'Missing self-contained binary chunk');this.buffer=buffer;this.bin=p+8;
    const d=this.doc;require(!d.extensionsRequired?.length&&!d.buffers.some(x=>x.uri)&&!d.images?.length,'This viewer requires self-contained uncompressed geometry without texture images');
    this.accessors=new Map();this.parents=new Map();
    d.nodes.forEach((node,i)=>{for(const c of node.children||[]){require(!this.parents.has(c),'Multiple node parents');this.parents.set(c,i)}});
    this.rest=d.nodes.map(n=>({translation:n.translation||[0,0,0],rotation:n.rotation||[0,0,0,1],scale:n.scale||[1,1,1],matrix:n.matrix}));
    this.meshes=[];this.maximumInfluences=0;this.maximumWeightSets=0;
    d.nodes.forEach((node,nodeIndex)=>{if(node.mesh===undefined)return;for(const primitive of d.meshes[node.mesh].primitives){
      require((primitive.mode??4)===4&&!primitive.targets,'Unsupported primitive or morph targets');const a=primitive.attributes;
      const position=this.accessor(a.POSITION),indices=this.accessor(primitive.indices);require(position.width===3&&indices.width===1,'Invalid triangle positions/indices');
      const sets=Object.keys(a).filter(x=>x.startsWith('WEIGHTS_')).map(x=>Number(x.slice(8))).sort((x,y)=>x-y);
      let joints=[],weights=[];if(node.skin!==undefined){require(sets.length>=1&&sets.length<=3&&sets.every((x,i)=>x===i),'All skin weight sets are required; this bounded viewer supports up to twelve slots');
        for(const set of sets){joints.push(this.accessor(a['JOINTS_'+set]));weights.push(this.accessor(a['WEIGHTS_'+set]));}
        require(joints.every(j=>j.width===4&&j.count===position.count)&&weights.every(w=>w.width===4&&w.count===position.count),'Invalid skin attribute dimensions');
        const count=d.skins[node.skin].joints.length;for(let vi=0;vi<position.count;vi++){let total=0,positive=0;for(let set=0;set<sets.length;set++)for(let k=0;k<4;k++){
          const w=weights[set].data[vi*4+k],j=joints[set].data[vi*4+k];require(Number.isFinite(w)&&w>=0&&Number.isInteger(j)&&j>=0&&j<count,'Invalid full skin influence');total+=w;if(w>0)positive++;
        }require(Math.abs(total-1)<2e-5,'Skin weights must retain their original normalized sum');this.maximumInfluences=Math.max(this.maximumInfluences,positive)}
        this.maximumWeightSets=Math.max(this.maximumWeightSets,sets.length);
      }
      let normals=a.NORMAL!==undefined?this.accessor(a.NORMAL).data:this.normals(position.data,indices.data);
      const material=d.materials?.[primitive.material];const color=material?.pbrMetallicRoughness?.baseColorFactor||[.36,.65,.68,1];
      this.meshes.push({node:nodeIndex,skin:node.skin,position:position.data,normals,indices:indices.data,joints:joints.map(x=>x.data),weights:weights.map(x=>x.data),count:position.count,color,weightSets:sets.length});
    }});
    this.skins=(d.skins||[]).map(s=>({joints:s.joints,inverseBind:this.accessor(s.inverseBindMatrices).data}));
    this.animations=(d.animations||[]).map(a=>{const tracks=a.channels.map(c=>{const s=a.samplers[c.sampler];require(['LINEAR','STEP'].includes(s.interpolation||'LINEAR'),'Unsupported animation interpolation');require(['translation','rotation','scale'].includes(c.target.path)&&!this.rest[c.target.node].matrix,'Unsupported animation target');
      const input=this.accessor(s.input),output=this.accessor(s.output);require(input.width===1&&output.count===input.count,'Invalid animation samples');for(let i=1;i<input.count;i++)require(input.data[i]>input.data[i-1],'Animation times must increase');
      return {node:c.target.node,path:c.target.path,times:input.data,values:output.data,width:output.width,interpolation:s.interpolation||'LINEAR'};});return {name:a.name,tracks,duration:Math.max(...tracks.map(t=>t.times.at(-1)))};});
    require(this.animations.length&&this.meshes.length,'No named animation or geometry');this.pose(this.animations[0].name,0);
  }
  accessor(index){
    require(Number.isInteger(index),'Missing accessor');if(this.accessors.has(index))return this.accessors.get(index);
    const a=this.doc.accessors[index],view=this.doc.bufferViews[a.bufferView];require(!a.sparse,'Sparse accessors are not supported');const [Type,size]=TYPES[a.componentType]||[];require(Type,'Unsupported accessor component');const width=WIDTH[a.type];require(width,'Unsupported accessor type');
    const offset=this.bin+(view.byteOffset||0)+(a.byteOffset||0),stride=view.byteStride||size*width;require(offset>=this.bin&&offset+(a.count-1)*stride+width*size<=this.buffer.byteLength,'Accessor bounds');
    const result=new Type(a.count*width);for(let i=0;i<a.count;i++)result.set(new Type(this.buffer,offset+i*stride,width),i*width);
    let data=result;if(a.normalized){data=new Float32Array(result.length);const limit={5120:127,5121:255,5122:32767,5123:65535}[a.componentType];require(limit,'Invalid normalized accessor');for(let i=0;i<data.length;i++)data[i]=Math.max(-1,result[i]/limit)}
    const value={data,width,count:a.count,component:a.componentType};this.accessors.set(index,value);return value;
  }
  normals(positions,indices){const n=new Float32Array(positions.length);for(let i=0;i<indices.length;i+=3){const a=indices[i]*3,b=indices[i+1]*3,c=indices[i+2]*3;const ux=positions[b]-positions[a],uy=positions[b+1]-positions[a+1],uz=positions[b+2]-positions[a+2],vx=positions[c]-positions[a],vy=positions[c+1]-positions[a+1],vz=positions[c+2]-positions[a+2];const cross=[uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx];for(const p of [a,b,c])for(let k=0;k<3;k++)n[p+k]+=cross[k]}
    for(let i=0;i<n.length;i+=3){const len=Math.hypot(n[i],n[i+1],n[i+2])||1;n[i]/=len;n[i+1]/=len;n[i+2]/=len}return n;}
  pose(name,time){
    const animation=this.animations.find(a=>a.name===name);require(animation,'Unknown named animation');time=Math.max(0,Math.min(animation.duration,time));const values=this.rest.map(n=>({...n}));
    for(const track of animation.tracks){const ts=track.times;let lo=0,hi=ts.length-1;while(lo+1<hi){const mid=(lo+hi)>>1;if(ts[mid]<=time)lo=mid;else hi=mid}if(time>=ts[hi])lo=hi;
      const next=Math.min(lo+1,ts.length-1),alpha=next===lo||track.interpolation==='STEP'?0:Math.max(0,Math.min(1,(time-ts[lo])/(ts[next]-ts[lo])));
      const a=Array.from(track.values.subarray(lo*track.width,(lo+1)*track.width)),b=Array.from(track.values.subarray(next*track.width,(next+1)*track.width));values[track.node][track.path]=track.path==='rotation'?slerp(a,b,alpha):a.map((v,i)=>v+(b[i]-v)*alpha);
    }
    const worlds=new Array(values.length),visiting=new Set();const visit=i=>{if(worlds[i])return worlds[i];require(!visiting.has(i),'Cyclic hierarchy');visiting.add(i);const v=values[i],local=v.matrix?new Float64Array(v.matrix):trs(v.translation,v.rotation,v.scale);worlds[i]=this.parents.has(i)?multiply(visit(this.parents.get(i)),local):local;visiting.delete(i);return worlds[i]};values.forEach((_,i)=>visit(i));this.worlds=worlds;
    this.palettes=this.skins.map(s=>{const matrices=new Float32Array(s.joints.length*16);s.joints.forEach((j,i)=>matrices.set(multiply(worlds[j],s.inverseBind.subarray(i*16,(i+1)*16)),i*16));return matrices});this.time=time;this.animation=animation;return this;
  }
  vertices(meshIndex){const m=this.meshes[meshIndex],out=new Float32Array(m.position.length),palette=m.skin===undefined?null:this.palettes[m.skin];
    for(let i=0;i<m.count;i++){const x=m.position[i*3],y=m.position[i*3+1],z=m.position[i*3+2];if(palette){for(let set=0;set<m.weightSets;set++)for(let k=0;k<4;k++){const w=m.weights[set][i*4+k],j=m.joints[set][i*4+k]*16;if(!w)continue;for(let r=0;r<3;r++)out[i*3+r]+=w*(palette[j+r]*x+palette[j+4+r]*y+palette[j+8+r]*z+palette[j+12+r]);}}else{const a=this.worlds[m.node];for(let r=0;r<3;r++)out[i*3+r]=a[r]*x+a[4+r]*y+a[8+r]*z+a[12+r];}}return out;}
}
