'use strict';
// 4.0.3: Chrome tab auto re-pairing, popup closing on the LIVE dashboard, reports to the app.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const dir=path.join(__dirname,'../CHROME_NBL_LIVE');

function background(store,tabs){
 const sockets=[],listeners={};
 class WebSocket{constructor(url){this.url=url;this.readyState=0;sockets.push(this);}send(){}close(){}}
 WebSocket.OPEN=1;
 const on=name=>({addListener:f=>{listeners[name]=f;}});
 const chrome={storage:{local:{get:async keys=>{const out={};for(const k of [].concat(keys))if(k in store)out[k]=JSON.parse(JSON.stringify(store[k]));return out;},set:async v=>{Object.assign(store,JSON.parse(JSON.stringify(v)));},remove:async k=>{delete store[k];}}},
  tabs:{get:async id=>{const t=tabs.find(t=>t.id===id);if(!t)throw Error('No tab');return t;},query:async q=>tabs.filter(t=>t.url.startsWith(q.url.replace('*',''))),update:async()=>{},onRemoved:on('removed'),onUpdated:on('updated')},
  alarms:{create(){},onAlarm:on('alarm')},runtime:{onMessage:on('message'),onStartup:on('startup')},windows:{update:async()=>{}}};
 const ctx={chrome,WebSocket,crypto:{randomUUID:()=>'00000000-0000-0000-0000-000000000001'},URL,setTimeout:()=>0,clearTimeout(){},console,Promise,Error,JSON,Object,Number,String,Set,Map,Array,Date};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(dir,'background.js'),'utf8'),ctx);
 return {ctx,sockets,listeners,store,restore:()=>vm.runInContext('restore()',ctx)};
}
const TOKEN='a'.repeat(32),DASH='https://shop.tiktok.com/streamer/live/product/dashboard?x=1';

test('Chrome restarted: old tab is gone, the open LIVE tab is paired with the saved code',async()=>{
 const b=background({nblPairs:{'11':{tabId:11,token:TOKEN}}},[{id:42,url:DASH}]);
 await b.restore();await b.restore();
 assert.ok(b.sockets.length>=1);
 assert.deepEqual(Object.keys(b.store.nblPairs),['42']);
 assert.equal(b.store.nblToken,TOKEN);
});
test('a tab disconnected by hand is not re-paired automatically',async()=>{
 const b=background({nblToken:TOKEN,nblPairs:{},nblSkip:[42]},[{id:42,url:DASH}]);
 await b.restore();
 assert.equal(b.sockets.length,0);
});
test('without a saved code nothing is paired',async()=>{
 const b=background({},[{id:42,url:DASH}]);
 await b.restore();
 assert.equal(b.sockets.length,0);
});
test('non-dashboard TikTok pages are not paired automatically',async()=>{
 const b=background({nblToken:TOKEN},[{id:7,url:'https://shop.tiktok.com/other'}]);
 await b.restore();
 assert.equal(b.sockets.length,0);
});

// --- popup closing, run against the real functions from content.js with a tiny fake DOM
const src=fs.readFileSync(path.join(dir,'content.js'),'utf8');
const piece=src.slice(src.indexOf('const reportQueue=[];'),src.indexOf('function stillBlocked()'));
function el(text,{buttons=[],role='dialog'}={}){const b=buttons.map(t=>({textContent:t,getAttribute:()=>null,getClientRects:()=>[1],clicked:0,click(){this.clicked++;}}));return {role,textContent:text,getClientRects:()=>[1],querySelectorAll:()=>b,buttons:b};}
function page(dialogs){
 const logs=[];const ctx={document:{querySelectorAll:()=>dialogs},getComputedStyle:()=>({visibility:'visible'}),Date,WeakMap,Set,String,Error,console,controlBusy:false,
  $:()=>({textContent:''})};
 vm.createContext(ctx);
 vm.runInContext(`const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 function buttonName(button){return [button.getAttribute('aria-label'),button.getAttribute('title'),button.textContent].filter(Boolean).map(x=>x.trim());}`,ctx);
 vm.runInContext(piece.replace("const log=s=>{$('log').textContent=new Date().toLocaleTimeString()+' '+s+'\\n'+$('log').textContent.slice(0,6500);","const log=s=>{"),ctx);
 return {ctx,run:s=>vm.runInContext(s,ctx)};
}
const RESTRICTED='Phiên LIVE đã bị hạn chế hiển thị Buổi LIVE của bạn không đủ điều kiện để được đề xuất và đang bị hạn chế trong kết quả tìm kiếm';
test('restriction notice is closed with its OK button and reported',()=>{
 const d=el(RESTRICTED,{buttons:['OK']});const p=page([d]);
 p.run('closeNotices()');
 assert.equal(d.buttons[0].clicked,1);
 const reports=p.run('takeReports()');
 assert.equal(reports.length,1);assert.equal(reports[0].kind,'hoat_dong');assert.match(reports[0].title,/Tự đóng thông báo/);
});
test('violation notice is closed too',()=>{
 const d=el('Vi phạm của video LIVE Nội dung có thể vi phạm nguyên tắc',{buttons:['Đã hiểu']});const p=page([d]);
 p.run('closeNotices()');assert.equal(d.buttons[0].clicked,1);
});
test('captcha, security check and ended LIVE are never clicked',()=>{
 for(const text of ['Cảnh báo: hoàn thành captcha','Cảnh báo xác minh bảo mật','Cảnh báo: Phiên LIVE đã kết thúc']){
  const d=el(text,{buttons:['OK']});page([d]).run('closeNotices()');assert.equal(d.buttons[0].clicked,0,text);
 }
});
test('ordinary dialogs (no warning words) are left alone',()=>{
 const d=el('Thêm sản phẩm vào phiên LIVE',{buttons:['Đóng']});page([d]).run('closeNotices()');assert.equal(d.buttons[0].clicked,0);
});
test('a notice that will not close stops with a clear error after 3 s, without clicking forever',()=>{
 const d=el(RESTRICTED,{buttons:['OK']});const p=page([d]);
 p.run('closeNotices();closeNotices();');assert.equal(d.buttons[0].clicked,1);
 p.run('closedAt.set(document.querySelectorAll()[0],Date.now()-4000)');
 assert.throws(()=>p.run('closeNotices()'),/không đóng được/);
});
test('pins and replies are turned into reports; ordinary log lines are not',()=>{
 const p=page([]);
 p.run("log('Đã ghim: Vietmap Live Pro');log('Đã thấy bình luận chủ phòng: Giá có trong giỏ ạ');log('App đã lưu cấu hình nick.')");
 const r=p.run('takeReports()');
 assert.deepEqual(JSON.parse(JSON.stringify(r.map(x=>x.title))),['Chrome · Đã ghim sản phẩm','Chrome · Đã trả lời bình luận']);
});
