// Actual Chromium CDP browser witness. No extra test framework or remote URLs.
import {spawn} from "node:child_process";
import {createServer} from "node:http";
import {readFile,mkdtemp,rm,writeFile} from "node:fs/promises";
import {existsSync} from "node:fs";
import {join,resolve,extname} from "node:path";
import {tmpdir} from "node:os";
import assert from "node:assert/strict";
const root=resolve(process.argv[2]);
const mime={".html":"text/html",".js":"text/javascript",".css":"text/css",".json":"application/json",".png":"image/png",".glb":"model/gltf-binary",".txt":"text/plain",".svg":"image/svg+xml"};
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
  await call("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await call("Page.navigate",{url:base+"anatomy/"});
  await until("document.getElementById('status')?.dataset.state==='image'");
  await val("(()=>{let x=document.getElementById('dataset');x.value='mammary';x.dispatchEvent(new Event('change'));return true})()");
  assert(await val("document.getElementById('layer').options.length===16 && !document.getElementById('dataset-receipt').hidden"));
  const ids=await val("Array.from(document.getElementById('layer').options).map(x=>x.value)");
  await val("document.getElementById('start').click()");
  await until("document.getElementById('status').dataset.state==='loaded' && document.querySelector('model-viewer').loaded");
  for(const id of ids.slice(1)){await val("(()=>{let x=document.getElementById('layer');x.value="+JSON.stringify(id)+";x.dispatchEvent(new Event('change'));return true})()");await until("document.getElementById('status').dataset.state==='loaded' && document.querySelector('model-viewer').loaded");console.log("MAMMARY_NODE_BROWSER_PASS",id)}
  await until("document.getElementById('inventory').children.length===1");
  assert(await val("document.documentElement.scrollWidth<=innerWidth+1"));
  await val("document.getElementById('display').scrollIntoView({block:'start'})");await wait(250);
  const shot=await call("Page.captureScreenshot",{format:"png"});await writeFile(join(process.env.RUNNER_TEMP,"mammary-isolation.png"),Buffer.from(shot.data,"base64"));
  console.log("MAMMARY_ALL_16_LOADED");
}catch(e){console.error("CHROMIUM_DIAGNOSTIC",stderr);throw e;}finally{if(ws)ws.close();if(child)child.kill();server.close();await wait(300);await rm(profile,{recursive:true,force:true,maxRetries:2});}
