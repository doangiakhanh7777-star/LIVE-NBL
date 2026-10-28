import sys, os, ssl, threading, time, subprocess, signal, json, shutil
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
SRC = Path(sys.argv[1]); sys.path.insert(0, str(SRC))
import live_chrome as L, chrome_bridge as B
from session_binding import make_binding, resolve_binding
HERE = Path(__file__).parent; HTML = (HERE/'dash_ai.html').read_bytes()
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(HTML))); self.end_headers(); self.wfile.write(HTML)
srv = ThreadingHTTPServer(('127.0.0.1', 8443), H); ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(HERE/'c.pem', HERE/'k.pem')
srv.socket = ctx.wrap_socket(srv.socket, server_side=True); threading.Thread(target=srv.serve_forever, daemon=True).start()
bridge = B.ChromeBridge(); bridge.start(); print('bridge port', bridge.port)
exe = subprocess.run(['node','-e',"console.log(require('playwright').chromium.executablePath())"],capture_output=True,text=True).stdout.strip()
prof = HERE/'profile'; shutil.rmtree(prof, ignore_errors=True)
procs = []
def launcher(profile, url):
    extra = ['--headless=new','--no-sandbox','--host-resolver-rules=MAP shop.tiktok.com:443 127.0.0.1:8443','--ignore-certificate-errors','--no-proxy-server']
    before = set(p.pid for p in procs)
    L.launch(profile, url, exe=exe, extra=extra)
w = L.Watchdog(prof, lambda: L.DASHBOARD, launcher=launcher, serve=bridge.serve, source=lambda: L.page_source(SRC/'CHROME_NBL_LIVE','4.3.5'), version='4.3.5')
w.START_WAIT = 8
def drain():
    while True:
        try: print('  bridge:', bridge.events.get_nowait())
        except Exception: break
def run_until(cond, secs, busy=False):
    end = time.time()+secs; r=None
    while time.time() < end:
        r = w.step(busy); drain()
        if r.get('actions'): print('  actions', r['actions'])
        if cond(r): return r
        time.sleep(1.5)
    return r
w.start()
r = run_until(lambda r: r['state']=='ok', 60)
snap = bridge.snapshot(); print('STATE', r['state'], 'client', r.get('client'), 'bridge clients', {k:(v.get('account'),v.get('version')) for k,v in snap.items()})
assert r['state']=='ok' and r['client'] in snap, 'not linked'
st = snap[r['client']]; b = make_binding(r['client'], st)
page=[p for p in w.chrome.pages() if L.is_dashboard(p['url'])][0]
print('AI dialog still there?', w.chrome.call(page,'Runtime.evaluate',{'expression':"!!document.getElementById('aiins')",'returnByValue':True})['result']['value'])
cid = bridge.command(r['client'], dict(action='cart_check', module='all'))
for _ in range(20):
    w.step(); c = bridge.snapshot()[r['client']].get('control') or {}
    if c.get('id') == cid and c.get('state') in ('done','failed'): break
    time.sleep(1)
print('CART CHECK', c); assert resolve_binding(b, snap)==r['client']; print('BINDING', b)
# extra tab gets closed
w.chrome.open(L.DASHBOARD); time.sleep(3)
r = run_until(lambda r: r['state']=='ok' and len([p for p in w.chrome.pages() if L.is_dashboard(p['url'])])==1, 40)
print('AFTER EXTRA', r['state'], len([p for p in w.chrome.pages() if L.is_dashboard(p['url'])]))
# Chrome closed -> reopened
w.chrome.quit(); time.sleep(2); print('alive after quit', w.chrome.alive())
r = run_until(lambda r: r['state']=='ok', 70)
snap = bridge.snapshot(); print('AFTER RESTART', r['state'], r.get('client') in snap, 'clients', len(snap))
page=[p for p in w.chrome.pages() if L.is_dashboard(p['url'])][0]
w.chrome.reload(page); t0=time.time(); time.sleep(2)
r = run_until(lambda r: r['state']=='ok' and r.get('client') in bridge.snapshot() and bridge.snapshot()[r['client']].get('account')=='giakhanhdoxe', 60)
print('AFTER PAGE RELOAD', r['state'], round(time.time()-t0), 'same link', r.get('client')==w.link.client_id)
# NBL restarted with the same version: new link, page kept (no reload)
old=w.link; old.close(); w.link=None; w.link_at=0
beat0=w.chrome.page_state(page)
r = run_until(lambda r: r['state']=='ok' and r.get('client') in bridge.snapshot() and r.get('client')!=old.client_id, 60)
print('NBL RESTART same version', r['state'], 'new client', r.get('client')!=old.client_id)
# NBL updated: other version -> page reloaded once with the new code
w.version='4.3.6'; w.source=lambda: L.page_source(SRC/'CHROME_NBL_LIVE','4.3.6'); old=w.link; old.close(); w.link=None; w.link_at=0
r = run_until(lambda r: r['state']=='ok' and r.get('client') in bridge.snapshot() and bridge.snapshot()[r['client']].get('version')=='4.3.6', 90)
print('NBL UPDATE', r['state'], bridge.snapshot().get(r.get('client'),{}).get('version'))
w.chrome.quit(); srv.shutdown(); print('DONE')
