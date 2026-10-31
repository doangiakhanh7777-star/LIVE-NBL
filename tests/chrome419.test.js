'use strict';
// 4.1.9 (owner 26/10/2026): "lịch ghim sản phẩm theo giờ … ngay thời điểm bao nhiêu phút sẽ
// ghim sản phẩm nào, ghim trong bao lâu", and the LIVE page reload command.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const P=require('../CHROME_NBL_LIVE/pin_engine.js');
const src=fs.readFileSync(path.join(__dirname,'../CHROME_NBL_LIVE/content.js'),'utf8');

test('times and holds are read the way the owner writes them',()=>{
 assert.equal(P.span('5','minutes'),300);assert.equal(P.span('5:30','minutes'),330);assert.equal(P.span('1:05:30','minutes'),3930);
 assert.equal(P.span('90s','minutes'),90);assert.equal(P.span('60','seconds'),60);assert.equal(P.span('2:00','seconds'),120);assert.equal(P.span('2p','seconds'),120);
 assert.equal(P.span('5:75','minutes'),null);assert.equal(P.span('abc','minutes'),null);
});
test('a timeline is sorted, and a line that starts early cuts the one before',()=>{
 const t=P.parseTimeline('5:00 | 3 | 2:00\n0:30 | 1 | 60\n6:00 | 2 | 30\n\n# ghi chú');
 assert.deepEqual(t.map(x=>[x.at,x.number,x.end]),[[30,1,90],[300,3,360],[360,2,390]]);
 const cut=P.parseTimeline('1:00 | 1 | 120\n2:00 | 2 | 60');assert.equal(cut[0].end,120);assert.equal(cut[0].cut,true);
});
test('mistakes say which line is wrong',()=>{
 assert.throws(()=>P.parseTimeline('5:00 | 3'),/dòng 1/);
 assert.throws(()=>P.parseTimeline('0:10 | 1 | 30\n5:00 | x | 30'),/dòng 2.*số sản phẩm/);
 assert.throws(()=>P.parseTimeline('5:00 | 3 | 2'),/5 giây/);
 assert.throws(()=>P.parseTimeline('5:00 | 3 | 30\n5:00 | 4 | 30'),/cùng thời điểm/);
});
test('which line is active at a moment of the clip',()=>{
 const t=P.parseTimeline('0:30 | 1 | 60\n5:00 | 3 | 2:00');
 assert.equal(P.activeAt(t,29),null);assert.equal(P.activeAt(t,30).number,1);assert.equal(P.activeAt(t,89).number,1);
 assert.equal(P.activeAt(t,90),null);assert.equal(P.activeAt(t,301).number,3);assert.equal(P.activeAt(t,421),null);
});
test('clip time follows NBL VIDEO, wraps when the clip loops, and is not trusted when old',()=>{
 const now=1_000_000_000_000,sync={position:59000,duration:60000,playing:true,at:now/1000-3,received:now-3000};
 assert.equal(P.clipSeconds(sync,now),2);                  // 59 s + 3 s → looped to 2 s
 assert.equal(P.clipSeconds({...sync,playing:false},now),59);
 assert.equal(P.clipSeconds({...sync,duration:0},now,10),72);
 assert.equal(P.clipSeconds({...sync,received:now-31000},now),null);
});

// 4.1.11: the 4.1.9/4.1.10 "lịch ghim theo giờ clip" page became the app's clip pin script
// (ghim chèn); its tests are in chrome4111.test.js.
test('the page knows the reload and clip commands; a busy cart is never reloaded away',()=>{
 assert.match(src,/c\.action==='reload_page'\)\{if\(controlBusy\)error=/);
 assert.match(src,/setTimeout\(\(\)=>location\.reload\(\),1500\)/);
 assert.match(src,/c\.action==='clip_sync'\)\{clipSync=/);
});
