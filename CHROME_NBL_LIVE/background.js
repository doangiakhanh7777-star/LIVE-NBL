'use strict';
// 4.0: protocol 402; tries ports 17869-17871 so a busy port does not break pairing.
const PROTOCOL=402,PORTS=[17869,17870,17871];
const connections=new Map(),connecting=new Set();let storageTail=Promise.resolve();const storePair=work=>{storageTail=storageTail.catch(()=>{}).then(work);return storageTail;};
let instancePromise;
// 4.1.1: QR login removed; only TikTok Shop pages can be paired.
function officialUrl(value){try{const u=new URL(value);return u.protocol==='https:'&&u.hostname==='shop.tiktok.com';}catch(_){return false;}}
function dashboardUrl(value){try{const u=new URL(value);return u.origin==='https://shop.tiktok.com'&&u.pathname==='/streamer/live/product/dashboard';}catch(_){return false;}}
function browserInstance(){
 if(!instancePromise)instancePromise=(async()=>{
  const {nblInstance}=await chrome.storage.local.get('nblInstance');
  if(typeof nblInstance==='string'&&/^[a-f0-9]{32}$/.test(nblInstance))return nblInstance;
  const value=crypto.randomUUID().replaceAll('-','');await chrome.storage.local.set({nblInstance:value});return value;
 })();
 return instancePromise;
}
// Leave enough time for the app's eight-second reply deadline.
function contentMessage(tabId,message,timeoutMs=4000){
 let timer;
 const timeout=new Promise((resolve,reject)=>{timer=setTimeout(()=>reject(Error('Tab LIVE không phản hồi.')),timeoutMs);});
 return Promise.race([Promise.resolve().then(()=>chrome.tabs.sendMessage(tabId,message)),timeout]).finally(()=>clearTimeout(timer));
}
async function disconnect(tabId,reason='Mất kết nối app'){
 const s=connections.get(tabId);if(!s)return;connections.delete(tabId);s.closed=true;clearTimeout(s.retry);try{s.socket?.close();}catch(e){}
 try{await contentMessage(tabId,{type:'disconnect',reason,terminal:true});}catch(e){}
}
async function connect(tabId,token){
 if(connecting.has(tabId))throw Error('Đang ghép đôi tab; thử lại sau vài giây.');
 connecting.add(tabId);try{
 if(!Number.isInteger(tabId)||! /^[a-f0-9]{32}$/.test(token))throw Error('Mã ghép đôi phải gồm 32 ký tự.');
 const tab=await chrome.tabs.get(tabId);if(!officialUrl(tab.url))throw Error('Chọn tab TikTok Shop hoặc trang đăng nhập TikTok.');
 const instance=await browserInstance();
 await disconnect(tabId);await chrome.tabs.update(tabId,{autoDiscardable:false});
 const state={tabId,token,instance,closed:false,socket:null,retry:null,port:0,opened:false};connections.set(tabId,state);open(state);
 }finally{connecting.delete(tabId);}
}
function open(state){
 if(state.closed)return;
 const socket=new WebSocket('ws://127.0.0.1:'+PORTS[state.port%PORTS.length]);state.socket=socket;let opened=false;
 const current=()=>!state.closed&&connections.get(state.tabId)===state&&state.socket===socket;
 socket.onopen=()=>{opened=true;if(current())socket.send(JSON.stringify({protocol:PROTOCOL,token:state.token,tab:state.tabId,instance:state.instance}));};
 socket.onmessage=async event=>{
  if(!current())return;
  let message;try{message=JSON.parse(event.data);}catch(e){return;}
  if(!message||message.type!=='tick')return;
  const commands=message.commands||[];let response={account:'Chưa đăng nhập',accountVerified:false,modules:{},acks:[],config:{}};
  try{
   const tab=await chrome.tabs.get(state.tabId);
   if(dashboardUrl(tab.url)){
    let version;try{version=await contentMessage(state.tabId,{type:'version'},1000);}catch(e){}
    if(version?.protocol===PROTOCOL)response=await contentMessage(state.tabId,message)||response;
    else response.acks=commands.map(c=>({id:c.id,error:'Tải lại trang LIVE để dùng tiện ích 4.1.16.'}));
   }else response.acks=commands.map(c=>({id:c.id,error:'Chưa mở bảng LIVE của nick này.'}));
  }catch(e){
   // 4.1.1: a slow or reloading LIVE tab used to close the socket here ("Tab Chrome
   // ngắt kết nối: received 1005") and every pending command was dropped. Keep the
   // connection; commands of this tick are NOT acknowledged, so the app never
   // records a success that did not happen and they simply expire.
   response={account:'Đang đọc trang',accountVerified:false,modules:{},acks:[],config:{}};
  }
  try{if(current()&&socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify(response));}catch(e){}
 };
 socket.onclose=event=>{
  if(!current())return;
  if(event.code===1008){state.closed=true;connections.delete(state.tabId);}
  else{if(!opened)state.port++;state.retry=setTimeout(()=>open(state),opened?5000:1500);}
  // Reconnect scheduling must never depend on a frozen tab acknowledging stop.
  void contentMessage(state.tabId,{type:'disconnect'}).catch(()=>{});
 };
 socket.onerror=()=>{};
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
 if(message.type==='pair'){
  connect(message.tabId,message.token).then(async()=>{await storePair(async()=>{const {nblPairs={}}=await chrome.storage.local.get('nblPairs');nblPairs[String(message.tabId)]={tabId:message.tabId,token:message.token};const {nblSkip=[]}=await chrome.storage.local.get('nblSkip');await chrome.storage.local.set({nblPairs,nblToken:message.token,nblSkip:nblSkip.filter(id=>id!==message.tabId)});});respond({ok:true});}).catch(e=>respond({ok:false,error:e.message}));return true;
 }
 if(message.type==='status'){respond({tabs:[...connections.values()].map(s=>({tabId:s.tabId,connected:s.socket?.readyState===WebSocket.OPEN}))});return;}
 if(message.type==='unpair'){disconnect(message.tabId).then(async()=>{await storePair(async()=>{const {nblPairs={}}=await chrome.storage.local.get('nblPairs');delete nblPairs[String(message.tabId)];const {nblSkip=[]}=await chrome.storage.local.get('nblSkip');await chrome.storage.local.set({nblPairs,nblSkip:[...new Set([...nblSkip,message.tabId])].slice(-50)});await chrome.storage.local.remove('nblPair');});respond({ok:true});});return true;}
});
chrome.tabs.onRemoved.addListener(id=>void disconnect(id));
chrome.tabs.onUpdated.addListener((id,change)=>{if(change.url&&!officialUrl(change.url))void disconnect(id);});
// Reconnect paired tabs. Reload/new app connection never starts automation itself.
// 4.0.3: a pairing used to be tied to one tab ID. Restarting Chrome or reopening the
// LIVE tab gives a new ID, so the tab silently stayed unpaired ("Chrome: chưa kết
// nối") until the code was pasted again. The code is now remembered and any open
// LIVE dashboard tab is paired with it automatically.
const DASHBOARD='https://shop.tiktok.com/streamer/live/product/dashboard*';
let restoring=null;
function restore(){if(!restoring)restoring=restoreNow().finally(()=>{restoring=null;});return restoring;}
async function restoreNow(){
 const {nblPairs={},nblPair,nblToken,nblSkip=[]}=await chrome.storage.local.get(['nblPairs','nblPair','nblToken','nblSkip']);
 const pairs={...nblPairs};if(nblPair&&!pairs[String(nblPair.tabId)])pairs[String(nblPair.tabId)]=nblPair;
 const valid=t=>typeof t==='string'&&/^[a-f0-9]{32}$/.test(t);
 let token=valid(nblToken)?nblToken:'';const gone=[],added={};
 for(const [key,pair] of Object.entries(pairs)){
  if(!token&&valid(pair?.token))token=pair.token;
  let alive=false;try{const tab=await chrome.tabs.get(pair.tabId);alive=officialUrl(tab.url);}catch(e){}
  if(!alive){gone.push(key);continue;}
  if(!connections.has(pair.tabId)&&!connecting.has(pair.tabId))try{await connect(pair.tabId,pair.token);}catch(e){}
 }
 if(token){
  let tabs=[];try{tabs=await chrome.tabs.query({url:DASHBOARD});}catch(e){}
  for(const tab of tabs){
   // A tab the user disconnected with "Ngắt kết nối" is never re-paired automatically.
   if(nblSkip.includes(tab.id)||connections.has(tab.id)||connecting.has(tab.id)||pairs[String(tab.id)]&&!gone.includes(String(tab.id)))continue;
   try{await connect(tab.id,token);added[String(tab.id)]={tabId:tab.id,token};}catch(e){}
  }
 }
 if(gone.length||Object.keys(added).length||(token&&token!==nblToken))await storePair(async()=>{
  const {nblPairs:current={}}=await chrome.storage.local.get('nblPairs');
  for(const key of gone)delete current[key];Object.assign(current,added);
  await chrome.storage.local.set({nblPairs:current,...(token?{nblToken:token}:{})});
 });
}
chrome.alarms.create('nbl-reconnect',{periodInMinutes:.5});
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='nbl-reconnect')void restore();});
chrome.tabs.onUpdated.addListener((id,change,tab)=>{if(change.status==='complete'&&tab&&dashboardUrl(tab.url))void restore();});
chrome.runtime.onStartup?.addListener(()=>void restore());
void restore();
