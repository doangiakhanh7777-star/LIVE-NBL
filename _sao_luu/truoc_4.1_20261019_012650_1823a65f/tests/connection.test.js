'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../CHROME_NBL_LIVE/content.js'),'utf8'),start=src.indexOf('const handled=new Set();');
const actual=src.slice(start,src.indexOf("document.addEventListener('keydown'",start));
function page(){let handler,watchdog;const ctx={console,Date:{now:()=>1000000},NBLModules:{keys:['pin','reply']},setInterval:f=>watchdog=f,chrome:{runtime:{onMessage:{addListener:f=>handler=f}}}};vm.createContext(ctx);
 vm.runInContext(`let running=true,connectionLost=false,activeModule='',tickBusy=false,switchBusy=false,boundAccount='Nick',lastAppAck='';
 const states={pin:{running:true,pending:[{text:'old'}],nextPinAt:1},reply:{running:false,pending:[]}};
 const manager={items:states,status:()=>states,stop:k=>{for(const key of k==='all'?['pin','reply']:[k])states[key].running=false;}};
 function stop(){manager.stop('all');running=false;} function cancelControl(){} function read(){return {account:'selector',bundleName:'Bo A'};} function one(){return {textContent:'Nick'};} function log(){} function pulse(){} function tick(){} function saveConfig(){return Promise.resolve();} function identity(){return 'Nick';} function renderModules(){} function renderSuggestions(){} function startModule(k){states[k].running=true;return '';}
 let suggestions=[],cfg={},controlResult={};`,ctx);vm.runInContext(actual,ctx);
 return {run:s=>vm.runInContext(s,ctx),watchdog:()=>watchdog(),tick:(overrides={})=>{let reply;handler({type:'tick',commands:[],connectionId:'server:tab',configAck:'saved',...overrides},{},r=>reply=r);return reply;}};
}
test('late watchdog cannot resume a connection missing for 60 seconds',()=>{const p=page();p.run("lastTickAt=940000;runningSince=880000;lastConnectionId='server:tab';connectionLost=true");p.tick();assert.equal(p.run('states.pin.running'),false);p.watchdog();assert.equal(p.run('states.pin.running'),false);});
test('new server connection stops old automation',()=>{const p=page();p.run("lastTickAt=999000;lastConnectionId='old:tab'");p.tick();assert.equal(p.run('states.pin.running'),false);});
test('short interruption of same connection retains pin state and clears queued replies',()=>{const p=page();p.run("lastTickAt=999000;lastConnectionId='server:tab';connectionLost=true");p.tick();assert.equal(p.run('states.pin.running'),true);assert.equal(p.run('states.pin.pending.length'),0);});
test('first new connection sends all unchanged configuration',()=>{const p=page();p.run("lastSentConfig=JSON.stringify(read());lastSentConfigAt=999999;connectionNeedsConfig=false;lastConnectionId='old:tab'");assert.equal(p.tick().config.bundleName,'Bo A');});
test('missing app acknowledgement forces full configuration',()=>{const p=page();p.run("lastSentConfig=JSON.stringify(read());lastSentConfigAt=999999;connectionNeedsConfig=false;lastConnectionId='server:tab'");assert.equal(p.tick({configAck:''}).config.bundleName,'Bo A');});
test('stable acknowledged connection does not send the configuration each tick',()=>{const p=page();p.tick();assert.equal(Object.hasOwn(p.tick(),'config'),false);});
test('shutdown stops modules and rejects starts in the same tick',()=>{const p=page();const r=p.tick({closing:true,commands:[{id:'start',action:'start',module:'pin',deadline:2000}]});assert.equal(p.run('states.pin.running'),false);assert.ok(r.acks[0].error);});
test('acknowledged stop contains stopped module state',()=>{const p=page();const r=p.tick({commands:[{id:'stop',action:'stop',module:'all',deadline:2000}]});assert.equal(r.acks[0].id,'stop');assert.equal(r.modules.pin.running,false);assert.equal(r.modules.reply.running,false);});
const pins=require('../CHROME_NBL_LIVE/pin_engine.js'),{Modules}=require('../CHROME_NBL_LIVE/modules.js');
test('pin duration stays in range and avoids the immediately previous duration',()=>{let previous;for(let i=0;i<1000;i++){const n=pins.duration(30,40,previous);assert.ok(n>=30&&n<=40);assert.notEqual(n,previous);previous=n;}});
test('single duration range is supported',()=>assert.equal(pins.duration(30,30,30),30));
test('shuffled product cycles never repeat adjacent products across rounds',()=>{const c=new pins.Cycle([1,2,3,4,5].map(n=>({key:String(n)})));let last;for(let i=0;i<100;i++){const n=c.next().key;assert.notEqual(n,last);last=n;}});
test('pin transitions include a separate unpinned rest',()=>{const c=new pins.Cycle([{key:'1'}]);c.afterPin({key:'1'},30,40);assert.equal(c.phase,'hold');c.afterUnpin(30,40);assert.equal(c.phase,'gap');assert.equal(c.current,null);});
test('module failure stays isolated',async()=>{const m=new Modules();m.start('pin',()=>({}));m.start('reply',()=>({}));await m.guard('pin',async()=>{throw Error('pin failure');});assert.equal(m.items.pin.running,false);assert.equal(m.items.reply.running,true);});
