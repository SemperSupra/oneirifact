"""Original static-origin Go/WASM module worker acceptance fixture, no application source."""
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

GO = r'''package main

import (
    "encoding/json"
    "syscall/js"
)

type request struct {
    Value string `json:"value"`
}

func main() {
    fn := js.FuncOf(func(_ js.Value, args []js.Value) any {
        if len(args) != 1 || args[0].Type() != js.TypeString {
            return `{"ok":false}`
        }
        var req request
        if json.Unmarshal([]byte(args[0].String()), &req) != nil || req.Value == "" {
            return `{"ok":false}`
        }
        data, _ := json.Marshal(map[string]any{"ok": true, "value": req.Value})
        return string(data)
    })
    js.Global().Set("fixtureEcho", fn)
    select {}
}
'''
WORKER = """import './wasm_exec.js';
const go = new globalThis.Go();
const asset = await fetch(new URL('./fixture.wasm', import.meta.url), {credentials:'same-origin'});
if (!asset.ok || !asset.headers.get('content-type').includes('application/wasm')) throw Error('WASM asset response');
const {instance} = await WebAssembly.instantiate(await asset.arrayBuffer(), go.importObject);
const running = go.run(instance);
running.then(() => { throw Error('runtime exited'); });
if (typeof globalThis.fixtureEcho !== 'function') throw Error('missing fixture ABI');
self.onmessage = ({data}) => {
  self.postMessage({id:data.id, reply:JSON.parse(globalThis.fixtureEcho(data.raw))});
};
self.postMessage({ready:true});
"""
PAGE = """const report = async result => {
  await fetch('./result', {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(result)});
};
let worker;
try {
  worker = new Worker(new URL('./worker.mjs',import.meta.url),{type:'module'});
  await new Promise((resolve,reject) => {
    let stage = 0;
    const timer = setTimeout(() => reject(Error('worker deadline')),20000);
    worker.onerror = () => reject(Error('module worker error'));
    worker.onmessage = ({data}) => {
      try {
        if (stage === 0 && data.ready === true) {
          stage++; worker.postMessage({id:17,raw:JSON.stringify({value:'Grüße สวัสดี'})});
        } else if (stage === 1 && data.id === 17 && data.reply.ok === true && data.reply.value === 'Grüße สวัสดี') {
          stage++; worker.postMessage({id:18,raw:'{bad'});
        } else if (stage === 2 && data.id === 18 && data.reply.ok === false) {
          clearTimeout(timer); resolve();
        } else { reject(Error('unexpected response')); }
      } catch (err) { reject(err); }
    };
  });
  await report({ok:true,checks:['module worker startup','UTF-8 echo','invalid JSON rejection']});
} catch(err) { await report({ok:false,error:String(err)}); }
finally { worker?.terminate(); }
"""
HTML = '<!doctype html><meta charset="utf-8"><title>Module worker fixture</title><script type="module" src="./page.mjs"></script>'

def main():
    browser = next((shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser") if shutil.which(n)), None)
    if not browser:
        raise SystemExit("Chrome/Chromium required")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        site = root / "project" / "preview"
        site.mkdir(parents=True)
        (root / "main.go").write_text(GO, encoding="utf-8")
        env = dict(os.environ, GOOS="js", GOARCH="wasm", CGO_ENABLED="0", GOTOOLCHAIN="local", GOPROXY="off")
        subprocess.run(["go","build","-trimpath","-o",str(site/"fixture.wasm"),str(root/"main.go")],env=env,check=True,timeout=90)
        goroot = Path(subprocess.check_output(["go","env","GOROOT"],text=True).strip())
        runtime = next(p for p in (goroot/"lib/wasm/wasm_exec.js",goroot/"misc/wasm/wasm_exec.js") if p.is_file())
        shutil.copyfile(runtime,site/"wasm_exec.js")
        for name,data in (("index.html",HTML),("page.mjs",PAGE),("worker.mjs",WORKER)):
            (site/name).write_text(data,encoding="utf-8")
        received, fetched, complete = [], set(), threading.Event()
        class Handler(http.server.SimpleHTTPRequestHandler):
            extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".mjs":"text/javascript", ".wasm":"application/wasm"}
            def log_message(self,*args): pass
            def do_GET(self):
                fetched.add(self.path)
                return super().do_GET()
            def do_POST(self):
                if self.path != "/project/preview/result":
                    self.send_error(404); return
                count = int(self.headers.get("Content-Length","0"))
                if not 0 < count <= 1024:
                    self.send_error(400); return
                received.append(json.loads(self.rfile.read(count)))
                self.send_response(204); self.end_headers(); complete.set()
        with http.server.ThreadingHTTPServer(("127.0.0.1",0),functools.partial(Handler,directory=root)) as server:
            thread = threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/project/preview/"
            with (root/"browser.log").open("wb") as log:
                process = subprocess.Popen([browser,"--headless","--disable-dev-shm-usage","--disable-background-networking","--no-first-run",f"--user-data-dir={root/'profile'}",url],stdout=log,stderr=log)
                try:
                    if not complete.wait(40):
                        raise RuntimeError("browser result timeout")
                    assert received == [{"ok":True,"checks":["module worker startup","UTF-8 echo","invalid JSON rejection"]}],received
                    assert all("/project/preview/"+name in fetched for name in ("page.mjs","worker.mjs","wasm_exec.js","fixture.wasm")),fetched
                    print("REAL HTTP MODULE WORKER GO/WASM PASS: 3 checks")
                finally:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
                    server.shutdown(); thread.join(timeout=5)
if __name__ == "__main__":
    main()
