'use strict';
// 4.1.11 (owner 26/10/2026): "ghim chèn" from the clip pin script made in the app, shuffle
// pin OFF when its times are 0, the cart number is an <input> box, exact product names,
// and the pinned product that moved to its own "Đã ghim" box on top.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const P=require('../CHROME_NBL_LIVE/pin_engine.js');
const src=fs.readFileSync(path.join(__dirname,'../CHROME_NBL_LIVE/content.js'),'utf8');
const NBL=require('../CHROME_NBL_LIVE/engine.js');
const fn=name=>{const i=src.indexOf('function '+name+'(');let j=src.indexOf('\nfunction ',i+1);const k=src.indexOf('\nasync function ',i+1);if(k>0&&k<j)j=k;return src.slice(i,j);};

test('the script from the app: cut by the next flag and by the end of the clip',()=>{
 const s=P.cleanScript([{at:300,name:'B',hold:60},{at:30,name:'A',hold:120},{at:590,name:'C',hold:60},{at:5,name:'',hold:9},{at:7,name:'x',hold:1}]);
 assert.deepEqual(s.map(x=>x.name),['A','B','C']);                       // empty name / hold < 3 dropped
 assert.equal(P.insertAt(s,100,600).name,'A');assert.equal(P.insertAt(s,150,600),null);
 assert.equal(P.insertAt(s,599,600).name,'C');assert.equal(P.insertAt(s,600,600),null);
 const cut=P.cleanScript([{at:10,name:'A',hold:60},{at:40,name:'B',hold:60}]);assert.equal(P.insertAt(cut,39,0).name,'A');assert.equal(P.insertAt(cut,40,0).name,'B');
});

test('the cart number is read from its <input> box (owner screenshots)',()=>{
 const ctx={};vm.createContext(ctx);vm.runInContext(fn('readNumber'),ctx);
 const input={value:'3',getAttribute:()=>null,matches:s=>s==='input'};
 const wrap={textContent:'',getAttribute:()=>null,matches:()=>false,querySelector:()=>input};
 assert.equal(ctx.readNumber(input),3);assert.equal(ctx.readNumber(wrap),3);
 assert.equal(ctx.readNumber({textContent:'#7',getAttribute:()=>null,matches:()=>false,querySelector:()=>null}),7);
});

function cards(titles){return titles.map(t=>({title:t}));}
test('names: an exact name wins; a name inside two products is refused, never guessed',()=>{
 const ctx={NBL,visible:()=>true,cfg:{productTitle:'t'},relativeMatches:(spec,card)=>[{textContent:card.title}],productCards:()=>ctx.list,Error};
 vm.createContext(ctx);vm.runInContext(fn('pin'),ctx);
 ctx.list=cards(['Bơm lốp mini','Bơm lốp mini PRO']);
 assert.equal(ctx.pin({mode:'name',text:'bơm lốp  mini'}).title,'Bơm lốp mini');
 ctx.list=cards(['Bơm lốp mini xanh','Bơm lốp mini PRO']);
 assert.throws(()=>ctx.pin({mode:'name',text:'Bơm lốp mini'}),/khớp nhiều/);
 ctx.list=cards(['Camera hành trình 4K']);assert.equal(ctx.pin({mode:'name',text:'Bơm'}),null);
});

test('a product number read on some cards only still finds the right card (pinned card moved on top)',()=>{
 const ctx={visible:()=>true,cfg:{productNumber:'n'},Error,readNumber:el=>el.n,relativeMatches:(spec,card)=>card.n===undefined?[]:[{n:card.n}],productCards:()=>ctx.list};
 vm.createContext(ctx);vm.runInContext(fn('pin'),ctx);
 ctx.list=[{n:1,id:'a'},{n:3,id:'c'},{n:2,id:'b'}];assert.equal(ctx.pin({mode:'number',number:2}).id,'b');
 ctx.list=[{id:'top'},{n:2,id:'b'},{n:3,id:'c'}];assert.equal(ctx.pin({mode:'number',number:3}).id,'c');
});

function shuffleSetup(cycle,clicks){
 const ctx={NBLPins:P,NBL,Math,String,Number,Date,Error,Object,cfg:{cycle},log:()=>{},report:(...a)=>clicks.push('report '+a[1]),
  doPin:async p=>{clicks.push('pin '+p.text);return ctx.missing===p.text?null:{key:p.text,title:p.text};},doUnpin:async i=>{clicks.push('unpin '+i.title);}};
 vm.createContext(ctx);
 const piece=src.slice(src.indexOf('let clipSync=null;'),src.indexOf('async function tick(){'));
 vm.runInContext(piece+';this.sync=(pos,script)=>{clipSync={position:pos*1000,duration:600000,playing:false,at:Date.now()/1000,received:Date.now(),clip:"c1",script:NBLPins.cleanScript(script)}};',ctx);
 return ctx;
}
test('a flag pauses the shuffle, pins its product once, then the shuffle pins its next product',async()=>{
 const clicks=[],ctx=shuffleSetup(true,clicks),state={running:true,generation:1,pinCycle:{phase:'hold',current:{title:'X'}},nextPinAt:Date.now()+999999};
 const script=[{at:60,name:'Bơm lốp',hold:30}];
 ctx.sync(30,script);assert.equal(await ctx.insertTick(state),false);              // no flag yet: shuffle runs
 ctx.sync(61,script);assert.equal(await ctx.insertTick(state),true);
 ctx.sync(70,script);assert.equal(await ctx.insertTick(state),true);
 assert.deepEqual(clicks,['pin Bơm lốp']);assert.equal(state.pinCycle.phase,'gap');   // shuffle paused
 ctx.sync(95,script);assert.equal(await ctx.insertTick(state),true);
 assert.deepEqual(clicks,['pin Bơm lốp']);                                           // shuffle on: its pin replaces it
 assert.ok(state.nextPinAt<=Date.now());assert.equal(state.lastProductKey,'Bơm lốp'); // next shuffle product, not the same one
});
test('shuffle OFF: the inserted product is taken down when its time is over',async()=>{
 const clicks=[],ctx=shuffleSetup(false,clicks),state={running:true,generation:1};
 const script=[{at:10,name:'Sạc xe',hold:20}];
 ctx.sync(12,script);await ctx.insertTick(state);ctx.sync(40,script);await ctx.insertTick(state);
 assert.deepEqual(clicks,['pin Sạc xe','unpin Sạc xe']);
});
test('two flags in a row with the same product: it stays pinned',async()=>{
 const clicks=[],ctx=shuffleSetup(false,clicks),state={running:true,generation:1};
 const script=[{at:10,name:'Sạc xe',hold:20},{at:30,name:'sạc  xe',hold:20}];
 for(const t of [11,25,31,45])ctx.sync(t,script),await ctx.insertTick(state);
 assert.deepEqual(clicks,['pin Sạc xe']);
});
test('a product not in the cart is tried again every 5 seconds and reported once',async()=>{
 const clicks=[],ctx=shuffleSetup(true,clicks),state={running:true,generation:1};ctx.missing='Đèn LED';
 const script=[{at:10,name:'Đèn LED',hold:60}];
 ctx.sync(11,script);await ctx.insertTick(state);ctx.sync(12,script);await ctx.insertTick(state);
 assert.deepEqual(clicks.filter(c=>c.startsWith('pin')),['pin Đèn LED']);
 state.insTryAt=0;ctx.missing='';ctx.sync(17,script);await ctx.insertTick(state);
 assert.deepEqual(clicks.filter(c=>c.startsWith('pin')),['pin Đèn LED','pin Đèn LED']);
 assert.equal(clicks.filter(c=>c.startsWith('report')).length,1);
});
test('no video position from the app = no flags (never guessed from another clock)',async()=>{
 const clicks=[],ctx=shuffleSetup(true,clicks);assert.equal(await ctx.insertTick({running:true,generation:1}),false);
});

test('shuffle pin: all four times 0 = OFF, half-filled = clear error',()=>{
 const ctx={NBLPins:P,NBL,Number,String,Error,read:()=>ctx.c};vm.createContext(ctx);vm.runInContext(fn('prepare'),ctx);
 ctx.c={owner:'',pins:'1\n2',productMode:'number',pinMin:'0',pinMax:'0',gapMin:'0',gapMax:'0'};assert.equal(ctx.prepare('pin').cycle,false);
 ctx.c={...ctx.c,pins:'',pinMin:'30',pinMax:'40',gapMin:'30',gapMax:'40'};assert.equal(ctx.prepare('pin').cycle,false);
 ctx.c={...ctx.c,pins:'1',pinMin:'30',pinMax:'0'};assert.throws(()=>ctx.prepare('pin'),/để 0 cả 4 ô/);
 ctx.c={...ctx.c,pinMax:'40',products:'p',productTitle:'t'};assert.equal(ctx.prepare('pin').cycle,true);
 assert.equal((src.match(/data-zero="1" data-default="\d+" data-min="0"/g)||[]).length,4);
});

test('the unused "bundle name" picks are gone; the pinned box on top can be unpinned',async()=>{
 assert.doesNotMatch(src,/bundleTitle:'Tên của bộ sản phẩm'/);
 const clicked=[];let pinnedOnTop=true;const button={click:()=>{clicked.push('Bỏ ghim');pinnedOnTop=false;}};
 const ctx={Error,host:{contains:()=>false},document:{},assertContext:()=>{},trackedCard:()=>{throw Error('gone');},
  actionButtons:()=>pinnedOnTop?[button]:[],sendTarget:b=>b,log:()=>{},wait:async t=>{if(!t())throw Error('no');}};
 vm.createContext(ctx);vm.runInContext(fn('pageUnpin')+fn('doUnpin').replace('function doUnpin','this.doUnpin=async function'),ctx);
 await ctx.doUnpin({title:'Vietmap'});assert.deepEqual(clicked,['Bỏ ghim']);
});
