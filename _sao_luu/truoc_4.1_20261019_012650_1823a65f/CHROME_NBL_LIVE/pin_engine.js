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
root.NBLPins={validateRange,duration,parseProducts,Cycle};if(typeof module!=='undefined')module.exports=root.NBLPins;
})(globalThis);
