'use strict';
// 4.1.8 (owner 25/10/2026): the end-of-LIVE box still stayed open on Chrome and the next
// cart failed. When the X cannot close it, NBL reloads the LIVE page (once per 3 min).
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../CHROME_NBL_LIVE/content.js'),'utf8');
const piece=src.slice(src.indexOf('// 4.1: cart preparation BEFORE the LIVE'),src.indexOf("$('addBundle').onclick="));
const harness=fs.readFileSync(path.join(__dirname,'cart41.test.js'),'utf8');
const {El}=new Function(harness.slice(harness.indexOf('function parseSel'),harness.indexOf('function page('))+';return {El};')();
const at=(el,left,top,width,height)=>{el.getBoundingClientRect=()=>({left,top,width,height,right:left+width,bottom:top+height});return el;};
function page(){   // a box whose X does nothing (the case the owner keeps seeing)
 const body=at(new El('body'),0,0,1900,1000);
 const box=at(new El('div','',{},'tux-popup-container'),470,200,960,740);
 box.add(at(new El('h3','Chúc mừng bạn đã hoàn thành một buổi LIVE nữa - hãy tiếp tục phát huy!'),490,250,700,60),at(new El('svg'),1384,227,22,22));
 body.add(box);return body;
}
function run(store){
 const reloads=[],timers=[];
 const ctx={document:page(),window:{},getComputedStyle:()=>({visibility:'visible'}),Date,Number,String,Math,Error,Set,Promise,JSON,Object,
  KeyboardEvent:class{constructor(t){this.type=t;}},MouseEvent:class{constructor(t){this.type=t;}},SVGElement:class{},
  setTimeout:(f,ms)=>{if(ms>=1000)timers.push(f);else setImmediate(f);},
  sessionStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=v;}},location:{reload:()=>reloads.push(1)},
  NBL:{norm:s=>String(s)},log:()=>{},report:()=>{}};
 for(const e of [ctx.document,...ctx.document.all()])e.dispatchEvent=()=>true;
 vm.createContext(ctx);
 vm.runInContext(`let running=false,cfg={},controlEpoch=0,controlOwner=0,controlBusy=false,connectionLost=false,controlResult={};
 const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 function one(){throw Error('one');} function read(){return {};} function productCards(){return [];} function sendTarget(e){return e;}
 const delay=ms=>new Promise(r=>setTimeout(r,0));`,ctx);
 vm.runInContext(piece,ctx);
 return {ctx,reloads,timers,run:s=>vm.runInContext(s,ctx)};
}
test('a box that will not close makes the LIVE page reload, and the cart is told "busy"',async()=>{
 const store={};const r=run(store);
 const e=await r.run('closeSummary()').catch(e=>e);
 assert.equal(e.busy,true,String(e&&e.stack));assert.equal(r.timers.length,1);r.timers[0]();assert.equal(r.reloads.length,1);
 const res=await r.run(`prepareBundle({id:'c1',preLive:true,deadline:Date.now()/1000+60}).then(()=>controlResult)`);
 assert.equal(res.state,'failed');
});
test('never reloads again within 3 minutes (no reload loop)',async()=>{
 const store={nblReloadAt:String(Date.now()-60000)};const r=run(store);
 const e=await r.run('closeSummary()').catch(e=>e);
 assert.notEqual(e.busy,true);assert.equal(r.timers.length,0);
});
test('a cart command switches off pin/reply left on from the LIVE before',()=>{
 assert.match(src,/if\(running&&c\.stopModules&&!controlBusy\)\{manager\.stop\('all'\)/);
});
test('4.1.9: never reloads while pin/reply are on (a LIVE is still going, e.g. a mid-LIVE "Chúc mừng" box)',async()=>{
 const store={};const r=run(store);r.run('running=true');
 const e=await r.run('closeSummary()').catch(e=>e);
 assert.notEqual(e.busy,true);assert.equal(r.timers.length,0);
});
