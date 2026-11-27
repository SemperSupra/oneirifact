from pathlib import Path
import sys,json,zipfile
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from fit import read_glb

def obj(path):
    vs=[];fs=[]
    for l in path.read_text().splitlines():
        if l.startswith('v '):vs.append([float(x) for x in l.split()[1:]])
        if l.startswith('f '):fs.append([int(x)-1 for x in l.split()[1:]])
    return np.array(vs),np.array(fs)

def drawmesh(im,rect,v,f,c,scale):
    x,y,w,h=rect; angles=np.radians([22,20]);a,b=angles
    R=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])@np.array([[1,0,0],[0,np.cos(b),-np.sin(b)],[0,np.sin(b),np.cos(b)]])
    p=(v-c)@R;xy=np.column_stack((x+w/2+p[:,0]*scale,y+h/2-p[:,1]*scale));t=p[f];norm=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);lens=np.linalg.norm(norm,axis=1);norm=norm/np.maximum(lens[:,None],1e-12);shade=.35+.65*np.abs(norm@np.array([.3,.4,.866]));d=ImageDraw.Draw(im)
    for i in np.argsort(t[:,:,2].mean(1)):
        d.polygon([tuple(q) for q in xy[f[i]]],fill=tuple(int(k*shade[i]) for k in (160,207,217)))

def main(root,out):
    W,H=1200,1000;im=Image.new('RGB',(W,H),'#18212c');d=ImageDraw.Draw(im);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',22);bold=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',24);small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
    d.text((25,20),'R201 | Original mesh vs fitted section loft',font=bold,fill='white');d.text((25,54),'Geometry-only orthographic diagnostic • same scale per row • not texture or topology equivalence',font=small,fill='#b9c6d6')
    d.text((360,90),'Source mesh',font=bold,fill='white');d.text((825,90),'Candidate',font=bold,fill='white')
    for i,(name,aid) in enumerate([('Avocado',15229781019),('WaterBottle',15228334677),('Lantern',15228548803)]):
        with zipfile.ZipFile(root/f'github-actions-artifact-{aid}.zip') as z:parts=read_glb(z.read('normalized.glb'))
        v=np.concatenate([p[0] for p in parts.values()]);f=[];base=0
        for pv,pf in parts.values():f.extend(pf+base);base+=len(pv)
        f=np.array(f);cv,cf=obj(out/(name+'-candidate.obj'));c=(v.max(0)+v.min(0))/2;s=220/np.ptp(v,axis=0).max();y=135+i*280
        d.rectangle((20,y,1180,y+265),outline='#344454');d.text((35,y+15),name,font=bold,fill='white');d.text((35,y+55),'Source retained',font=small,fill='#f2bc7c');drawmesh(im,(230,y+5,430,250),v,f,c,s);drawmesh(im,(675,y+5,430,250),cv,cf,c,s)
    im.save(out/'geometry-comparison.png')
if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
