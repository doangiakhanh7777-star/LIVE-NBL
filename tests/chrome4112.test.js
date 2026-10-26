'use strict';
// 4.1.12 (owner photo 26/10/2026 19:41): the "Sản phẩm" list only draws ~5 of 100 products;
// NBL pinned only those on top and said number 12 / 50 "was not in the cart". Now it
// scrolls the list to the product (by number, or by name through the catalog).
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../CHROME_NBL_LIVE/content.js'),'utf8');
const NBL=require('../CHROME_NBL_LIVE/engine.js');
const fn=name=>{const i=src.indexOf('function '+name+'(');let j=src.indexOf('\nfunction ',i+1);const k=src.indexOf('\nasync function ',i+1);if(k>0&&k<j)j=k;return src.slice(i,j);};
const ROW=150,VIEW=600,N=100;
function page(){
 const titles=Array.from({length:N},(_,i)=>i===76?'Q2Pro Bơm Lốp Ôtô Xe Máy':i===11?'Ốp khoá Vinfast VF3':'Sản phẩm số '+(i+1));
 const box={_t:0,clientHeight:VIEW,scrollHeight:N*ROW,scrolls:0,dispatchEvent(){},get scrollTop(){return this._t;},set scrollTop(v){this.scrolls++;this._t=Math.max(0,Math.min(N*ROW-VIEW,Math.round(v)));}};
 const cards=()=>{const first=Math.floor(box._t/ROW),out=[];for(let i=first;i<Math.min(N,first+5);i++)out.push({i,number:i+1,title:titles[i],getBoundingClientRect:()=>({top:i*ROW-box._t+300})});return out;};
 const ctx={NBL,Math,Number,String,Error,Date,Map,Set,Promise,Event:class{},KeyboardEvent:class{},setTimeout:f=>setImmediate(f),
  cfg:{products:'p',productTitle:'t',productNumber:'n'},visible:()=>true,host:{},
  document:{addEventListener(){},querySelector:()=>null,querySelectorAll:()=>[]},
  productCards:cards,relativeMatches:(spec,card)=>spec==='n'?[{n:card.number}]:[{textContent:card.title}],readNumber:el=>el.n,
  productIdentity:card=>({card,title:card.title,key:NBL.norm(card.title)}),changeInput(){}};
 vm.createContext(ctx);
 vm.runInContext(fn('pin')+src.slice(src.indexOf('const pause='),src.indexOf('async function doPin(')),ctx);
 vm.runInContext('listBox=()=>BOX;',Object.assign(ctx,{BOX:box}));
 return {ctx,box};
}
test('number 50 far below the drawn products is found by scrolling, quickly',async()=>{
 const {ctx,box}=page();const card=await ctx.findCard({mode:'number',number:50});
 assert.equal(card.number,50);assert.ok(box.scrolls<=6,'scrolled '+box.scrolls+' times');
});
test('number 12 and then back up to number 3',async()=>{
 const {ctx,box}=page();assert.equal((await ctx.findCard({mode:'number',number:12})).number,12);
 assert.equal((await ctx.findCard({mode:'number',number:3})).number,3);
});
test('a product NAME far down the list is found by sweeping the list',async()=>{
 const {ctx}=page();const card=await ctx.findCard({mode:'name',text:'Q2Pro Bơm Lốp Ôtô Xe Máy'});assert.equal(card.number,77);
});
test('a product that is really not in the cart: null, and the list goes back to the top',async()=>{
 const {ctx,box}=page();assert.equal(await ctx.findCard({mode:'name',text:'Camera hành trình 4K'}),null);assert.equal(box.scrollTop,0);
});
test('the whole cart is read once (catalog), then a name goes straight to its number',async()=>{
 const {ctx,box}=page();await ctx.scanCatalog();
 assert.equal(vm.runInContext('catalog.items.length',ctx),100);assert.equal(box.scrollTop,0);
 box.scrolls=0;const card=await ctx.findCard({mode:'name',text:'ốp khoá vinfast vf3'});assert.equal(card.number,12);assert.ok(box.scrolls<=6);
});
test('the shuffle no longer skips products that are not drawn on screen',async()=>{
 const {ctx}=page();await ctx.scanCatalog();
 assert.ok(ctx.known({mode:'number',number:60}));assert.equal(ctx.known({mode:'number',number:160}),null);
 assert.ok(ctx.known({mode:'name',text:'Q2Pro Bơm Lốp'}));
});
test('the shuffle uses known(), the pin goes through findCard and the search box as last resort',()=>{
 assert.match(src,/const candidate=cycle\.next\(\),seen=known\(candidate\);if\(!seen\)continue;/);
 assert.match(src,/async function doPin\(product\)\{assertContext\(\);let card=await findCard\(product\),search=null;/);
 assert.match(src,/Tìm ID hoặc tên sản phẩm/);
});
