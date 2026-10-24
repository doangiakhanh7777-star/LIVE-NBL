'use strict';
// 4.1.5 (owner, 19/10/2026 04:40): several schedules saved at once; the next schedule
// found the previous schedule's products in the cart, skipped and never added its
// own set. A schedule with a set number now empties the cart, then adds its set.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../CHROME_NBL_LIVE/content.js'),'utf8');
const piece=src.slice(src.indexOf('// 4.1: cart preparation BEFORE the LIVE'),src.indexOf("$('addBundle').onclick="));
const harness=fs.readFileSync(path.join(__dirname,'cart41.test.js'),'utf8');
const {El,page}=new Function(harness.slice(harness.indexOf('function parseSel'),harness.indexOf('function run('))+';return {El,page};')();

function withOldCart(pg,{deletable=true}={}){
 const all=new El('label','Tất cả',{},'arco-checkbox');all.add(new El('input','',{type:'checkbox'}));pg.body.add(all);pg.state.deleted=false;
 if(deletable)all.onclick=()=>{if(pg.body.all().some(e=>e.ownText==='Xóa (5)'))return;const del=new El('button','Xóa (5)');pg.body.add(del);
  del.onclick=()=>{const m=new El('div','Xóa 5 sản phẩm khỏi phiên LIVE?',{role:'dialog'},'arco-modal');const ok=new El('button','Xóa');m.add(ok,new El('button','Hủy'));pg.body.add(m);
   ok.onclick=()=>{for(const c of pg.body.all().filter(e=>e.className==='card'||e.ownText==='Danh sách sản phẩm trong LIVE này'))c.remove();m.remove();del.remove();pg.body.add(new El('span','Chưa có sản phẩm'));pg.state.deleted=true;};};};
 return pg;
}
function run(pg,command){
 const logs=[],reports=[];
 const ctx={document:pg.body,window:{},getComputedStyle:()=>({visibility:'visible'}),Date,Number,String,Math,Error,Set,Promise,JSON,
  KeyboardEvent:class{constructor(t){this.type=t;}},MouseEvent:class{constructor(t){this.type=t;}},setTimeout:f=>setImmediate(f),
  NBL:{norm:s=>String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/đ/g,'d').trim()},log:s=>logs.push(s),report:(...a)=>reports.push(a)};
 const patchAll=()=>{for(const e of [pg.body,...pg.body.all()])if(!e.dispatchEvent)e.dispatchEvent=()=>true;};patchAll();
 const orig=El.prototype.add;El.prototype.add=function(...cs){const r=orig.apply(this,cs);patchAll();return r;};
 vm.createContext(ctx);
 vm.runInContext(`let cfg={},controlEpoch=0,controlOwner=0,controlBusy=false,connectionLost=false,controlResult={};
 const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 function one(spec){throw Error('one');} function read(){return {account:'',products:''};}
 function productCards(){return document.querySelectorAll('div.card');} function sendTarget(e){return e;}
 function liveTime(){throw Error('Không đọc được đồng hồ LIVE');}
 const delay=ms=>new Promise(r=>setTimeout(r,0));`,ctx);
 vm.runInContext(piece,ctx);
 return {ctx,logs,reports,go:()=>vm.runInContext('prepareBundle(command)',Object.assign(ctx,{command:{id:'c1',deadline:Date.now()/1000+150,preLive:true,...command}}))};
}
const result=r=>JSON.parse(JSON.stringify(vm.runInContext('controlResult',r.ctx)));

test('a schedule with a set number empties the old cart, then adds its own set',async()=>{
 const pg=withOldCart(page({cart:5}));const r=run(pg,{bundleIndex:2,replace:true});await r.go();
assert.equal(pg.state.deleted,true);assert.equal(result(r).state,'done');assert.equal(result(r).index,2);assert.equal(pg.state.picked,1);
 assert.ok(r.reports.some(a=>/Đã xoá giỏ cũ/.test(a[1])));
});
test('when the cart cannot be emptied the new set still goes on top and the owner is told',async()=>{
 const pg=withOldCart(page({cart:5}),{deletable:false});const r=run(pg,{bundleIndex:1,replace:true});await r.go();
 assert.equal(result(r).state,'done');assert.equal(pg.state.picked,0);assert.ok(r.reports.some(a=>a[0]==='loi'&&/Chưa xoá/.test(a[1])));
});
test('bộ số 0 keeps a cart filled by hand',async()=>{
 const pg=withOldCart(page({cart:5}));const r=run(pg,{bundleIndex:0,keepCart:true});await r.go();
 assert.equal(result(r).skipped,'cart');assert.equal(pg.state.deleted,false);assert.equal(pg.state.drawer,null);
});
test('bộ số 0 with an empty cart is a clear failure',async()=>{
 const pg=page();const r=run(pg,{bundleIndex:0,keepCart:true});await r.go();
 assert.equal(result(r).state,'failed');assert.match(result(r).error,/giữ giỏ tự thêm tay/);
});
test('an empty cart is just filled (nothing to remove)',async()=>{
 const pg=withOldCart(page());const r=run(pg,{bundleIndex:3,replace:true});await r.go();
 assert.equal(pg.state.deleted,false);assert.equal(result(r).state,'done');assert.equal(pg.state.picked,2);
});
