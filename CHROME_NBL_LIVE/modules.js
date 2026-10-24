(function(root){
'use strict';
const keys=['pin','reply'];
class Modules {
 constructor(){this.items=Object.fromEntries(keys.map(k=>[k,{running:false,error:'',generation:0}]));}
 start(key,prepare){if(!keys.includes(key))throw Error('Mục không hợp lệ');const old=this.items[key];old.running=false;old.generation++;try{const config=prepare();this.items[key]={running:true,error:'',generation:old.generation,config,started:Date.now(),prev:-1,done:new Set(),pending:[],replyAt:new Map(),seen:new Set()};return this.items[key];}catch(e){old.error=e.message;throw e;}}
 stop(key,error=''){if(key==='all'){for(const k of keys)this.stop(k,error);return;}const s=this.items[key];if(!s)return;s.running=false;s.error=error;s.generation++;s.pending=[];}
 async guard(key,work){const state=this.items[key];if(!state.running)return;const generation=state.generation;try{await work(state);}catch(e){if(state.running&&state.generation===generation)this.stop(key,e.message);}}
 status(){return Object.fromEntries(keys.map(k=>[k,{running:this.items[k].running,error:this.items[k].error,...(this.items[k].detail?{detail:this.items[k].detail}:{})}]));}
}
root.NBLModules={Modules,keys};if(typeof module!=='undefined')module.exports=root.NBLModules;
})(globalThis);
