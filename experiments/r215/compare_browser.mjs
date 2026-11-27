// Actual Chromium CDP browser witness. No extra test framework or remote URLs.
import {spawn} from "node:child_process";
import {createServer} from "node:http";
import {readFile,mkdtemp,rm,writeFile} from "node:fs/promises";
import {existsSync} from "node:fs";
import {join,resolve,extname} from "node:path";
import {tmpdir} from "node:os";
import assert from "node:assert/strict";
const root=resolve("site");
const mime={".html":"text/html",".js":"text/javascript",".css":"text/css",".json":"application/json",".png":"image/png",".glb":"model/gltf-binary",".txt":"text/plain"};
const server=createServer(async(req,res)=>{
  try{
    let path=new URL(req.url,"http://127.0.0.1").pathname;
    if(!path.startsWith("/oneirifact/"))throw Error("path");
    let rel=path.slice("/oneirifact/".length)||"index.html";if(rel.endsWith("/"))rel+="index.html";
    const target=resolve(root,rel);if(!target.startsWith(root+"/"))throw Error("path");
    let data=await readFile(target);res.writeHead(200,{"Content-Type":mime[extname(target)]||"application/octet-stream"});res.end(data);
  }catch(e){res.writeHead(404);res.end();}
});
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const profile=await mkdtemp(join(tmpdir(),"oneirifact-viewer-"));
let child,ws,stderr="";try{
  await new Promise(r=>server.listen(0,"127.0.0.1",r));
  const base="http://127.0.0.1:"+server.address().port+"/oneirifact/";
  const browser=["/usr/bin/google-chrome","/usr/bin/chromium","/usr/bin/chromium-browser"].find(existsSync);assert(browser,"Chromium required");
  child=spawn(browser,["--headless","--disable-dev-shm-usage","--disable-background-networking","--no-first-run","--no-sandbox","--enable-unsafe-swiftshader","--use-gl=angle","--use-angle=swiftshader","--remote-debugging-port=0","--user-data-dir="+profile,"about:blank"],{stdio:["ignore","ignore","pipe"]});
  child.stderr.on("data",b=>{stderr=(stderr+b.toString()).slice(-12000)});
  let port;for(let i=0;i<300;i++){try{port=(await readFile(join(profile,"DevToolsActivePort"),"utf8")).split("\n")[0];if(port)break}catch{}if(child.exitCode!==null)break;await wait(150)}assert(port,"CDP port; exit="+child.exitCode+" stderr="+stderr);
  const targets=await (await fetch("http://127.0.0.1:"+port+"/json/list")).json();ws=new WebSocket(targets.find(t=>t.type==="page").webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.addEventListener("open",r,{once:true});ws.addEventListener("error",j,{once:true})});
  let id=0;const pending=new Map();
  ws.addEventListener("message",e=>{const m=JSON.parse(e.data);if(pending.has(m.id)){const [r,j]=pending.get(m.id);pending.delete(m.id);m.error?j(Error(m.error.message)):r(m.result)}});
  function call(method,params={}){return new Promise((r,j)=>{const n=++id;pending.set(n,[r,j]);ws.send(JSON.stringify({id:n,method,params}));setTimeout(()=>{if(pending.delete(n))j(Error("CDP timeout "+method))},20000).unref()})}
  async function val(expression){const r=await call("Runtime.evaluate",{expression,returnByValue:true});if(r.exceptionDetails)throw Error("evaluation failed");return r.result.value}
  async function until(expression){for(let i=0;i<160;i++){try{if(await val(expression))return}catch{}await wait(250)}throw Error("witness timeout: "+expression)}
  await call("Page.enable");await call("Runtime.enable");
  const size=process.env.VIEWPORT==="mobile"?[390,844]:[1200,900];
  await call("Emulation.setDeviceMetricsOverride",{width:size[0],height:size[1],deviceScaleFactor:1,mobile:false});
  for(const part of ["3001","3002","3003","3004","3005","3020","3022"]){
    await call("Page.navigate",{url:base+"compare/"+part+".html"});
    await until("location.pathname.endsWith('/"+part+".html') && document.getElementById('state')?.dataset.state==='loaded'");
    assert(await val("document.getElementById('reference').loaded && document.getElementById('candidate').loaded"));
    assert(await val("document.documentElement.scrollWidth <= innerWidth+1"));
    await val("document.getElementById('bottom').click()");
    await until("['reference','candidate'].every(id=>document.getElementById(id).getCameraOrbit().phi>3.0)");
    const shot=await call("Page.captureScreenshot",{format:"png"});
    if(process.env.RUNNER_TEMP)await writeFile(join(process.env.RUNNER_TEMP,"comparison-"+size[0]+"-"+part+".png"),Buffer.from(shot.data,"base64"));
    await val("document.getElementById('top').click()");
    await until("['reference','candidate'].every(id=>document.getElementById(id).getCameraOrbit().phi<0.1)");
    await val("document.getElementById('reset').click()");
    await until("['reference','candidate'].every(id=>Math.abs(document.getElementById(id).getCameraOrbit().theta-Math.PI/4)<0.04)");
    // Real drag in first pane; check both model orbits change and match.
    const box=await val("(()=>{let r=document.getElementById('reference').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()");
    await call("Input.dispatchMouseEvent",{type:"mousePressed",x:box.x,y:box.y,button:"left",buttons:1,clickCount:1});
    for(let i=1;i<=6;i++){await call("Input.dispatchMouseEvent",{type:"mouseMoved",x:box.x+i*7,y:box.y,button:"left",buttons:1});await wait(30);}
    await call("Input.dispatchMouseEvent",{type:"mouseReleased",x:box.x+42,y:box.y,button:"left",buttons:0,clickCount:1});
    await until("(()=>{let a=document.getElementById('reference').getCameraOrbit(),b=document.getElementById('candidate').getCameraOrbit();return Math.abs(a.theta-Math.PI/4)>.05&&Math.abs(a.theta-b.theta)<.04&&Math.abs(a.phi-b.phi)<.04})()");
    console.log("R215_COMPARE_PASS",part,size.join("x"));
  }
}catch(e){console.error("CHROMIUM_DIAGNOSTIC",stderr);throw e;}finally{if(ws)ws.close();if(child)child.kill();server.close();await wait(300);await rm(profile,{recursive:true,force:true,maxRetries:2});}
