'use strict';
// 4.1.1: QR login removed; a slow LIVE tab must not close the app connection.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const dir=path.join(__dirname,'../CHROME_NBL_LIVE');
const DASH='https://shop.tiktok.com/streamer/live/product/dashboard';
function background({url=DASH,content}={}){
 const sockets=[];
 class FakeSocket{constructor(u){this.url=u;this.readyState=1;this.sent=[];this.closed=0;sockets.push(this);}send(d){this.sent.push(JSON.parse(d));}close(){this.closed++;}}
 FakeSocket.OPEN=1;
 const noop=()=>{},listener={addListener:noop};
 const ctx={console,setTimeout:()=>0,clearTimeout:noop,Promise,URL,JSON,Error,Number,String,Object,Set,Map,Date,crypto:{randomUUID:()=>'0'.repeat(8)+'-'+'0'.repeat(4)+'-'+'0'.repeat(4)+'-'+'0'.repeat(4)+'-'+'0'.repeat(12)},WebSocket:FakeSocket,
  chrome:{storage:{local:{get:async()=>({}),set:async()=>{},remove:async()=>{}}},alarms:{create:noop,onAlarm:listener},runtime:{onMessage:listener,onStartup:listener},
   tabs:{get:async()=>({url}),update:async()=>({}),query:async()=>[],sendMessage:async(id,m)=>m.type==='version'?{protocol:402}:content(m),onRemoved:listener,onUpdated:listener}}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(dir,'background.js'),'utf8'),ctx);
 return {ctx,sockets,run:s=>vm.runInContext(s,ctx)};
}
async function tick(b,commands=[{id:'c1',action:'cart_check',module:'all'}]){
 b.run("var st={tabId:7,token:'a'.repeat(32),instance:'b'.repeat(32),closed:false,socket:null,retry:null,port:0};connections.set(7,st);open(st);");
 const s=b.sockets.at(-1);s.onopen();await s.onmessage({data:JSON.stringify({type:'tick',commands})});
 for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r));return s;
}
test('manifest has no QR login script and no login hosts',()=>{
 const m=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json'),'utf8'));
 assert.equal(m.version,'4.1.11');
 const all=JSON.stringify(m);assert.ok(!/shop_login|seller-vn|tiktok\.com\/login/.test(all));
 assert.equal(m.content_scripts.length,1);assert.ok(!fs.existsSync(path.join(dir,'shop_login.js')));
});
test('extension sources no longer handle QR login',()=>{
 for(const f of ['background.js','popup.js','popup.html','content.js'])assert.ok(!/shop_login|shopLogin|nbl-shop-login|loginSnapshot|loginCommand/.test(fs.readFileSync(path.join(dir,f),'utf8')),f);
 assert.match(fs.readFileSync(path.join(dir,'popup.js'),'utf8'),/url:\['https:\/\/shop\.tiktok\.com\/\*'\]/);
});
test('only TikTok Shop pages can be paired',()=>{
 const b=background();
 assert.equal(b.run("officialUrl('https://shop.tiktok.com/streamer/live/product/dashboard')"),true);
 assert.equal(b.run("officialUrl('https://www.tiktok.com/login')"),false);
 assert.equal(b.run("officialUrl('https://seller-vn.tiktok.com/homepage')"),false);
});
test('a LIVE tab that does not answer keeps the connection and acknowledges nothing',async()=>{
 const b=background({content:async()=>{throw Error('Tab LIVE không phản hồi.');}});
 const s=await tick(b);
 assert.equal(s.closed,0);assert.equal(s.sent.length,2);
 const reply=s.sent[1];assert.equal(reply.account,'Đang đọc trang');assert.equal(reply.accountVerified,false);assert.deepEqual(reply.acks,[]);
});
test('a normal tick forwards every command to the LIVE tab and returns its answer',async()=>{
 let got;const b=background({content:async m=>{got=m;return {account:'Nick',accountVerified:true,modules:{},acks:[{id:'c1',error:''}],config:{}};}});
 const s=await tick(b);
 assert.equal(got.commands.length,1);assert.equal(got.commands[0].id,'c1');
 assert.equal(s.closed,0);assert.deepEqual(s.sent[1].acks,[{id:'c1',error:''}]);assert.ok(!('shopLogin' in s.sent[1]));
});
test('a tab outside the LIVE dashboard refuses commands without disconnecting',async()=>{
 const b=background({url:'https://shop.tiktok.com/homepage',content:async()=>({})});
 const s=await tick(b);
 assert.equal(s.closed,0);assert.equal(s.sent[1].acks[0].error,'Chưa mở bảng LIVE của nick này.');
});
