(function(root){
'use strict';
const norm=s=>String(s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').toLowerCase().trim();
function seconds(s){const p=String(s).trim().split(':');if(p.length!==3||p.some(x=>!/^\d+$/.test(x))||+p[1]>59||+p[2]>59)throw Error('Thời gian phải là HH:MM:SS');return +p[0]*3600 + +p[1]*60 + +p[2];}
function parse(lines,kind){return lines.split('\n').filter(s=>s.trim()).map((s,i)=>{const p=s.split('|').map(x=>x.trim());if(kind==='rule'){if(p.length!==2||!p[0]||!p[1])throw Error('Quy tắc: từ khóa | câu trả lời');return {words:p[0].split(';').map(norm),text:p[1]};}if(p.length!==2||!p[1])throw Error('Lịch: HH:MM:SS | nội dung / tên sản phẩm');return {at:seconds(p[0]),text:p[1],id:kind+i};}).sort((a,b)=>(a.at||0)-(b.at||0));}
// 4.0: whole-word matching ("gia" no longer matches "giao"/"giay") and the most
// specific rule wins (keyword phrase with the most words); a tie between rules is ambiguous -> null.
const words=s=>' '+norm(s).replace(/[^\p{L}\p{N}]+/gu,' ').trim()+' ';
function score(rule,padded){let best=0;for(const w of rule.words){const k=words(w);if(k.trim()&&padded.includes(k))best=Math.max(best,k.trim().split(' ').length);}return best;}
function answer(rules,text){const padded=words(text);let best=0,winners=[];for(const r of rules){const n=score(r,padded);if(!n)continue;if(n>best){best=n;winners=[r];}else if(n===best&&!winners.some(x=>x.text===r.text))winners.push(r);}return winners.length===1?winners[0].text:null;}
function due(jobs,elapsed,previous,done,cycle=0){return jobs.filter(j=>j.at<=elapsed&&j.at>previous&&!done.has(cycle+':'+j.id));}
function recurringDue(jobs,elapsed,previous,done,duration=0){if(!duration)return due(jobs,elapsed,previous,done).map(j=>({...j,absoluteAt:j.at,key:'0:'+j.id}));const cycle=Math.floor(elapsed/duration);return jobs.map(j=>({...j,absoluteAt:cycle*duration+j.at,key:cycle+':'+j.id})).filter(j=>j.absoluteAt<=elapsed&&j.absoluteAt>previous&&!done.has(j.key));}
const api={norm,words,seconds,parse,answer,due,recurringDue};root.NBL=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis==='undefined'?window:globalThis);
