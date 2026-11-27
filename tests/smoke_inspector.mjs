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
let child,ws;try{
  await new Promise(r=>server.listen(0,"127.0.0.1",r));
  const base="http://127.0.0.1:"+server.address().port+"/oneirifact/";
  const browser=["/usr/bin/google-chrome","/usr/bin/chromium","/usr/bin/chromium-browser"].find(existsSync);assert(browser,"Chromium required");
  child=spawn(browser,["--headless","--disable-dev-shm-usage","--disable-background-networking","--no-first-run","--no-sandbox","--enable-unsafe-swiftshader","--use-gl=angle","--use-angle=swiftshader","--remote-debugging-port=0","--user-data-dir="+profile,"about:blank"],{stdio:"ignore"});
  let port;for(let i=0;i<100;i++){try{port=(await readFile(join(profile,"DevToolsActivePort"),"utf8")).split("\n")[0];break}catch{await wait(100)}}assert(port,"CDP port");
  const targets=await (await fetch("http://127.0.0.1:"+port+"/json/list")).json();ws=new WebSocket(targets.find(t=>t.type==="page").webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.addEventListener("open",r,{once:true});ws.addEventListener("error",j,{once:true})});
  let id=0;const pending=new Map();
  ws.addEventListener("message",e=>{const m=JSON.parse(e.data);if(pending.has(m.id)){const [r,j]=pending.get(m.id);pending.delete(m.id);m.error?j(Error(m.error.message)):r(m.result)}});
  function call(method,params={}){return new Promise((r,j)=>{const n=++id;pending.set(n,[r,j]);ws.send(JSON.stringify({id:n,method,params}));setTimeout(()=>{if(pending.delete(n))j(Error("CDP timeout "+method))},20000).unref()})}
  async function val(expression){const r=await call("Runtime.evaluate",{expression,returnByValue:true});if(r.exceptionDetails)throw Error("evaluation failed");return r.result.value}
  async function until(expression){for(let i=0;i<160;i++){try{if(await val(expression))return}catch{}await wait(250)}throw Error("witness timeout: "+expression)}
  await call("Page.enable");await call("Runtime.enable");
  for(const size of [[1200,900],[390,844]]){
    await call("Emulation.setDeviceMetricsOverride",{width:size[0],height:size[1],deviceScaleFactor:1,mobile:false});
    await call("Page.navigate",{url:base+"inspect/pavilion-day.html"});
    await until("document.title.startsWith('Pavilion Day') && document.querySelector('model-viewer')?.loaded");
    await until("document.getElementById('viewer-status').dataset.state === 'loaded'");
    assert(await val("document.querySelector('model-viewer').getCameraOrbit().radius > 0"));
    await val("(()=>{let m=document.querySelector('model-viewer');m.cameraOrbit='45deg 60deg 105%';m.jumpCameraToGoal();return true})()");
    await until("Math.abs(document.querySelector('model-viewer').getCameraOrbit().theta - Math.PI/4)<0.03");
    assert(await val("document.documentElement.scrollWidth <= innerWidth+1"));
    const shot=await call("Page.captureScreenshot",{format:"png"});if(process.env.RUNNER_TEMP)await writeFile(join(process.env.RUNNER_TEMP,"inspector-"+size[0]+".png"),Buffer.from(shot.data,"base64"));
    console.log("MODEL_VIEWER_PASS",size.join("x"));
  }
  await call("Page.navigate",{url:base+"inspect/pavilion.py.html"});await until("document.title.startsWith('pavilion.py') && !!document.querySelector('code.hljs .hljs-keyword')");assert(await val("document.querySelector('code').textContent.includes('def render(')"));
  await call("Page.navigate",{url:base+"inspect/specs.json.html"});await until("document.title.startsWith('specs.json') && document.querySelectorAll('details').length > 4");
  assert(await val("document.body.textContent.includes('oneirifact.public-procedural-raytrace-study/v0.1')"));
  console.log("SOURCE_AND_JSON_VIEW_PASS");
}finally{if(ws)ws.close();if(child)child.kill();server.close();await wait(300);await rm(profile,{recursive:true,force:true,maxRetries:2});}
