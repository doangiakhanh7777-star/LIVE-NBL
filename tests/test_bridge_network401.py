"""Real loopback WebSocket integration; no Chrome or TikTok session involved."""
import json,sys,threading,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from chrome_bridge import ChromeBridge,PROTOCOL
from websockets.sync.client import connect

class BridgeNetworkTests(unittest.TestCase):
 def test_real_socket_confirms_stop(self):
  bridge=ChromeBridge(port=0);bridge.start();ready=threading.Event();stopped=threading.Event();errors=[]
  def peer():
   try:
    with connect('ws://127.0.0.1:'+str(bridge.port),origin='chrome-extension://nbl-test',open_timeout=3) as ws:
     ws.send(json.dumps(dict(token=bridge.token,protocol=PROTOCOL,tab=1,instance='a'*32)))
     while True:
      tick=json.loads(ws.recv(timeout=5));acks=[];running=True
      for command in tick['commands']:
       if command['action']=='stop':running=False;stopped.set();acks.append(dict(id=command['id'],error=''))
      ws.send(json.dumps(dict(account='Nick',accountVerified=True,acks=acks,modules=dict(pin=dict(running=running),reply=dict(running=running)))))
      ready.set()
   except Exception as error:
    if not bridge.closed:errors.append(str(error))
  t=threading.Thread(target=peer,daemon=True);t.start()
  try:
   self.assertTrue(ready.wait(4));bridge.close(wait=True);t.join(3)
   self.assertTrue(stopped.is_set());self.assertFalse(bridge.pending_commands);self.assertFalse(errors)
  finally:bridge.close(wait=True)
 def test_protocol_rejects_old_extension(self):
  bridge=ChromeBridge(port=0);bridge.start()
  try:
   with connect('ws://127.0.0.1:'+str(bridge.port),origin='chrome-extension://nbl-test',open_timeout=3) as ws:
    ws.send(json.dumps(dict(token=bridge.token,protocol=40,tab=1,instance='a'*32)))
    with self.assertRaises(Exception):ws.recv(timeout=3)
   self.assertFalse(bridge.clients)
  finally:bridge.close(wait=True)

if __name__=='__main__':unittest.main()
