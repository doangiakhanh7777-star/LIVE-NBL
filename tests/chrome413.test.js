'use strict';
// 4.1.3 (owner photo 19/10/2026 03:33): the "Chúc mừng…" end-of-LIVE box stayed open on
// Chrome. Run the REAL content.js functions on a fake page where the box is a plain
// div (no role=dialog) and its X is a bare svg icon.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../CHROME_NBL_LIVE/content.js'),'utf8');
const piece=src.slice(src.indexOf('// 4.1: cart preparation BEFORE the LIVE'),src.indexOf("$('addBundle').onclick="));
const harness=fs.readFileSync(path.join(__dirname,'cart41.test.js'),'utf8');
const {El}=new Function(harness.slice(harness.indexOf('function parseSel'),harness.indexOf('function page('))+';return {El};')();
const at=(el,left,top,width,height)=>{el.getBoundingClientRect=()=>({left,top,width,height,right:left+width,bottom:top+height});return el;};

function page({plain=true}={}){
 const body=at(new El('body'),0,0,1900,1000);
 const box=at(new El('div','',plain?{}:{role:'dialog'},plain?'tux-popup-container':'arco-modal'),470,200,960,740);
 const title=at(new El('h3','Chúc mừng bạn đã hoàn thành một buổi LIVE nữa - hãy tiếp tục phát huy!'),490,250,700,60);
 const x=at(new El('svg'),1384,227,22,22);
 const go=at(new El('button','Đi đến tổng quan dữ liệu LIVE'),650,880,200,36);
 const state={closed:false,overview:false};
 x.onclick=()=>{state.closed=true;box.remove();};go.onclick=()=>{state.overview=true;};
 box.add(title,x,at(new El('div','GMV đã ghi nhận 0đ'),490,320,300,60),go);body.add(box);
 return {body,state};
}
function run(pg){
 const reports=[],logs=[];
 const ctx={document:pg.body,window:{},getComputedStyle:()=>({visibility:'visible'}),Date,Number,String,Math,Error,Set,Promise,JSON,
  KeyboardEvent:class{constructor(t){this.type=t;}},MouseEvent:class{constructor(t){this.type=t;}},SVGElement:class{},setTimeout:f=>setImmediate(f),
  NBL:{norm:s=>String(s)},log:s=>logs.push(s),report:(...a)=>reports.push(a)};
 for(const e of [pg.body,...pg.body.all()])e.dispatchEvent=()=>true;
 vm.createContext(ctx);
 vm.runInContext(`let cfg={},controlEpoch=0,controlOwner=0,controlBusy=false,connectionLost=false,controlResult={};
 const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 function one(){throw Error('one');} function read(){return {};} function productCards(){return [];} function sendTarget(e){return e;}
 const delay=ms=>new Promise(r=>setTimeout(r,0));`,ctx);
 vm.runInContext(piece,ctx);
 return {ctx,reports,logs,run:s=>vm.runInContext(s,ctx)};
}
const settle=async()=>{for(let i=0;i<40;i++)await new Promise(r=>setImmediate(r));};

test('a plain end-of-LIVE box is found by its text',()=>{
 const pg=page();const r=run(pg);assert.ok(r.run('summaryDialog()'));
});
test('it closes by itself with the bare X icon, never the overview button',async()=>{
 const pg=page();const r=run(pg);r.run('autoCloseSummary()');await settle();
 assert.equal(pg.state.closed,true);assert.equal(pg.state.overview,false);
 assert.ok(r.reports.some(a=>/Đã đóng bảng tổng kết LIVE/.test(a[1])));
});
test('the classic arco modal still closes',async()=>{
 const pg=page({plain:false});const r=run(pg);await r.run('closeSummary()');assert.equal(pg.state.closed,true);
});
test('not while the tool is adding products',async()=>{
 const pg=page();const r=run(pg);r.run('controlBusy=true;autoCloseSummary()');await settle();assert.equal(pg.state.closed,false);
});
test('the auto close runs on every app tick and a busy refusal reaches the app at once',()=>{
 assert.match(src,/try\{closeNotices\(\);\}catch\(e\)\{log\(e\.message\);\}\n try\{autoCloseSummary\(\);\}catch\(e\)\{\}/);
 assert.match(src,/controlResult=\{id:c\.id,state:'failed',error,busy:'1'\}/);
});
test('4.1.8: a box that cannot be closed stops the cart with "busy" (retried) instead of clicking under it',()=>{
 assert.match(src,/try\{await closeSummary\(\);\}catch\(e\)\{log\(e\.message\);if\(e\.busy\|\|summaryDialog\(\)\)throw/);
 assert.match(src,/\.\.\.\(e\.busy\?\{busy:'1'\}:\{\}\)/);
});
