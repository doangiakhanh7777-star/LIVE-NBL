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
prof = HERE/'pb'; shutil.rmtree(prof, ignore_errors=True)
def launcher(profile, url):
    L.launch(profile, url, exe=exe, extra=['--headless=new','--no-sandbox','--no-proxy-server','--host-resolver-rules=MAP shop.tiktok.com:443 127.0.0.1:8443','--ignore-certificate-errors'])
w = L.Watchdog(prof, lambda: L.DASHBOARD, launcher=launcher, serve=bridge.serve, source=lambda: L.page_source(SRC/'CHROME_NBL_LIVE','T'), version='T')
w.start()
def run_until(cond, secs):
    end=time.time()+secs; r=None
    while time.time()<end:
        r=w.step()
        if cond(r):return r
        time.sleep(1)
    return r
r = run_until(lambda r: r['state']=='ok', 40)
cid = r['client']; assert cid in bridge.snapshot(), 'not linked: '+r['state']
print('LINKED', bridge.snapshot()[cid].get('account'))
# promo auto-closed?
promo = w.link.eval("!!document.getElementById('promo')")
for _ in range(6):
    w.step(); promo = w.link.eval("!!document.getElementById('promo')")
    if not promo: break
    time.sleep(1)
print('PROMO closed:', not promo)
def bundle(idx, acct, secs=30):
    c = 'bundletest'+str(time.time())
    cmd = dict(action='prepare_bundle', module='all', bundleIndex=idx, keepCart=False, replace=True, preLive=True,
               expectedAccount=acct, stopModules=True)
    rid = bridge.command(cid, cmd)
    end=time.time()+secs
    while time.time()<end:
        w.step(); st=bridge.snapshot().get(cid,{}).get('control') or {}
        if st.get('id')==rid and st.get('state') in ('done','failed'): return st
        time.sleep(1)
    return {'state':'timeout'}
r1 = bundle(1, 'giakhanhdoxe'); print('BUNDLE idx1:', json.dumps(r1, ensure_ascii=False))
r2 = bundle(2, 'giakhanhdoxe'); print('BUNDLE idx2:', json.dumps(r2, ensure_ascii=False))
r3 = bundle(1, 'ngườikhác');   print('WRONG acct:', json.dumps(r3, ensure_ascii=False))
w.chrome.quit(); srv.shutdown()
ok = r1.get('state')=='done' and str(r1.get('added'))=='2' and r2.get('state')=='done' and str(r2.get('added'))=='3' and r3.get('state')=='failed' and 'khác nick' in r3.get('error','')
print('RESULT', 'PASS' if (ok and not promo) else 'FAIL')
