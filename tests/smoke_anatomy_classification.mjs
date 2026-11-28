// Actual pinned Model Viewer loading plus served GLB and UI membership witnesses.
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {readFile,mkdtemp,rm,writeFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {resolve,join,extname} from 'node:path';
import {tmpdir} from 'node:os';
import assert from 'node:assert/strict';

const root=resolve(process.argv[2]),out=resolve(process.argv[3]);
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.glb':'model/gltf-binary','.txt':'text/plain','.svg':'image/svg+xml'};
const server=createServer(async(req,res)=>{
  try{
    let rel=new URL(req.url,'http://127.0.0.1').pathname;
    if(!rel.startsWith('/oneirifact/'))throw Error('path');
    rel=rel.slice('/oneirifact/'.length);if(rel.endsWith('/'))rel+='index.html';
    const target=resolve(root,rel);if(!target.startsWith(root+'/'))throw Error('path');
    const data=await readFile(target);res.writeHead(200,{'Content-Type':mime[extname(target)]||'application/octet-stream'});res.end(data);
  }catch{res.writeHead(404);res.end();}
});
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const profile=await mkdtemp(join(tmpdir(),'oneirifact-r257-'));
let child,ws,stderr='';
try{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const base='http://127.0.0.1:'+server.address().port+'/oneirifact/';
  const browser=['/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'].find(existsSync);assert(browser,'Chromium required');
  child=spawn(browser,['--headless','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--no-sandbox','--enable-unsafe-swiftshader','--use-gl=angle','--use-angle=swiftshader','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore','ignore','pipe']});
  child.stderr.on('data',b=>{stderr=(stderr+b.toString()).slice(-10000)});
  let port;for(let i=0;i<200;i++){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];if(port)break}catch{}if(child.exitCode!==null)break;await wait(150)}assert(port,'CDP unavailable');
  const targets=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true})});
  let id=0;const pending=new Map();ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(pending.has(m.id)){const[r,j]=pending.get(m.id);pending.delete(m.id);m.error?j(Error(m.error.message)):r(m.result)}});
  function call(method,params={}){return new Promise((r,j)=>{const n=++id;pending.set(n,[r,j]);ws.send(JSON.stringify({id:n,method,params}));setTimeout(()=>{if(pending.delete(n))j(Error('CDP timeout '+method))},20000).unref()})}
  async function val(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
  async function until(expression){for(let i=0;i<160;i++){try{if(await val(expression))return}catch{}await wait(150)}throw Error('browser condition '+expression)}
  await call('Page.enable');await call('Runtime.enable');await call('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:base+'anatomy/'});
  await until("document.getElementById('status').dataset.state==='image' && document.getElementById('preview').naturalWidth>0");
  const cases=[
    {sex:'male',layer:'male-urinary',query:'adrenal',expected:[],nodes:6},
    {sex:'male',layer:'male-endocrine',query:'adrenal',expected:['FJ3129','FJ3130'],nodes:4},
    {sex:'female',layer:'female-respiratory',query:'diaphragmatic_surface_of_liver',expected:[],nodes:56},
    {sex:'female',layer:'female-digestive',query:'diaphragmatic_surface_of_liver',expected:['hra_0382_VH_F_diaphragmatic_surface_of_liver'],nodes:78},
  ];
  const moved=['FJ3129','FJ3130','hra_0382_VH_F_diaphragmatic_surface_of_liver'],observed=[];
  for(const c of cases){
    await val(`(()=>{const d=document.getElementById('dataset');d.value=${JSON.stringify(c.sex)};d.dispatchEvent(new Event('change'));const l=document.getElementById('layer');l.value=${JSON.stringify(c.layer)};l.dispatchEvent(new Event('change'));document.getElementById('start').click();return true})()`);
    await until("document.getElementById('status').dataset.state==='loaded' && document.querySelector('model-viewer').loaded");
    await until(`document.getElementById('count').textContent.startsWith(${JSON.stringify(c.nodes+' named source meshes')})`);
    const actual=await val(`(async()=>{const viewer=document.querySelector('model-viewer'),src=viewer.getAttribute('src'),r=await fetch(src);if(!r.ok)throw Error('served GLB');const b=await r.arrayBuffer(),v=new DataView(b),j=JSON.parse(new TextDecoder().decode(new Uint8Array(b,20,v.getUint32(12,true))));const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b))).map(x=>x.toString(16).padStart(2,'0')).join('');return {src,bytes:b.byteLength,sha256:hash,nodes:j.nodes.filter(n=>'mesh'in n).map(n=>n.name),loaded:viewer.loaded,camera_radius:viewer.getCameraOrbit().radius,scope:document.getElementById('scope').textContent}})()`);
    assert.equal(actual.src,'data/'+c.layer+'.glb');assert.equal(actual.nodes.length,c.nodes);assert(actual.loaded&&actual.camera_radius>0);
    assert.deepEqual(actual.nodes.filter(n=>moved.includes(n)).sort(),[...c.expected].sort());
    assert(actual.scope.includes('incomplete anatomy')&&actual.scope.includes('not articulated'));
    const catalog=JSON.parse(await readFile(join(root,'anatomy/data/catalog.json'),'utf8')),layer=catalog.datasets.find(d=>d.id===c.sex).layers.find(l=>l.id===c.layer);
    assert.equal(actual.sha256,layer.sha256);assert.equal(actual.bytes,layer.bytes);
    await val(`(()=>{const s=document.getElementById('search');s.value=${JSON.stringify(c.query)};s.dispatchEvent(new Event('input'));return true})()`);
    const names=await val("Array.from(document.querySelectorAll('#inventory li')).map(n=>n.textContent)");assert.equal(names.length,c.expected.length);for(const id of c.expected)assert(names.some(n=>n.includes(id)));
    assert(await val('document.documentElement.scrollWidth<=innerWidth+1'));
    await wait(250);const image=await call('Page.captureScreenshot',{format:'png'});const file=c.layer+'-classification.png';await writeFile(join(out,file),Buffer.from(image.data,'base64'));
    observed.push({...c,actual,inventory_text:names,screenshot:file});
    await val("document.getElementById('image').click()");
  }
  await writeFile(join(out,'browser-witness.json'),JSON.stringify({schema:'oneirifact.actual-classification-browser-witness/v1',status:'PASS_ACTUAL_BROWSER_MEMBERSHIP',source_head:process.env.SOURCE_HEAD_SHA||null,run_id:process.env.GITHUB_RUN_ID||null,cases:observed,limits:'Actual served display models and inventory only; no registration, coupling or physics qualification'},null,2)+'\n');
  console.log('R257_BROWSER_CLASSIFICATION_PASS',observed.length);
}catch(e){console.error('CHROMIUM_DIAGNOSTIC',stderr);throw e}finally{if(ws)ws.close();if(child)child.kill();server.close();await wait(300);await rm(profile,{recursive:true,force:true,maxRetries:2})}
