"""Readable projections of actual source triangles and evaluated morphology."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from geometry import exact_quotient

FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def triangles(draw,v,f,rect,bounds,color,boundaries=False):
    x,y,w,h=rect;lo,hi=np.array(bounds);scale=min(w/max(hi[0]-lo[0],1e-8),h/max(hi[1]-lo[1],1e-8))*.88
    xy=np.column_stack([x+w/2+(v[:,0]-(lo[0]+hi[0])/2)*scale,y+h*.94-(v[:,1]-lo[1])*scale])
    normals=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
    length=np.linalg.norm(normals,axis=1);shade=.55+.45*np.divide(abs(normals[:,2]),length,out=np.zeros(len(f)),where=length>0)
    for i in np.argsort(v[f,2].mean(1)):
        draw.polygon([tuple(p) for p in xy[f[i]]],fill=tuple(int(c*shade[i]) for c in color))
    if boundaries:
        edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
        edges,count=np.unique(edges,axis=0,return_counts=True)
        for edge in edges[count==1]:draw.line([tuple(p) for p in xy[edge]],fill='#ff8680',width=2)


def render(folder,morph):
    report=json.loads((folder/'audit.json').read_text());data=np.load(folder/'original-selected-surfaces.npz');sex=report['sex'];font=ImageFont.truetype(FONT,22);small=ImageFont.truetype(FONT,17)
    if sex=='male':
        selected=next(r for r in report['organs'] if r['id']=='FJ3145');key=selected['array_key'];v=data[key+'_vertices'];f=data[key+'_faces'];label='Male left kidney / exact source FJ3145';metric=selected['geometry'];left='Original source indices';right='Exact coordinate index quotient'
    else:
        selected=report['derived_same_source_compartments'][0];key=selected['array_key'];v=data[key+'_vertices'];f=data[key+'_faces'];label='Female spleen / five exact same-parent source patches';metric=selected['geometry'];left='Five original patches, original indices';right='Exact same-source assembled quotient'
    q,g,*_=exact_quotient(v,f);bounds=[v.min(0),v.max(0)]
    im=Image.new('RGB',(1280,810),'#13202b');draw=ImageDraw.Draw(im)
    draw.text((24,18),label,font=font,fill='white');draw.text((24,52),'All ordered triangle corners retained; no filling, fitting or physical density',font=small,fill='#bdd0de')
    for i,(a,b,title) in enumerate([(v,f,left),(q,g,right)]):
        draw.text((24+i*640,100),title,font=font,fill='white');triangles(draw,a,b,(i*640+30,150,580,470),bounds,(113,190,177),True)
    b=metric['before'];a=metric['exact_quotient'];p=metric['geometric_properties']
    draw.text((24,655),f"Boundary edges: {b['boundary_edges']} -> {a['boundary_edges']} | triangle count retained: {len(f):,}",font=font,fill='white')
    draw.text((24,690),f"Conditional geometric volume: {p['volume_m3']*1e6:.6f} mL | inertia integral measured in m^5",font=small,fill='#bdd0de')
    draw.text((24,723),'Density / physical mass / attachments / morphology registration: UNKNOWN or MISSING',font=small,fill='#ffcc83')
    draw.text((24,755),'Self-intersection and tissue-domain semantics remain unqualified. This is a geometry result.',font=small,fill='#ffcc83')
    im.save(folder/'source-geometry-before-after.png')
    names=['baseline','common-height_m-high','common-mass_morph-high','common-age_years-high','regional-abdomen-high','common-spine_flexion_deg-high']
    labels=['Baseline','Stature 2.0 m','Mass-shape 1','Age-design 90','Abdomen 1','Spine flexion 20 deg']
    rows=json.loads((morph/'morphology-audit.json').read_text())['cases'];faces=np.fromfile(morph/'faces.u32',dtype='<u4').reshape(-1,3)
    im=Image.new('RGB',(1800,1120),'#13202b');draw=ImageDraw.Draw(im);draw.text((20,16),sex.title()+' / actual shipped exterior changes; internal reference remains separate',font=font,fill='white')
    draw.text((20,51),'Top: actual evaluated exterior. Bottom: unchanged source-organ reference in its own frame; no anatomical overlay.',font=small,fill='#bdd0de')
    # One scale for all exterior panels so stature differences remain visible.
    body_bounds=[[-.45,0,-.4],[.45,2,.4]]
    source_v=np.concatenate([data[r['array_key']+'_vertices'] for r in report['organs']]);source_bounds=[source_v.min(0),source_v.max(0)]
    for i,(name,label) in enumerate(zip(names,labels)):
        row=next(r for r in rows if r['id']==sex+'/'+name);v=np.fromfile(morph/row['position_file'],dtype='<f4').reshape(-1,3)
        draw.text((i*300+14,96),label,font=small,fill='white');triangles(draw,v,faces,(i*300,125,300,650),body_bounds,(147,190,202))
        for j,r in enumerate(report['organs']):
            k=r['array_key'];triangles(draw,data[k+'_vertices'],data[k+'_faces'],(i*300+35,825,230,190),source_bounds,[(205,130,110),(114,181,167),(197,170,100),(145,137,202)][j%4])
        draw.text((i*300+18,793),'Source reference: unchanged',font=small,fill='#ffcc83')
    draw.text((20,1048),'Real organ propagation, mass/inertia response, attachments and secondary motion: NOT IMPLEMENTED',font=font,fill='#ffcc83')
    draw.text((20,1082),'The mass-shape slider is dimensionless; no kilograms, tissue density or physical coupling are inferred.',font=small,fill='#bdd0de')
    im.save(folder/'actual-morphology-organ-response.png')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('morphology',type=Path);a=p.parse_args();render(a.folder,a.morphology)
