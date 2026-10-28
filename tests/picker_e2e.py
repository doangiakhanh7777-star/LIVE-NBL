import sys, ssl, threading, time, subprocess, shutil, json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
SRC = Path(sys.argv[1]); sys.path.insert(0, str(SRC))
import live_chrome as L, chrome_bridge as B
HERE = Path(__file__).parent; HTML = (HERE/'dash_bundle.html').read_bytes()
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(HTML))); self.end_headers(); self.wfile.write(HTML)
srv = ThreadingHTTPServer(('127.0.0.1', 8443), H); ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(HERE/'c.pem', HERE/'k.pem')
srv.socket = ctx.wrap_socket(srv.socket, server_side=True); threading.Thread(target=srv.serve_forever, daemon=True).start()
bridge = B.ChromeBridge(); bridge.start()
exe = subprocess.run(['node','-e',"console.log(require('playwright').chromium.executablePath())"],capture_output=True,text=True).stdout.strip()
prof = HERE/'pp'; shutil.rmtree(prof, ignore_errors=True)
def launcher(profile, url):
    L.launch(profile, url, exe=exe, extra=['--headless=new','--no-sandbox','--no-proxy-server','--host-resolver-rules=MAP shop.tiktok.com:443 127.0.0.1:8443','--ignore-certificate-errors'])
w = L.Watchdog(prof, lambda: L.DASHBOARD, launcher=launcher, serve=bridge.serve, source=lambda: L.page_source(SRC/'CHROME_NBL_LIVE','T'), version='T')
w.start()
def wait(cond, secs):
    end=time.time()+secs
    while time.time()<end:
        w.step()
        if cond(): return True
        time.sleep(1)
    return False
assert wait(lambda: w.link and w.link.ctx and w.link.eval('typeof __nblCall==="function"&&!!globalThis.__nblStarted'), 40), 'not ready'
ev = w.link.eval
# launcher button present and panel hidden by default
print('launcher exists:', ev("!!document.querySelector('[data-nbl-launch]')"))
print('panel hidden by default:', ev("getComputedStyle(document.getElementById('nbl-live-extension')).display==='none'"))
# click launcher -> panel shows
ev("document.querySelector('[data-nbl-launch]').click()")
print('panel shown after click:', ev("document.getElementById('nbl-live-extension').style.display!=='none'"))
print('header version:', ev("document.getElementById('nbl-live-extension').shadowRoot.querySelector('h3').textContent.trim()"))
# simulate picking bundleTab position: set the field value directly via the shadow input and fire change (same as commitPick save path)
pick = """(()=>{const ui=document.getElementById('nbl-live-extension').shadowRoot;
 const set=(id,val)=>{const el=ui.getElementById(id);el.value=val;el.dispatchEvent(new Event('change',{bubbles:true}));};
 // pick the 2nd tab (Bộ sản phẩm TRỰC TIẾP) by a precise selector, and the drawer confirm
 set('bundleTab','div[role=tab]:nth-of-type(2)');
 set('account','#acct');
 return [ui.getElementById('bundleTab').value, ui.getElementById('account').value];})()"""
print('picked:', ev(pick))
# give it a moment to persist to the shim localStorage
time.sleep(1); w.step()
print('persisted bundleTab:', ev("JSON.parse(localStorage.getItem('nbl:nblSharedSetup')||'{}').bundleTab"))
# now run a bundle add; it must use the picked tab (still succeeds)
cid=[c for c in bridge.snapshot()][0]
rid=bridge.command(cid, dict(action='prepare_bundle',module='all',bundleIndex=1,keepCart=False,replace=True,preLive=True,expectedAccount='giakhanhdoxe',stopModules=True))
end=time.time()+40; st={}
while time.time()<end:
    w.step(); st=bridge.snapshot().get(cid,{}).get('control') or {}
    if st.get('id')==rid and st.get('state') in ('done','failed'): break
    time.sleep(1)
print('bundle with picked tab:', json.dumps(st,ensure_ascii=False))
# reload the page -> picked positions must survive (stored in Chrome LIVE profile)
page=[p for p in w.chrome.pages() if L.is_dashboard(p['url'])][0]
w.chrome.reload(page); w.link=None; w.link_at=0; time.sleep(2)
assert wait(lambda: w.link and w.link.ctx and w.link.eval('!!globalThis.__nblStarted'), 40), 'not ready after reload'
restored = w.link.eval("document.getElementById('nbl-live-extension').shadowRoot.getElementById('bundleTab').value")
print('bundleTab restored after reload:', restored)
w.chrome.quit(); srv.shutdown()
