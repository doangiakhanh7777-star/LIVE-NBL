'use strict';
// 4.1.13 (owner 26/10/2026 20:26): read ONLY the number column (1, 2, 3… on the left), take the
// Ghim button of the same row, scroll to the number; names through the page search box
// (3–4 first words; several results → the one starting with them, else the first).
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../CHROME_NBL_LIVE/content.js'),'utf8');
const NBL=require('../CHROME_NBL_LIVE/engine.js');
const fn=name=>{const i=src.indexOf('function '+name+'(');let j=src.indexOf('\nfunction ',i+1);const k=src.indexOf('\nasync function ',i+1);if(k>0&&k<j)j=k;return src.slice(i,j);};
const ROW=170,VIEW=640,TOP=300;
function el(tag,props={}){const e={tagName:tag.toUpperCase(),children:[],parentElement:null,attrs:{},textContent:'',value:'',_rect:()=>({left:0,top:-9999,width:0,height:0,right:0,bottom:0}),...props};
 e.getBoundingClientRect=()=>{const r=e._rect();return {...r,right:r.left+r.width,bottom:r.top+r.height};};e.getClientRects=()=>e.hidden?[]:[1];
 e.getAttribute=k=>e.attrs[k]??null;e.matches=s=>s==='input'?e.tagName==='INPUT':false;e.contains=x=>{for(let p=x;p;p=p.parentElement)if(p===e)return true;return false;};
 e.add=(...k)=>{for(const c of k){c.parentElement=e;e.children.push(c);}return e;};e.querySelector=s=>s==='input'?e.children.find(c=>c.tagName==='INPUT')||null:null;e.closest=()=>null;e.dispatchEvent=()=>true;return e;}
function page({virtual=true,names,slow=0,never=false}={}){
 const N=100,state={scroll:0,pinned:0,clicks:[]};
 const titles=names||Array.from({length:N},(_,i)=>({0:'Vietmap Live Pro Dẫn đường',2:'(2 Năm) Vietmap Live Plus Bản Quyền',11:'Ốp khoá Vinfast VF3',76:'Q2Pro Bơm Lốp Ôtô Xe Máy'})[i]||'Sản phẩm số '+(i+1));
 const search=el('input',{attrs:{placeholder:'Tìm ID hoặc tên sản phẩm'},_rect:()=>({left:240,top:200,width:300,height:30})});
 const box={_t:0,clientHeight:VIEW,get scrollHeight(){return rowsShown(true).length*ROW+300;},dispatchEvent(){},get scrollTop(){return this._t;},set scrollTop(v){this.scrolls=(this.scrolls||0)+1;this._t=Math.max(0,Math.min(Math.max(0,this.scrollHeight-VIEW),Math.round(v)));}};
 const products=titles.map((t,i)=>{const row=el('div');const input=el('input',{value:String(i+1)});const b=el('button');Object.defineProperty(b,'textContent',{get:()=>state.pinned===i+1?'Bỏ ghim':'Ghim'});
  b.click=()=>{state.clicks.push(i+1);const was=state.pinned===i+1;state.shownAt=clock+slow;state.next=was?0:(never?-1:i+1);if(!slow&&!never)state.pinned=state.next;};row.add(input,b);Object.defineProperty(row,'textContent',{get:()=>String(i+1)+t+'474.999đCòn: 2,5K'});return {i,row,input,b,title:t};});
 // a voucher row and the "Danh sách sản phẩm trong LIVE này" row also have a Ghim button, no number box
 const voucher=el('button',{textContent:'Ghim',_rect:()=>({left:690,top:TOP-120,width:70,height:24})}),list=el('button',{textContent:'Ghim',_rect:()=>({left:690,top:TOP-50,width:70,height:24})});
 function rowsShown(all){if(state.next!==undefined&&state.next!==-1&&clock>=state.shownAt){state.pinned=state.next;state.next=undefined;}const q=nn(search.value);const list=products.filter(p=>!q||nn(p.title).includes(q));const top=list.filter(p=>p.i+1===state.pinned);return top.concat(list.filter(p=>p.i+1!==state.pinned));}   // 4.1.14: the pinned product moves to the top
 function layout(){const shown=rowsShown();const first=virtual?Math.floor(box._t/ROW):0;
  products.forEach(p=>{p.input.hidden=true;p.b.hidden=true;});
  shown.forEach((p,k)=>{if(virtual&&(k<first||k>=first+5))return;const top=TOP+k*ROW-box._t;p.input.hidden=false;p.b.hidden=false;p.input._rect=()=>({left:245,top:top+10,width:30,height:28});p.b._rect=()=>({left:690,top:top+80,width:70,height:24});});}
 const nn=x=>NBL.norm(x).replace(/\s+/g,' ');
 let clock=1e12;
 const ctx={NBL,Math,Number,String,Error,JSON,Map,Set,Promise,Object,Event:class{},KeyboardEvent:class{},
  Date:{now:()=>clock},setTimeout:(f,ms)=>{clock+=ms||0;setImmediate(f);},
  host:{contains:()=>false},cfg:{},getComputedStyle:()=>({visibility:'visible',overflowY:'auto'}),
  document:{addEventListener(){},body:{},documentElement:{},querySelectorAll:s=>{layout();if(s==='input')return [search,...products.map(p=>p.input)];if(s==='button,[role=button]')return [voucher,list,...products.map(p=>p.b)];return [];}},
  changeInput:(input,text)=>{input.value=text;},log:()=>{},assertContext:()=>{},$:()=>null,selector:()=>'input'};
 vm.createContext(ctx);
 vm.runInContext('const visible=e=>e&&e.getClientRects().length;'+fn('buttonName')+fn('actionButtons')+fn('readNumber')+fn('sendTarget').replace('el instanceof SVGElement','false')+src.slice(src.indexOf('const pause='),src.indexOf('// "Kiểm tra cột số"'))+src.slice(src.indexOf('// "Kiểm tra cột số"'),src.indexOf('function sendTarget(el){')),ctx);
 vm.runInContext('listBox=()=>BOX;',Object.assign(ctx,{BOX:box}));
 return {ctx,state,box,search};
}
test('the number column: each number gets the Ghim of its own row; voucher / list rows never',()=>{
 const {ctx}=page({virtual:false});const rows=ctx.numberRows();
 assert.equal(rows.length,100);assert.ok(rows.every(r=>r.pin));
 rows[1].pin.click();const {state}={state:null};
 assert.equal(ctx.numberRows().find(r=>r.number===2).pinned,true);
});
test('number 50 (not drawn yet) is reached by scrolling and pinned; the list goes back to the top',async()=>{
 const {ctx,state,box}=page();const item=await ctx.doPin({mode:'number',number:50});
 assert.equal(state.pinned,50);assert.equal(item.key,'#50');assert.equal(box.scrollTop,0);
 assert.ok(box.scrolls<=8,'jumps close to the number instead of sweeping ('+box.scrolls+' scrolls)');
});
test('a number written as text in a flag ("12") also goes through the column',async()=>{
 const {ctx,state}=page();await ctx.doPin({mode:'name',text:'12'});assert.equal(state.pinned,12);
});
test('a name goes through the search box (3–4 first words) and the box is cleared after',async()=>{
 const {ctx,state,search}=page();const item=await ctx.doPin({mode:'name',text:'Q2Pro Bơm Lốp'});
 assert.equal(state.pinned,77);assert.equal(item.number,77);assert.equal(search.value,'');
});
test('several results: the one whose name STARTS with the words wins, otherwise the first',async()=>{
 const {ctx,state}=page();await ctx.doPin({mode:'name',text:'Vietmap Live'});assert.equal(state.pinned,1);   // not "(2 Năm) Vietmap Live Plus"
 const p2=page();await p2.ctx.doPin({mode:'name',text:'Bản Quyền'});assert.equal(p2.state.pinned,3);
});
test('a name that is not in the cart: nothing clicked, search box cleared',async()=>{
 const {ctx,state,search}=page();assert.equal(await ctx.doPin({mode:'name',text:'Camera 4K'}),null);
 assert.deepEqual(state.clicks,[]);assert.equal(search.value,'');
});
test('a number that is not in the cart: nothing clicked',async()=>{
 const {ctx,state}=page();assert.equal(await ctx.doPin({mode:'number',number:140}),null);assert.deepEqual(state.clicks,[]);
});
test('unpin finds its number again even after the list scrolled away',async()=>{
 const {ctx,state,box}=page();const item=await ctx.doPin({mode:'number',number:60});box.scrollTop=0;
 await ctx.doUnpin(item);assert.equal(state.pinned,0);
});
test('"Kiểm tra cột số" and "Tìm thử" only read, never pin',async()=>{
 const {ctx,state}=page();const report=await ctx.checkColumn();
 assert.match(report,/Đọc được 100 ô số · từ 1 tới 100 · không thiếu số nào · đủ nút Ghim/);
 assert.match(await ctx.findTest('35'),/Số 35: Sản phẩm số 35/);assert.match(await ctx.findTest('Ốp khoá'),/số 12 · Ốp khoá Vinfast VF3/);
 assert.deepEqual(state.clicks,[]);
});
test('the shuffle really tries every product (no list read beforehand decides); the app can ask "Tìm thử"',()=>{
 assert.doesNotMatch(src,/known\(candidate\)/);assert.match(src,/item=await doPin\(candidate\)/);
 assert.match(src,/c\.action==='find_product'/);assert.match(src,/id="testPins"/);assert.match(src,/id="checkColumn"/);
});

// ---- 4.1.14 (owner photo 26/10/2026 20:59): after Ghim TikTok moves the product to the TOP;
// the list was still scrolled down → "chưa thấy Bỏ ghim" → hold / rest times never applied.
test('pin far down: click once → back to the top → confirmed there; the list ends at the top',async()=>{
 const {ctx,state,box}=page();const item=await ctx.doPin({mode:'number',number:67});
 assert.equal(state.pinned,67);assert.deepEqual(state.clicks,[67]);assert.equal(item.confirmed,true);assert.equal(box.scrollTop,0);
});
test('a slow page (12 s) is still confirmed: the 15 s only start once the list is back on top',async()=>{
 const {ctx,state}=page({slow:12000});const item=await ctx.doPin({mode:'number',number:67});
 assert.equal(item.confirmed,true);assert.deepEqual(state.clicks,[67]);
});
test('never shown as pinned: no error, no second click (it could unpin), still held, list at the top',async()=>{
 const {ctx,state,box}=page({never:true});const item=await ctx.doPin({mode:'number',number:40});
 assert.equal(item.confirmed,false);assert.equal(item.number,40);assert.deepEqual(state.clicks,[40]);assert.equal(box.scrollTop,0);
});
test('unpin: the pinned product is taken down from the top of the list',async()=>{
 const {ctx,state,box}=page();const item=await ctx.doPin({mode:'number',number:67});box.scrollTop=5000;
 await ctx.doUnpin(item);assert.equal(state.pinned,0);assert.deepEqual(state.clicks,[67,67]);assert.equal(box.scrollTop,0);
});
test('the product pinned on top does not spoil the distance estimate to another number',async()=>{
 const {ctx,state,box}=page();await ctx.doPin({mode:'number',number:67});box.scrolls=0;
 await ctx.doPin({mode:'number',number:30});assert.equal(state.pinned,30);assert.ok(box.scrolls<=10,'scrolled '+box.scrolls);
});
test('hold and rest are counted from the confirmation (a 5 s confirmation does not eat the hold)',async()=>{
 const P=require('../CHROME_NBL_LIVE/pin_engine.js');
 const a=src.indexOf(" if(module==='pin'&&await insertTick(state)){}"),b=src.indexOf(" }else{\n  for(const r of chat())");
 let t=0;const ev=[];
 const ctx={NBLPins:P,NBL,Math,String,Number,Error,Object,Map,Date:class extends Date{static now(){return t;}},log(){},report(){},FATAL:/x^/,hhmmss:()=>'',
  cfg:{cycle:true,pinJobs:P.parseProducts('35\n14','number'),pinMin:30,pinMax:30,gapMin:20,gapMax:20},
  doPin:async p=>{t+=5000;ev.push(['pin',p.number,t/1000]);return {number:p.number,title:'số '+p.number,key:'#'+p.number,confirmed:true};},
  doUnpin:async i=>{t+=3000;ev.push(['unpin',i.number,t/1000]);},insertTick:async()=>false};
 vm.createContext(ctx);vm.runInContext("async function step(state){const module='pin';"+src.slice(a,b)+"}}",ctx);
 const state={running:true,generation:1,pinCycle:new P.Cycle(ctx.cfg.pinJobs,()=>0.5),nextPinAt:0};
 for(;t<=140000;t+=1000)await ctx.step(state);
 const [p1,u1,p2]=ev;assert.equal(u1[2]-3-p1[2],30);                 // held 30 s after the confirmation
 assert.equal(p2[2]-5-u1[2],20);                                         // rested 20 s after the unpin was done
});
