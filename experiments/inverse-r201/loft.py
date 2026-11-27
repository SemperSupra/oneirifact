"""Section-based star-shaped loft candidate from training surface points."""
import numpy as np
from scipy.spatial import cKDTree

def loft(v,train,nlevels=33,nangles=48):
    axis=int(np.argmax(np.ptp(v,axis=0)));rad=[i for i in range(3) if i!=axis]
    lo,hi=v[:,axis].min(),v[:,axis].max();levels=np.linspace(lo,hi,nlevels)
    theta=np.arange(nangles)*2*np.pi/nangles;vs=[];centers=[];radii=[]
    dy=(hi-lo)/(nlevels-1)
    for z in levels:
        slice_=train[np.abs(train[:,axis]-z)<=dy*.65][:,rad]
        if len(slice_)<30:slice_=train[np.argsort(abs(train[:,axis]-z))[:60]][:,rad]
        c=(np.quantile(slice_,.02,axis=0)+np.quantile(slice_,.98,axis=0))/2
        xy=slice_-c;angle=np.arctan2(xy[:,1],xy[:,0]);r=np.linalg.norm(xy,axis=1)
        # Local circular angular neighborhoods. Quantiles estimate the outer
        # surface, not internal cavities; candidate must be validated separately.
        rr=[]
        for t in theta:
            dist=np.abs(np.angle(np.exp(1j*(angle-t))));idx=np.argsort(dist)[:max(6,min(30,len(dist)//20))];rr.append(float(np.quantile(r[idx],.65)))
        ring=np.zeros((nangles,3));ring[:,axis]=z;ring[:,rad[0]]=c[0]+np.array(rr)*np.cos(theta);ring[:,rad[1]]=c[1]+np.array(rr)*np.sin(theta);vs.append(ring);centers.append(c.tolist());radii.append(rr)
    vs=np.concatenate(vs);f=[]
    for j in range(nlevels-1):
        for i in range(nangles):
            k=(i+1)%nangles;a=j*nangles+i;b=j*nangles+k;c=(j+1)*nangles+k;d=(j+1)*nangles+i;f.extend(((a,b,c),(a,c,d)))
    # Close ends with separate center vertices; no topology reconstruction claim.
    caps=np.zeros((2,3));caps[:,axis]=[lo,hi];caps[:,rad]=[centers[0],centers[-1]];vs=np.concatenate((vs,caps))
    for i in range(nangles):
        k=(i+1)%nangles;f.extend(((len(vs)-2,k,i),(len(vs)-1,(nlevels-1)*nangles+i,(nlevels-1)*nangles+k)))
    return vs,np.array(f),{'axis':axis,'levels':levels.tolist(),'centers':centers,'radii':radii,'angular_samples':nangles}
