"""Use a real local browser to navigate the static site at a project base path."""
import functools
import http.server
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    browser = next((p for name in ("google-chrome", "chromium", "chromium-browser")
                    if (p := shutil.which(name))), None)
    if browser is None:
        raise SystemExit("A supported Chrome or Chromium executable is required")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shutil.copytree(ROOT / "site", root / "oneirifact")
        handler = functools.partial(QuietHandler, directory=root)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/oneirifact/"
                with urllib.request.urlopen(url, timeout=10) as response:
                    assert response.status == 200
                    assert response.read() == (ROOT / "site/index.html").read_bytes()
                result = subprocess.run(
                    [browser, "--headless", "--disable-dev-shm-usage",
                     "--disable-background-networking", "--no-first-run",
                     f"--user-data-dir={root / 'browser-profile'}", "--dump-dom", url],
                    capture_output=True, text=True, timeout=45, check=True,
                )
                assert "<h1>Oneirifact</h1>" in result.stdout
                assert "Browser preview in preparation" in result.stdout
                assert "Gallery — procedural design studies" in result.stdout
                if (ROOT / "site/gallery").exists():
                    # A test-only page forces all actual PNGs to decode in Chromium.
                    names = ("day", "night", "plan", "tall")
                    probe = root / "oneirifact" / "decode-probe.html"
                    probe.write_text('<!doctype html><meta charset="utf-8"><p id="result">PENDING</p>' +
                        ''.join(f'<img src="gallery/pavilion-{n}.png">' for n in names) +
                        '<script>Promise.all([...document.images].map(async i=>{await i.decode();if(i.naturalWidth!==720||i.naturalHeight!==480)throw Error("dimensions")})).then(()=>document.getElementById("result").textContent="DECODE_PASS").catch(()=>document.getElementById("result").textContent="DECODE_FAIL")</script>')
                    decoded = subprocess.run([browser, "--headless", "--disable-dev-shm-usage", "--disable-background-networking", "--no-first-run", "--virtual-time-budget=5000", f"--user-data-dir={root / 'decode-profile'}", "--dump-dom", url+"decode-probe.html"], capture_output=True, text=True, timeout=45, check=True)
                    assert '<p id="result">DECODE_PASS</p>' in decoded.stdout, decoded.stdout[-1000:]
                    print("All four real gallery PNGs decoded in Chromium")
                print("Public site HTTP and real browser navigation PASS")
            finally:
                server.shutdown()
                t.join(timeout=5)


if __name__ == "__main__":
    main()
