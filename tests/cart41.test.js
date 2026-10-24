'use strict';
// 4.1: cart preparation on the TikTok Shop LIVE dashboard, run with the REAL
// content.js functions against a small fake page built like the owner's screenshots.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../CHROME_NBL_LIVE/content.js'),'utf8');
const piece=src.slice(src.indexOf('// 4.1: cart preparation BEFORE the LIVE'),src.indexOf("$('addBundle').onclick="));

function parseSel(sel){return sel.split(',').map(s=>s.trim()).filter(Boolean).map(part=>{const m=part.match(/^([a-z0-9]*)(.*)$/i);const tag=m[1].toUpperCase();const conds=[];let rest=m[2];
 const re=/\.([\w-]+)|\[([\w-]+)(?:([*^]?=)([^\]\s]+)(?:\s+i)?)?\]/g;let found;while((found=re.exec(rest))){const x=found;if(x[1])conds.push(e=>String(e.className).split(/\s+/).includes(x[1]));else{const [_,_a,name,op,val]=x;const v=val&&val.replace(/^["']|["']$/g,'');conds.push(e=>{const a=name==='class'?String(e.className):e.getAttribute(name);if(op===undefined)return a!==null&&a!==undefined;if(a===null||a===undefined)return false;return op==='*='?String(a).toLowerCase().includes(v.toLowerCase()):String(a)===v;});}}
 return e=>(!tag||e.tagName===tag)&&conds.every(c=>c(e));});}
class El{constructor(tag,text='',attrs={},cls=''){this.tagName=tag.toUpperCase();this.ownText=text;this.attrs={...attrs};this.className=cls;this.children=[];this.parentElement=null;this.hidden=false;this.onclick=null;this.disabled=!!attrs.disabled;this.checked=false;}
 add(...cs){for(const c of cs){c.parentElement=this;this.children.push(c);}return this;}
 remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(c=>c!==this);this.parentElement=null;}
 get innerText(){return [this.ownText,...this.children.filter(c=>!c.hidden).map(c=>c.innerText)].filter(Boolean).join(' ');}
 get textContent(){return this.innerText;}
 getAttribute(n){return n in this.attrs?this.attrs[n]:null;}
 getClientRects(){let e=this;while(e){if(e.hidden)return [];e=e.parentElement;}return [1];}
 getBoundingClientRect(){return {left:0,top:0,right:20,bottom:20,width:20,height:20};}
 all(){return this.children.flatMap(c=>[c,...c.all()]);}
 matches(sel){return parseSel(sel).some(f=>f(this));}
 querySelectorAll(sel){return this.all().filter(e=>e.matches(sel));}
 closest(sel){let e=this;while(e){if(e.matches&&e.matches(sel))return e;e=e.parentElement;}return null;}
 contains(o){while(o){if(o===this)return true;o=o.parentElement;}return false;}
 click(){if(this.onclick)this.onclick();else if(this.parentElement&&this.tagName==='INPUT'){}}
}
function page({cart=0,bundles=[['MỚI NHẤT',10],['THIẾT BỊ CHUẨN NGHỊ ĐỊNH',80],['Live',91]],added=null,fail=false,perPage=10}={}){
 const body=new El('body');const header=new El('button','+ Thêm');body.add(header);
 const empty=new El('span','Chưa có sản phẩm');if(!cart)body.add(empty);
 if(cart)body.add(new El('span','Danh sách sản phẩm trong LIVE này'));for(let i=0;i<cart;i++)body.add(new El('div','món '+i,{},'card'));
 const state={picked:null,confirmed:false,drawer:null,page:0};
 header.onclick=()=>{const d=new El('div','',{role:'dialog'},'arco-drawer');d.add(new El('span','Thêm sản phẩm mới'));
  const close=new El('span','',{'aria-label':'Close'},'arco-drawer-close-icon');close.onclick=()=>{d.remove();};d.add(close);
  const tabs=[new El('div','Sản phẩm trên trang trưng bày',{role:'tab'}),new El('div','Bộ sản phẩm TRỰC TIẾP',{role:'tab'}),new El('div','URL sản phẩm',{role:'tab'})];d.add(...tabs);
  const list=new El('div','',{},'list');const footer=new El('div','Bạn có thể thêm 150 sản phẩm nữa');
  const confirm=new El('button','Thêm sản phẩm',{disabled:true},'arco-btn disabled');confirm.disabled=true;
  const render=()=>{list.children=[];const slice=bundles.slice(state.page*perPage,(state.page+1)*perPage);slice.forEach(([name,n],k)=>{const row=new El('div','',{},'row');const label=new El('label','',{},'arco-radio');const input=new El('input','',{type:'radio'});label.add(input);
    const idx=state.page*perPage+k;label.onclick=()=>{state.picked=idx;footer.ownText=n+'/'+n+' sản phẩm sẽ được thêm vào đầu danh sách.';confirm.disabled=false;confirm.className='arco-btn';};
    const title=new El('div',name+' >');title.onclick=()=>{state.openedDetail=true;};row.add(label,title,new El('span',n+' sản phẩm'));list.add(row);});
   if(bundles.length>(state.page+1)*perPage){const next=new El('li','',{},'arco-pagination-item-next');next.onclick=()=>{state.page++;render();};list.add(next);}};
  tabs[1].onclick=()=>render();
  confirm.onclick=()=>{state.confirmed=true;const n=bundles[state.picked][1];footer.ownText=fail?'Không thể thêm sản phẩm nào':'Đã thêm '+(added??n)+'/'+n+' sản phẩm vào buổi LIVE';if(!fail){empty.remove();}};
  d.add(list,footer,confirm);body.add(d);state.drawer=d;};
 return {body,state};
}
function run(pg,command){
 const logs=[],reports=[];let cfg={};
 const ctx={document:pg.body,getComputedStyle:()=>({visibility:'visible'}),Date,Number,String,Math,Error,Set,Promise,JSON,KeyboardEvent:class{constructor(t){this.type=t;}},setTimeout:(f)=>setImmediate(f),
  NBL:{norm:s=>String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/đ/g,'d').trim()},log:s=>logs.push(s),report:(...a)=>reports.push(a)};
 pg.body.dispatchEvent=()=>{};
 vm.createContext(ctx);
 vm.runInContext(`let cfg={},controlEpoch=0,controlOwner=0,controlBusy=false,connectionLost=false,controlResult={};
 const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 function one(spec){const a=document.querySelectorAll(spec).filter(visible);if(a.length!==1)throw Error('one');return a[0];}
 function read(){return {account:'',products:''};}
 function productCards(){return document.querySelectorAll('div.card');}
 function sendTarget(e){return e;}
 function liveTime(){throw Error('Không đọc được đồng hồ LIVE');}
 const delay=ms=>new Promise(r=>setTimeout(r,0));`,ctx);
 vm.runInContext(piece,ctx);
 return {ctx,logs,reports,go:()=>vm.runInContext('prepareBundle(command)',Object.assign(ctx,{command:{id:'c1',deadline:Date.now()/1000+150,preLive:true,...command}}))};
}
const result=r=>JSON.parse(JSON.stringify(vm.runInContext('controlResult',r.ctx)));

test('adds the chosen set number 2 before the LIVE and closes the drawer',async()=>{
 const pg=page();const r=run(pg,{bundleIndex:2});await r.go();
 assert.deepEqual(result(r).state,'done');assert.equal(result(r).index,2);assert.equal(pg.state.picked,1);
 assert.equal(pg.state.drawer.parentElement,null);assert.ok(!pg.state.openedDetail);
});
test('partial add (sold-out items) counts as success',async()=>{
 const pg=page({added:8});const r=run(pg,{bundleIndex:1});await r.go();
 assert.equal(result(r).state,'done');assert.equal(result(r).added,'8');assert.equal(result(r).total,'10');
});
test('a cart that already has products is left alone',async()=>{
 const pg=page({cart:5});const r=run(pg,{bundleIndex:1});await r.go();
 assert.equal(result(r).skipped,'cart');assert.equal(pg.state.drawer,null);
});
test('set number beyond the list fails clearly without adding',async()=>{
 const pg=page();const r=run(pg,{bundleIndex:7});await r.go();
 assert.equal(result(r).state,'failed');assert.match(result(r).error,/bộ sản phẩm số 7/);assert.ok(!pg.state.confirmed);
});
test('set number on page 2 is reached through the pager',async()=>{
 const bundles=Array.from({length:13},(_,i)=>['Bộ '+(i+1),5]);const pg=page({bundles});const r=run(pg,{bundleIndex:12});await r.go();
 assert.equal(result(r).state,'done');assert.equal(pg.state.picked,11);
});
test('TikTok refusing every product is a failure (LIVE must not start)',async()=>{
 const pg=page({fail:true});const r=run(pg,{bundleIndex:1});await r.go();
 assert.equal(result(r).state,'failed');assert.match(result(r).error,/không thêm được/);
});
test('pre-LIVE add does not need the LIVE clock; a LIVE add still does',async()=>{
 const pg=page();const r=run(pg,{bundleIndex:1,preLive:false});await r.go();
 assert.equal(result(r).state,'failed');assert.match(result(r).error,/đồng hồ/);
});
