'use strict';
// 4.0: protocol 40; tries ports 17869-17871 so a busy port does not break pairing.
const PROTOCOL=402,PORTS=[17869,17870,17871];
const connections=new Map(),connecting=new Set();let storageTail=Promise.resolve();const storePair=work=>{storageTail=storageTail.catch(()=>{}).then(work);return storageTail;};
let instancePromise;
function officialUrl(value){try{const u=new URL(value);return u.protocol==='https:'&&['shop.tiktok.com','seller-vn.tiktok.com','www.tiktok.com'].includes(u.hostname);}catch(_){return false;}}
function dashboardUrl(value){try{const u=new URL(value);return u.origin==='https://shop.tiktok.com'&&u.pathname==='/streamer/live/product/dashboard';}catch(_){return false;}}
async function loginCommand(state,command){
 if(command.expectedAccount&&state.lastAccount&&state.lastAccount!==command.expectedAccount)throw Error('Nick khác với nick đang chọn trong app.');
 const tab=await chrome.tabs.get(state.tabId);if(!officialUrl(tab.url))throw Error('Trang đăng nhập không thuộc TikTok.');
 if(command.operation==='close'){state.loginActive=false;state.shopLogin={state:'idle'};return;}
 if(command.operation==='show_browser'){await chrome.tabs.update(state.tabId,{active:true});if(Number.isInteger(tab.windowId))await chrome.windows.update(tab.windowId,{focused:true});return;}
 if(!['open','refresh'].includes(command.operation))throw Error('Thao tác đăng nhập không hợp lệ.');
 state.loginActive=true;state.loginRequestId=command.id;state.shopLogin={state:'waiting',requestId:command.id,observedAt:Date.now()/1000};
 await contentMessage(state.tabId,{type:command.operation==='refresh'?'nbl-shop-login-refresh':'nbl-shop-login-choose-qr'},1000).catch(()=>{});
}
async function loginSnapshot(state,account,pageUrl,accountVerified=false){
 if(!state.loginActive)return state.shopLogin||{state:'idle'};
 if(accountVerified&&account&&!['Chưa đăng nhập','Chưa chọn tài khoản','Chưa hiệu chỉnh','Không đọc được trang','Đang đọc trang'].includes(account)){state.lastAccount=account;return state.shopLogin={state:'authenticated',account,pageUrl:new URL(pageUrl).origin+new URL(pageUrl).pathname,requestId:state.loginRequestId,observedAt:Date.now()/1000};}
 try{const result=await contentMessage(state.tabId,{type:'nbl-shop-login-capture'},2000);state.shopLogin=result&&typeof result==='object'?result:{state:'unavailable',error:'Chưa đọc được mã QR. Bấm Mở trang trên Chrome.'};}catch(e){state.shopLogin={state:'waiting',error:'Đang chờ trang đăng nhập; bấm Mở trang trên Chrome nếu cần.',observedAt:Date.now()/1000};}state.shopLogin.requestId=state.loginRequestId;return state.shopLogin;
}

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
  try{const message=JSON.parse(event.data);if(message.type!=='tick')return;
   const commands=message.commands||[],loginCommands=commands.filter(c=>c.action==='shop_login'),ordinary=commands.filter(c=>c.action!=='shop_login');const loginAcks=[];
   for(const command of loginCommands){if(command.deadline*1000<Date.now()){loginAcks.push({id:command.id,error:'Lệnh đăng nhập đã quá hạn'});continue;}try{await loginCommand(state,command);loginAcks.push({id:command.id,error:''});}catch(e){state.shopLogin={state:'unavailable',error:e.message};loginAcks.push({id:command.id,error:e.message});}}
   const tab=await chrome.tabs.get(state.tabId);let response={account:'Chưa đăng nhập',accountVerified:false,modules:{},acks:[],config:{}};
   if(dashboardUrl(tab.url)){
    let version;try{version=await contentMessage(state.tabId,{type:'version'},1000);}catch(e){}
    if(version?.protocol===PROTOCOL)response=await contentMessage(state.tabId,{...message,commands:ordinary})||response;
    else response.acks=ordinary.map(c=>({id:c.id,error:'Tải lại trang LIVE để dùng tiện ích 4.0.2.'}));
   }else response.acks=ordinary.map(c=>({id:c.id,error:'Chưa mở bảng LIVE của nick này.'}));
   response.acks=[...(response.acks||[]),...loginAcks];response.shopLogin=await loginSnapshot(state,response.account,tab.url,response.accountVerified===true);
   if(current()&&socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify(response));
  }catch(e){if(current())socket.close();}
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
  connect(message.tabId,message.token).then(async()=>{await storePair(async()=>{const {nblPairs={}}=await chrome.storage.local.get('nblPairs');nblPairs[String(message.tabId)]={tabId:message.tabId,token:message.token};await chrome.storage.local.set({nblPairs});});respond({ok:true});}).catch(e=>respond({ok:false,error:e.message}));return true;
 }
 if(message.type==='status'){respond({tabs:[...connections.values()].map(s=>({tabId:s.tabId,connected:s.socket?.readyState===WebSocket.OPEN}))});return;}
 if(message.type==='unpair'){disconnect(message.tabId).then(async()=>{await storePair(async()=>{const {nblPairs={}}=await chrome.storage.local.get('nblPairs');delete nblPairs[String(message.tabId)];await chrome.storage.local.set({nblPairs});await chrome.storage.local.remove('nblPair');});respond({ok:true});});return true;}
});
chrome.tabs.onRemoved.addListener(id=>void disconnect(id));
chrome.tabs.onUpdated.addListener((id,change)=>{if(change.url&&!officialUrl(change.url))void disconnect(id);});
// Reconnect only the paired tab. Reload/new app connection never starts automation itself.
async function restore(){const {nblPairs={},nblPair}=await chrome.storage.local.get(['nblPairs','nblPair']);const pairs={...nblPairs};if(nblPair&&!pairs[String(nblPair.tabId)])pairs[String(nblPair.tabId)]=nblPair;for(const pair of Object.values(pairs))if(!connections.has(pair.tabId)&&!connecting.has(pair.tabId))try{await connect(pair.tabId,pair.token);}catch(e){}}
chrome.alarms.create('nbl-reconnect',{periodInMinutes:.5});
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='nbl-reconnect')void restore();});
void restore();
