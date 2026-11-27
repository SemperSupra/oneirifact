#!/usr/bin/env python3
"""Standalone SQLite crash/recovery experiment, NOT a production queue.
Fixed original ray/sphere scene. One host, two worker processes, persistent disk.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import zlib

W, H = 192, 128
SOURCE = hashlib.sha256(b"original-sphere-v1:192x128").hexdigest()

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def connect(path):
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    return db

def claim(db, expected):
    changed = db.execute("UPDATE operation SET epoch=epoch+1,state='running' WHERE id=1 AND epoch=? AND state IN ('queued','running')", (expected,)).rowcount
    require(changed == 1, "claim rejected")
    return expected+1

def publish(db, epoch, data):
    # Both terminal status and artifact bytes reside in the same transaction.
    digest = hashlib.sha256(data).hexdigest()
    return db.execute("UPDATE operation SET state='succeeded',artifact=?,digest=? WHERE id=1 AND epoch=? AND state='running' AND source=?", (data,digest,epoch,SOURCE)).rowcount

def chunk(kind, payload):
    return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",zlib.crc32(kind+payload))

def row(y):
    pixels = bytearray(b"\0")
    for x in range(W):
        dx,dy,dz=(x-W/2)/H,(H/2-y)/H,-1
        norm=math.sqrt(dx*dx+dy*dy+1)
        dx,dy,dz=dx/norm,dy/norm,dz/norm
        b=-3*dz
        disc=b*b-8.2
        if disc>0:
            t=b-math.sqrt(disc)
            light=max(0,(-0.4*t*dx+0.7*t*dy+0.6*(t*dz+3))/math.sqrt(0.8))
            pixels.extend(int(c*(0.23+0.77*light)) for c in (220,135,70))
        else:
            pixels.extend((35,53,81))
    return bytes(pixels)

def image(rows):
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",W,H,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(b"".join(rows)))+chunk(b"IEND",b"")

def worker(path,epoch,crash_probe):
    with connect(path) as db:
        require(db.execute("SELECT epoch,state,source FROM operation WHERE id=1").fetchone()==(epoch,"running",SOURCE),"worker fence")
        rows=[]
        for y in range(H):
            rows.append(row(y))
            if crash_probe and y==15:
                # Deliberate barrier after real partial computation. No partial
                # artifact is published; restart must recompute from source.
                db.execute("UPDATE operation SET witness=16 WHERE id=1 AND epoch=? AND state='running'",(epoch,))
                time.sleep(60)
        require(publish(db,epoch,image(rows))==1,"completion fence")

def experiment(out):
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/"state.db"
        with connect(path) as db:
            db.execute("CREATE TABLE operation(id INTEGER PRIMARY KEY, source TEXT NOT NULL, epoch INTEGER NOT NULL, state TEXT NOT NULL, witness INTEGER NOT NULL, artifact BLOB, digest TEXT)")
            db.execute("INSERT INTO operation VALUES(1,?,0,'queued',0,NULL,NULL)",(SOURCE,))
            first=claim(db,0)
        args=[sys.executable,str(Path(__file__).resolve()),"worker",str(path)]
        child=subprocess.Popen(args+[str(first),"crash"])
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                with connect(path) as db:
                    if db.execute("SELECT witness FROM operation").fetchone()==(16,):
                        break
                require(child.poll() is None,"worker exited before barrier")
                time.sleep(.05)
            else:
                raise RuntimeError("worker barrier timeout")
            child.kill()
            child.wait(timeout=5)
            require(child.returncode!=0,"worker must be killed")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
        with connect(path) as db:
            require(db.execute("SELECT epoch,state,artifact FROM operation").fetchone()==(first,"running",None),"crash state")
            second=claim(db,first)
            require(publish(db,first,b"stale")==0,"stale completion accepted")
        subprocess.run(args+[str(second),"complete"],check=True,timeout=20)
        with connect(path) as db:
            epoch,state,data,digest=db.execute("SELECT epoch,state,artifact,digest FROM operation").fetchone()
            require((epoch,state)==(second,"succeeded"),"recovery terminal state")
            require(publish(db,second,b"duplicate")==0,"duplicate publication")
            require(publish(db,first,b"stale")==0,"stale terminal publication")
            require(db.execute("SELECT artifact,digest FROM operation").fetchone()==(data,digest),"artifact changed")
        expected=image([row(y) for y in range(H)])
        require(data==expected and hashlib.sha256(data).hexdigest()==digest,"recovered image mismatch")
        (out/"recovered.png").write_bytes(data)
        receipt={"schema":"public-worker-loss/v1","source_sha256":SOURCE,"artifact_sha256":digest,"first_epoch":first,"replacement_epoch":second,"computed_before_kill_rows":16,"partial_publication":False,"stale_completion_rejected":True,"duplicate_completion_rejected":True,"reference_bytes_equal":True,"scope":"same-host process loss and SQLite recovery; not runner replacement or product"}
        (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
        print(json.dumps(receipt))

if __name__=="__main__":
    if len(sys.argv)==5 and sys.argv[1]=="worker":
        worker(sys.argv[2],int(sys.argv[3]),sys.argv[4]=="crash")
    elif len(sys.argv)==2:
        experiment(Path(sys.argv[1]))
    else:
        raise SystemExit("usage: worker_loss.py OUTPUT_DIRECTORY")
