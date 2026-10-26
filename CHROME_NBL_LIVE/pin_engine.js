(function(root){
'use strict';
function validateRange(min,max){if(!Number.isInteger(min)||!Number.isInteger(max)||min<1||max<min||max>86400)throw Error('Thời gian: ít nhất 1 giây, số lớn không nhỏ hơn số bé.');}
function duration(min,max,last,random=Math.random){validateRange(min,max);const count=max-min+1;if(count===1)return min;const excluded=Number.isInteger(last)&&last>=min&&last<=max;let n=min+Math.min(count-(excluded?1:0)-1,Math.floor(random()*(count-(excluded?1:0))));if(excluded&&n>=last)n++;return n;}
function parseProducts(text,mode='number'){const lines=String(text).split(mode==='number'?/[\n,;]+/:/\n+/).map(s=>s.trim()).filter(Boolean),seen=new Set();return lines.map(text=>{if(mode==='number'&&!/^[1-9]\d{0,4}$/.test(text))throw Error('Số sản phẩm phải là số nguyên từ 1, mỗi dòng một số.');const key=mode==='number'?String(Number(text)):text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();if(seen.has(key))return null;seen.add(key);return {mode,text,number:mode==='number'?Number(text):null,key};}).filter(Boolean);}
class Cycle{
 constructor(jobs,random=Math.random){this.jobs=jobs;this.random=random;this.bag=[];this.last=null;this.phase='ready';this.current=null;this.lastHold=null;this.lastGap=null;}
 next(){if(!this.jobs.length)return null;if(!this.bag.length){this.bag=[...this.jobs];for(let i=this.bag.length-1;i>0;i--){const j=Math.min(i,Math.floor(this.random()*(i+1)));[this.bag[i],this.bag[j]]=[this.bag[j],this.bag[i]];}if(this.bag.length>1&&this.bag[0].key===this.last){const i=this.bag.findIndex(x=>x.key!==this.last);[this.bag[0],this.bag[i]]=[this.bag[i],this.bag[0]];}}const product=this.bag.shift();this.last=product.key;return product;}
 afterPin(item,min,max){this.current=item;this.phase='hold';return this.lastHold=duration(min,max,this.lastHold,this.random);}
 afterUnpin(min,max){this.current=null;this.phase='gap';return this.lastGap=duration(min,max,this.lastGap,this.random);}
}
// 4.1.9 (owner, 26/10/2026): "lịch ghim theo giờ clip" — at minute X of the clip pin
// product N for D. The clip always replays from its start when the LIVE starts.
// Line: time in clip | product number in the cart | how long to keep it pinned.
// Time: "5" = minute 5, "5:30", "1:05:30", "90s"; hold: "60" = 60 seconds, "2:00", "2p".
function span(text,plain){const t=String(text).trim().toLowerCase().replace(/\s+/g,'');let m;
 if((m=t.match(/^(\d+)(?:s|giây|giay)$/)))return +m[1];
 if((m=t.match(/^(\d+)(?:p|ph|phút|phut|m)$/)))return +m[1]*60;
 if(/^\d+$/.test(t))return plain==='minutes'?+t*60:+t;
 const p=t.split(':');if((p.length===2||p.length===3)&&p.every(x=>/^\d+$/.test(x))&&p.slice(1).every(x=>+x<60))return p.reduce((a,x)=>a*60+ +x,0);
 return null;}
function parseTimeline(text){const out=[];String(text||'').split(/\n+/).forEach((raw,i)=>{const line=raw.trim();if(!line||line.startsWith('#'))return;
  const p=line.split('|').map(x=>x.trim());const where='Lịch ghim dòng '+(i+1)+' ("'+line+'"): ';
  if(p.length!==3)throw Error(where+'cần 3 phần: thời điểm | số sản phẩm | giữ bao lâu');
  const at=span(p[0],'minutes'),hold=span(p[2],'seconds');
  if(at===null)throw Error(where+'thời điểm viết kiểu 5:30 (phút:giây)');
  if(!/^[1-9]\d{0,3}$/.test(p[1]))throw Error(where+'số sản phẩm là số thứ tự trong giỏ, từ 1');
  if(hold===null||hold<5||hold>6*3600)throw Error(where+'giữ ghim từ 5 giây tới 6 giờ');
  out.push({line:i+1,at,number:+p[1],hold,end:at+hold,mode:'number',text:p[1],key:p[1]});});
 out.sort((a,b)=>a.at-b.at);
 for(let i=1;i<out.length;i++){if(out[i].at===out[i-1].at)throw Error('Lịch ghim: dòng '+out[i-1].line+' và dòng '+out[i].line+' cùng thời điểm');
  if(out[i-1].end>out[i].at){out[i-1].end=out[i].at;out[i-1].cut=true;}}   // the next line takes over
 out.forEach((x,i)=>x.index=i);return out;}
function activeAt(entries,t){if(!Number.isFinite(t))return null;for(const x of entries)if(x.at<=t&&t<x.end)return x;return null;}
function clipSeconds(sync,now,offset=0,freshMs=30000){if(!sync||now-sync.received>freshMs)return null;let ms=sync.position+(sync.playing?Math.max(0,now-sync.at*1000):0);if(sync.duration>0)ms%=sync.duration;return ms/1000+offset;}
// 4.1.11: the clip pin script made in the app — [{at seconds, name, hold seconds}].
function cleanScript(list){if(!Array.isArray(list))return [];return list.map(x=>({at:Number(x&&x.at),name:String(x&&x.name||'').trim(),hold:Number(x&&x.hold)})).filter(x=>Number.isFinite(x.at)&&x.at>=0&&x.name&&Number.isFinite(x.hold)&&x.hold>=3).sort((a,b)=>a.at-b.at).slice(0,2000);}
function insertAt(script,t,clipSeconds=0){if(!Number.isFinite(t))return null;for(let i=0;i<script.length;i++){const x=script[i];let end=x.at+x.hold;if(i+1<script.length)end=Math.min(end,script[i+1].at);if(clipSeconds>0)end=Math.min(end,clipSeconds);if(x.at<=t&&t<end)return {...x,end,index:i};}return null;}
root.NBLPins={validateRange,duration,parseProducts,Cycle,span,parseTimeline,activeAt,clipSeconds,cleanScript,insertAt};if(typeof module!=='undefined')module.exports=root.NBLPins;
})(globalThis);
