import sys, time, subprocess, shutil, json, urllib.request
from pathlib import Path
SRC=Path(sys.argv[1]); sys.path.insert(0,str(SRC))
import studio_cdp as C
HERE=Path(__file__).parent
def chromium():
    import shutil as sh
    for n in ('chromium','chromium-browser','google-chrome'):
        if sh.which(n): return sh.which(n)
    return subprocess.run(['node','-e',"console.log(require('playwright').chromium.executablePath())"],capture_output=True,text=True).stdout.strip()
PORT=9366
main=(HERE/'html/main/index.html').as_uri()
proc=subprocess.Popen([chromium(),'--headless=new','--no-sandbox','--remote-debugging-port=%d'%PORT,'--remote-allow-origins=http://127.0.0.1:%d'%PORT,main],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
st=C.Studio(PORT)
for _ in range(40):
    time.sleep(.25)
    if st.alive() and st.page('/html/main/'): break
# open the floating chat tab
floaturl=(HERE/'html/liveChatFloat/index.html').as_uri()
req=urllib.request.Request('http://127.0.0.1:%d/json/new?%s'%(PORT,urllib.request.quote(floaturl,safe=':/')),method='PUT');urllib.request.urlopen(req,timeout=5)
time.sleep(1)
print('float present before:', bool(st.page('/html/liveChatFloat/')))
# chat_read should dock first, then read the comment
rows=st.chat_read()
print('comments read:', [(r['user'],r['text']) for r in rows])
time.sleep(1)
print('float present after dock:', bool(st.page('/html/liveChatFloat/')))
proc.kill()
