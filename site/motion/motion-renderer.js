/* Original WebGL2 display: all three skin sets, with a GPU readback qualification hook. */
import {IDENTITY,multiply} from './motion-runtime.js';
const VERTEX=`#version 300 es
precision highp float;
layout(location=0) in vec3 position;
layout(location=1) in vec3 normal;
layout(location=2) in vec4 joints0;
layout(location=3) in vec4 weights0;
layout(location=4) in vec4 joints1;
layout(location=5) in vec4 weights1;
layout(location=6) in vec4 joints2;
layout(location=7) in vec4 weights2;
uniform bool skinned;
uniform sampler2D boneMatrices;
uniform mat4 nodeMatrix;
uniform mat4 viewProjection;
out vec3 worldPosition;
out vec3 worldNormal;
mat4 bone(float index){int j=int(index);return mat4(texelFetch(boneMatrices,ivec2(0,j),0),texelFetch(boneMatrices,ivec2(1,j),0),texelFetch(boneMatrices,ivec2(2,j),0),texelFetch(boneMatrices,ivec2(3,j),0));}
mat4 group(vec4 joints,vec4 weights){return weights.x*bone(joints.x)+weights.y*bone(joints.y)+weights.z*bone(joints.z)+weights.w*bone(joints.w);}
void main(){
  mat4 m=nodeMatrix;
  if(skinned)m=group(joints0,weights0)+group(joints1,weights1)+group(joints2,weights2);
  worldPosition=(m*vec4(position,1.0)).xyz;
  worldNormal=normalize(mat3(m)*normal);
  gl_Position=viewProjection*vec4(worldPosition,1.0);
}`;
const FRAGMENT=`#version 300 es
precision highp float;
in vec3 worldPosition;
in vec3 worldNormal;
uniform vec4 baseColor;
out vec4 color;
void main(){vec3 n=normalize(worldNormal);if(!gl_FrontFacing)n=-n;
float key=max(dot(n,normalize(vec3(-0.5,0.8,0.9))),0.0);float rim=max(dot(n,normalize(vec3(0.7,0.3,-0.5))),0.0);
vec3 light=vec3(0.35)+vec3(0.65,0.65,0.62)*key+vec3(0.14,0.22,0.25)*rim;
color=vec4(pow(max(baseColor.rgb*light,vec3(0.0)),vec3(1.0/2.2)),1.0);}`;
const norm=a=>{const n=Math.hypot(...a)||1;return a.map(x=>x/n)};
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const dot=(a,b)=>a.reduce((v,x,i)=>v+x*b[i],0);
function lookAt(eye,target){const z=norm(eye.map((x,i)=>x-target[i])),x=norm(cross([0,1,0],z)),y=cross(z,x);return new Float64Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1])}
function perspective(aspect){const f=1/Math.tan(Math.PI/8),near=.01,far=100;return new Float64Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0])}
export class MotionRenderer{
  constructor(canvas,model){
    this.canvas=canvas;this.model=model;const gl=canvas.getContext('webgl2',{antialias:true,alpha:false,preserveDrawingBuffer:true});if(!gl)throw Error('WebGL2 is unavailable. The rendered video and native downloads remain available.');this.gl=gl;this.resources=[];
    const compile=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s};
    const p=gl.createProgram(),vs=compile(gl.VERTEX_SHADER,VERTEX),fs=compile(gl.FRAGMENT_SHADER,FRAGMENT);gl.attachShader(p,vs);gl.attachShader(p,fs);gl.transformFeedbackVaryings(p,['worldPosition'],gl.INTERLEAVED_ATTRIBS);gl.linkProgram(p);gl.deleteShader(vs);gl.deleteShader(fs);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p));this.program=p;
    this.uniforms=Object.fromEntries(['skinned','boneMatrices','nodeMatrix','viewProjection','baseColor'].map(k=>[k,gl.getUniformLocation(p,k)]));
    if(gl.getParameter(gl.MAX_VERTEX_ATTRIBS)<8||gl.getParameter(gl.MAX_VERTEX_TEXTURE_IMAGE_UNITS)<1)throw Error('Full-weight shader limits are unavailable on this device.');
    const attribute=(index,width,data)=>{const b=gl.createBuffer();this.resources.push(b);gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,data instanceof Float32Array?data:new Float32Array(data),gl.STATIC_DRAW);gl.enableVertexAttribArray(index);gl.vertexAttribPointer(index,width,gl.FLOAT,false,0,0)};
    this.draws=model.meshes.map(m=>{const vao=gl.createVertexArray();gl.bindVertexArray(vao);attribute(0,3,m.position);attribute(1,3,m.normals);for(let i=0;i<3;i++){attribute(2+i*2,4,m.joints[i]||new Float32Array(m.count*4));attribute(3+i*2,4,m.weights[i]||new Float32Array(m.count*4))}
      const indices=new Uint32Array(m.indices),index=gl.createBuffer();this.resources.push(index);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,index);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);return {vao,count:indices.length};});gl.bindVertexArray(null);
    this.textures=model.skins.map(s=>{if(s.joints.length>gl.getParameter(gl.MAX_TEXTURE_SIZE))throw Error('Skin exceeds device bone texture height.');const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA32F,4,s.joints.length,0,gl.RGBA,gl.FLOAT,null);return t});
    // A real texture also remains bound for rigid primitives, avoiding incomplete sampler state.
    this.rigidTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,this.rigidTexture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA32F,4,1,0,gl.RGBA,gl.FLOAT,new Float32Array(IDENTITY));
    this.azimuth=.3;this.elevation=.12;this.follow=true;this.frame();this.upload();this.bindInteraction();this.draw();
  }
  upload(){const g=this.gl;this.model.palettes.forEach((p,i)=>{g.bindTexture(g.TEXTURE_2D,this.textures[i]);g.texSubImage2D(g.TEXTURE_2D,0,0,0,4,p.length/16,g.RGBA,g.FLOAT,p)})}
  pose(name,time){this.model.pose(name,time);this.upload();this.draw()}
  frame(){const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];for(let m=0;m<this.model.meshes.length;m++){const v=this.model.vertices(m);for(let i=0;i<v.length;i++) {const k=i%3;lo[k]=Math.min(lo[k],v[i]);hi[k]=Math.max(hi[k],v[i])}}
    this.target=lo.map((x,i)=>(x+hi[i])/2);this.distance=Math.max(1.3,Math.hypot(...hi.map((x,i)=>x-lo[i]))*1.6);this.followOrigin=this.rootPosition();this.followTarget=[...this.target];this.draw();}
  rootPosition(){const s=this.model.skins[0];if(!s)return [0,0,0];const a=this.model.worlds[s.joints[0]];return [a[12],a[13],a[14]]}
  matrix(){if(this.follow){const r=this.rootPosition();this.target=this.followTarget.map((x,i)=>x+r[i]-this.followOrigin[i])}const [x,y,z]=this.target,r=this.distance,e=this.elevation,a=this.azimuth;return multiply(perspective(this.canvas.width/this.canvas.height),lookAt([x+r*Math.cos(e)*Math.sin(a),y+r*Math.sin(e),z+r*Math.cos(e)*Math.cos(a)],this.target))}
  bindMesh(i,vp){const g=this.gl,m=this.model.meshes[i],u=this.uniforms;g.bindVertexArray(this.draws[i].vao);g.uniform1i(u.skinned,m.skin!==undefined);g.uniformMatrix4fv(u.nodeMatrix,false,new Float32Array(this.model.worlds[m.node]));g.uniformMatrix4fv(u.viewProjection,false,new Float32Array(vp));g.uniform4fv(u.baseColor,m.color);g.activeTexture(g.TEXTURE0);g.bindTexture(g.TEXTURE_2D,m.skin===undefined?this.rigidTexture:this.textures[m.skin]);g.uniform1i(u.boneMatrices,0)}
  draw(){if(!this.gl||!this.target)return;const g=this.gl,c=this.canvas,ratio=Math.min(devicePixelRatio||1,2),w=Math.max(1,Math.round(c.clientWidth*ratio)),h=Math.max(1,Math.round(c.clientHeight*ratio));if(c.width!==w||c.height!==h){c.width=w;c.height=h}g.viewport(0,0,w,h);g.clearColor(.055,.078,.095,1);g.clear(g.COLOR_BUFFER_BIT|g.DEPTH_BUFFER_BIT);g.enable(g.DEPTH_TEST);g.disable(g.CULL_FACE);g.useProgram(this.program);const vp=this.matrix();for(let i=0;i<this.draws.length;i++){this.bindMesh(i,vp);g.drawElements(g.TRIANGLES,this.draws[i].count,g.UNSIGNED_INT,0)}g.bindVertexArray(null)}
  gpuVertices(i){const g=this.gl,m=this.model.meshes[i],out=new Float32Array(m.count*3),buffer=g.createBuffer(),tf=g.createTransformFeedback();g.useProgram(this.program);this.bindMesh(i,IDENTITY);g.bindTransformFeedback(g.TRANSFORM_FEEDBACK,tf);g.bindBuffer(g.TRANSFORM_FEEDBACK_BUFFER,buffer);g.bufferData(g.TRANSFORM_FEEDBACK_BUFFER,out.byteLength,g.STREAM_READ);g.bindBufferBase(g.TRANSFORM_FEEDBACK_BUFFER,0,buffer);g.enable(g.RASTERIZER_DISCARD);g.beginTransformFeedback(g.POINTS);g.drawArrays(g.POINTS,0,m.count);g.endTransformFeedback();g.disable(g.RASTERIZER_DISCARD);g.getBufferSubData(g.TRANSFORM_FEEDBACK_BUFFER,0,out);g.bindBufferBase(g.TRANSFORM_FEEDBACK_BUFFER,0,null);g.bindTransformFeedback(g.TRANSFORM_FEEDBACK,null);g.bindVertexArray(null);g.deleteBuffer(buffer);g.deleteTransformFeedback(tf);if(g.getError()!==g.NO_ERROR)throw Error('Full-weight GPU readback failed');return out}
  bindInteraction(){const c=this.canvas;this.events=new AbortController();const opts={signal:this.events.signal};let last=null;
    c.addEventListener('pointerdown',e=>{last=[e.clientX,e.clientY];c.setPointerCapture(e.pointerId)},opts);c.addEventListener('pointerup',()=>{last=null},opts);c.addEventListener('pointercancel',()=>{last=null},opts);
    c.addEventListener('pointermove',e=>{if(!last)return;this.azimuth-=(e.clientX-last[0])*.008;this.elevation=Math.max(-1.4,Math.min(1.4,this.elevation+(e.clientY-last[1])*.008));last=[e.clientX,e.clientY];this.draw()},opts);
    c.addEventListener('wheel',e=>{e.preventDefault();this.distance=Math.max(.3,Math.min(30,this.distance*Math.exp(e.deltaY*.001)));this.draw()},{...opts,passive:false});
    c.addEventListener('keydown',e=>{const k=e.key;let handled=true;if(k==='ArrowLeft')this.azimuth-=.12;else if(k==='ArrowRight')this.azimuth+=.12;else if(k==='ArrowUp')this.elevation=Math.min(1.4,this.elevation+.1);else if(k==='ArrowDown')this.elevation=Math.max(-1.4,this.elevation-.1);else if(k==='+'||k==='=')this.distance*=.9;else if(k==='-')this.distance*=1.1;else if(k.toLowerCase()==='r')this.frame();else handled=false;if(handled){e.preventDefault();this.draw()}},opts);
    this.observer=new ResizeObserver(()=>this.draw());this.observer.observe(c);
  }
  dispose(){this.events?.abort();this.observer?.disconnect();const g=this.gl;for(const b of this.resources)g.deleteBuffer(b);for(const d of this.draws)g.deleteVertexArray(d.vao);for(const t of [...this.textures,this.rigidTexture])g.deleteTexture(t);g.deleteProgram(this.program);this.gl=null}
}
