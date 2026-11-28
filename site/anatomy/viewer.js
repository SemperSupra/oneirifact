'use strict';
const $=id=>document.getElementById(id), viewer=$('viewer');
let catalog,active,mode=false,inventory=[],shown=40,request=0;
const path=p=>{if(typeof p!=='string'||!/^data\/[a-z0-9-]+\.[a-z0-9]+$/.test(p))throw Error('Unexpected asset path');return p;};
async function data(p){const r=await fetch(path(p));if(!r.ok)throw Error('Asset unavailable');return r.json();}
function status(t,state='pending'){$('status').textContent=t;$('status').dataset.state=state;}
function option(el,value,label){const o=new Option(label,value);el.add(o);}
function link(id,url){const a=$(id);a.hidden=!url;if(url)a.href=path(url);}
function chooseDataset(){
 active=catalog.datasets.find(d=>d.id===$('dataset').value);if(!active)throw Error('Unknown dataset');
 $('layer').replaceChildren();for(const m of active.layers)option($('layer'),m.id,m.label);
 $('layer').disabled=false;$('scope').textContent=active.source+'. '+active.scope;
 $('preview').src=path(active.preview);$('preview').alt=active.label+' — rendered reference';
 link('attribution',active.attribution);link('attribution2',active.additional_attribution);
 $('search').value='';inventory=[];const epoch=++request;$('inventory-panel').hidden=!active.inventory;
 if(active.inventory)data(active.inventory).then(rows=>{if(epoch===request){inventory=rows;list();}}).catch(()=>{$('count').textContent='Inventory unavailable';});
 chooseLayer();
}
function selected(){return active.layers.find(m=>m.id===$('layer').value);}
function list(){if(!active)return;const m=selected(),q=$('search').value.toLowerCase().trim(),all=inventory.filter(r=>r.layer===m.id&&(!q||[r.id,...r.names].join(' ').toLowerCase().includes(q)));$('inventory').replaceChildren();
 for(const r of all.slice(0,shown)){const li=document.createElement('li');li.textContent=r.names.join(' / ')+' · '+r.id;$('inventory').append(li);}
 $('count').textContent=all.length+' named source meshes in this layer. Names are inventory evidence, not anatomy admission.';$('more').hidden=all.length<=shown;}
function chooseLayer(){const m=selected();shown=40;list();$('size').textContent=m.fidelity+' · '+(m.bytes/1048576).toFixed(1)+' MB · '+m.display_triangles.toLocaleString()+' display triangles / '+m.source_triangles.toLocaleString()+' source triangles.';
 if(mode)load();else status('Reference image ready. Select Explore in 3D to load the model.','image');}
function load(){const m=selected();mode=true;$('preview').hidden=true;viewer.hidden=false;status('Loading '+m.label+'…','pending');viewer.setAttribute('src',path(m.file));$('start').disabled=true;$('image').disabled=false;for(const id of ['front','side','reset'])$(id).disabled=true;}
function image(){mode=false;viewer.hidden=true;viewer.removeAttribute('src');$('preview').hidden=false;$('start').disabled=false;$('image').disabled=true;for(const id of ['front','side','reset'])$(id).disabled=true;status('Reference image ready.','image');}
viewer.addEventListener('load',()=>{if(mode&&viewer.getAttribute('src')===selected().file){status(selected().label+' loaded. Drag to orbit; pinch or scroll to zoom.','loaded');for(const id of ['front','side','reset'])$(id).disabled=false;}});
viewer.addEventListener('error',()=>{if(mode){image();status('3D unavailable on this device or connection. Reference image remains available.','error');}});
$('start').addEventListener('click',load);$('image').addEventListener('click',image);
function orbit(theta){viewer.cameraTarget='auto auto auto';viewer.cameraOrbit=theta+'deg 90deg auto';viewer.jumpCameraToGoal();}
$('front').onclick=()=>orbit(0);$('side').onclick=()=>orbit(90);$('reset').onclick=()=>{viewer.cameraOrbit='auto auto auto';viewer.cameraTarget='auto auto auto';viewer.fieldOfView='auto';viewer.jumpCameraToGoal();};
$('dataset').onchange=chooseDataset;$('layer').onchange=chooseLayer;$('search').oninput=()=>{shown=40;list();};$('more').onclick=()=>{shown+=40;list();};
$('theme').onchange=()=>{document.documentElement.dataset.theme=$('theme').value;try{localStorage.setItem('oneirifact-theme',$('theme').value);}catch{}};
try{const t=localStorage.getItem('oneirifact-theme');if(['light','dark','system'].includes(t)){$('theme').value=t;document.documentElement.dataset.theme=t;}}catch{}
let evidenceLoaded=false;
function text(tag,t){const e=document.createElement(tag);e.textContent=t;return e;}
function table(parent,headers,rows){const t=document.createElement('table'),h=document.createElement('thead'),tr=document.createElement('tr');for(const x of headers)tr.append(text('th',x));h.append(tr);t.append(h);const b=document.createElement('tbody');for(const row of rows){const q=document.createElement('tr');for(const x of row)q.append(text('td',String(x)));b.append(q);}t.append(b);parent.append(t);}
async function evidence(){if(evidenceLoaded||!catalog)return;const p=$('evidence-content');p.textContent='Loading qualification evidence…';
 try{const [r,i]=await Promise.all([data(catalog.evidence.registration),data(catalog.evidence.identity)]);p.replaceChildren();p.append(text('h3','Held-out registration — millimetres RMSE'));const plot=document.createElement('img');plot.src=path(catalog.evidence.registration_plot);plot.alt='Bar chart of regional and global bone-centre residuals';p.append(plot);
 const methods=['global_rigid','global_similarity','regional_rigid','regional_similarity'];table(p,['Region','Global rigid','Global scaled','Regional rigid','Regional scaled'],Object.entries(r.summary).map(([k,v])=>[k,...methods.map(m=>v[m].rmse_mm?.toFixed(2)??'N/A')]));
 p.append(text('h3','Individual skeletal and dental identities'));const ss=i.summary.by_sex;const keys=[...new Set([...Object.keys(ss.male),...Object.keys(ss.female)])];table(p,['Status','Male','Female'],keys.map(k=>[k.replaceAll('_',' ').toLowerCase(),ss.male[k]||0,ss.female[k]||0]));
 p.append(text('p',i.summary.ct_mapped_any+' of '+i.summary.ct_total+' female CT source meshes have candidate mappings. No anatomical acceptance.'));
 for(const [label,file] of [['Registration receipt',catalog.evidence.registration],['Identity receipt',catalog.evidence.identity]]){const a=document.createElement('a');a.textContent=label;a.href=path(file);const line=document.createElement('p');line.append(a);p.append(line);}evidenceLoaded=true;
 }catch(e){p.textContent='Evidence could not be loaded. Return to the explorer or try again.';}}
function tab(which){$('explore').hidden=which!=='explore';$('evidence').hidden=which!=='evidence';$('explore-tab').setAttribute('aria-pressed',String(which==='explore'));$('evidence-tab').setAttribute('aria-pressed',String(which==='evidence'));if(which==='evidence')evidence();}
$('explore-tab').onclick=()=>tab('explore');$('evidence-tab').onclick=()=>tab('evidence');
(async()=>{try{catalog=await data('data/catalog.json');if(catalog.schema!=='oneirifact.reference-viewer/v1'||!catalog.datasets?.length)throw Error('Invalid catalog');
 for(const d of catalog.datasets)option($('dataset'),d.id,d.label);$('dataset').disabled=false;chooseDataset();image();}catch(e){status('Reference catalog unavailable. Please return to the project showcase.','error');}})();