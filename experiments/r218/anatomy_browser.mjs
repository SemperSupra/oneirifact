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
  for(const size of [[1200,900],[390,844]]){
    await call("Emulation.setDeviceMetricsOverride",{width:size[0],height:size[1],deviceScaleFactor:1,mobile:false});
    await call("Page.navigate",{url:base+"anatomy/index.html"});
    await until("document.querySelector('#status')?.dataset.state==='loaded' && document.querySelector('#status').dataset.layer==='combined'");
    assert(await val("document.documentElement.scrollWidth<=innerWidth+1"));
    const shot=await call("Page.captureScreenshot",{format:"png"});
    if(process.env.RUNNER_TEMP)await writeFile(join(process.env.RUNNER_TEMP,"anatomy-"+size[0]+"-combined.png"),Buffer.from(shot.data,"base64"));
    for(const layer of ["organs","heart","kidneys",process.env.SEX==="male"?"prostate":"uterus","skin"]){
      await val("(()=>{let s=document.getElementById('layer');s.value='"+layer+"';s.dispatchEvent(new Event('change'));return true})()");
      await until("document.querySelector('#status')?.dataset.state==='loaded' && document.querySelector('#status').dataset.layer==='"+layer+"'");
      assert(await val("document.getElementById('viewer').loaded"));
      assert(await val("document.getElementById('download').getAttribute('href')===document.getElementById('viewer').getAttribute('src')"));
      if(layer==="heart"){
        await val("document.getElementById('side').click()");
        await until("Math.abs(document.getElementById('viewer').getCameraOrbit().theta-Math.PI/2)<.05");
        const shot=await call("Page.captureScreenshot",{format:"png"});
        if(process.env.RUNNER_TEMP)await writeFile(join(process.env.RUNNER_TEMP,"anatomy-"+size[0]+"-heart.png"),Buffer.from(shot.data,"base64"));
      }
      console.log("R218_LAYER_PASS",process.env.SEX,size.join("x"),layer);
    }
  }
}catch(e){console.error("CHROMIUM_DIAGNOSTIC",stderr);throw e;}finally{if(ws)ws.close();if(child)child.kill();server.close();await wait(300);await rm(profile,{recursive:true,force:true,maxRetries:2});}
