(async()=>{
'use strict';
if(document.getElementById('nbl-live-extension'))return;
const host=document.createElement('div');host.id='nbl-live-extension';document.documentElement.append(host);
const ui=host.attachShadow({mode:'open'});
ui.innerHTML=`<style>:host{all:initial}section{position:fixed;right:12px;bottom:12px;width:min(390px,calc(100vw - 40px));max-height:84vh;overflow:auto;z-index:2147483647;background:#fff;color:#25384d;padding:16px;border:2px solid #44b7f2;border-radius:20px;font:14px Arial;box-shadow:0 7px 28px #1b6b9b30}h3{margin:0 0 12px;cursor:move;touch-action:none;position:sticky;top:0;background:#fff;z-index:2;color:#1673aa}label{display:block;margin-top:11px;font-weight:600}input,textarea,select{box-sizing:border-box;width:100%;padding:9px;margin-top:5px;background:#f4fbff;color:#25384d;border:1px solid #b3d4e7;border-radius:10px;font:14px Arial}textarea{height:76px}button{background:#e8f6ff;color:#135982;border:1px solid #9ad3f3;border-radius:11px;padding:9px;margin:5px 4px 5px 0;cursor:pointer;font:13px Arial}button:hover{background:#ccecff}pre{white-space:pre-wrap;font:12px Arial;max-height:160px;overflow:auto}.red{background:#fff0ed;color:#ae3723;border-color:#ffc0ad}.bar{background:#ff993f;color:#382100;border-color:#f28629}.step{display:flex;align-items:center;gap:6px;margin-top:5px}.step output{min-width:84px;text-align:center;background:#f0f9ff;padding:8px;border-radius:10px}.step button{margin:0}.hint{font-size:12px;line-height:1.45;color:#526e80}.selectors{display:none}details{margin:14px 0;padding:10px;background:#f5fbff;border-radius:12px}summary{cursor:pointer;font-weight:600}.picked{font-size:12px;font-weight:400;color:#267440}</style>
<section><h3>NBL LIVE • 4.1.5 <button id="fold">Thu gọn</button></h3><div id="body">
<p class="hint">Giỏ hàng và trả lời bình luận trên Chrome. Tin nhắn định kỳ và Chào khách cài trong app NBL LIVE.</p>
<label>Tên chủ phòng trong bình luận<input id="owner" placeholder="Khánh Car Auto"></label>
<label>Câu trả lời tự động<textarea id="rules" placeholder="bơm lốp;bom lop | Anh xem sản phẩm bơm lốp trong giỏ nhé."></textarea></label><p id="rulesHint" class="hint">Chưa có quy tắc. Chữ mẫu mờ không phải nội dung đã nhập.</p><p class="hint">Mỗi dòng: từ khóa | câu trả lời. Nhiều từ khóa cùng câu: ngăn bằng dấu ;</p>
<label>Chọn sản phẩm ghim bằng<select id="productMode"><option value="number">Số thứ tự trong giỏ</option><option value="name">Tên sản phẩm</option></select></label>
<button id="readProducts">Chọn sản phẩm từ giỏ hiện tại</button><p class="hint">Nếu số trên trang không đọc được, app đánh số NBL và nhớ đúng món đã tích. Không cần chọn chữ Đã ghim khi nút Ghim/Bỏ ghim đã đọc được.</p><div id="productChoices"></div><input id="productBindings" type="hidden"><label>Sản phẩm muốn ghim<textarea id="pins" placeholder="1&#10;3&#10;5"></textarea></label><p class="hint">Mỗi dòng một số hoặc một tên theo cách chọn ở trên. Tự xáo trộn mỗi vòng; món không có trong giỏ được bỏ qua.</p>
<label>Giữ sản phẩm đang ghim</label><div data-time="pinMin" data-default="30" data-min="1" data-label="Ít nhất"></div><div data-time="pinMax" data-default="40" data-min="1" data-label="Nhiều nhất"></div>
<label>Nghỉ sau khi tháo ghim</label><div data-time="gapMin" data-default="30" data-min="1" data-label="Ít nhất"></div><div data-time="gapMax" data-default="40" data-min="1" data-label="Nhiều nhất"></div><p class="hint">Ghim → giữ → tháo ghim → nghỉ không ghim món nào → ghim món tiếp theo.</p>
<label>Trả lời bình luận<select id="replyMode"><option value="auto">Tự gửi theo từ khóa</option><option value="suggest">Hiện gợi ý để tôi duyệt</option></select></label><label>Nghỉ trước khi trả lời lại cùng khách</label><div data-time="cooldown" data-default="60" data-min="15" data-label="Khoảng nghỉ"></div><div id="suggestions"></div>
<details><summary>Chọn các nút trên trang — làm một lần</summary><p class="hint">Bấm Chọn rồi bấm đúng vị trí trên trang. Nhấn Esc để hủy. Các vị trí đã chọn được dùng chung giữa các nick; nội dung lưu riêng từng nick.</p><div id="pickFields"></div><button id="shareSetup">Lưu cách chọn nút để dùng chung</button><button id="useShared">Dùng cách chọn nút đã lưu</button>
<details><summary>Cài đặt nâng cao</summary><div id="advancedFields"></div></details></details>
<label>Bộ sản phẩm (số thứ tự từ trên xuống, hoặc tên bộ)<input id="bundleName" placeholder="1"></label><button id="addBundle">Thêm bộ vào phiên LIVE</button><p class="hint">Lịch LIVE trong app tự thêm bộ đã chọn trước giờ phát. Nút này để thêm tay. Giỏ đã có sản phẩm thì không thêm nữa; món hết hàng được bỏ qua.</p>
<button id="save">Lưu ngay</button><button id="check">Kiểm tra kết nối trang</button><button id="start" class="bar">Bật các mục</button><button id="stop" class="red">Dừng các mục</button><div id="modules"></div>
<details><summary>Sao lưu và vị trí bảng</summary><button id="export">Xuất bản sao cài đặt</button><button id="import">Nhập bản sao cài đặt</button><input id="importFile" type="file" accept=".json" hidden><button id="resetPosition">Đưa bảng về góc dưới bên phải</button></details><p id="state">Đã dừng</p><pre id="log"></pre></div></section>`;
const $=id=>ui.getElementById(id);
const setupLabels={account:'Tên tài khoản',live:'Đồng hồ LIVE',input:'Ô nhập tin nhắn',send:'Nút gửi tin nhắn',rows:'Một dòng bình luận gồm tên và câu hỏi',user:'Tên khách trong dòng bình luận',text:'Câu hỏi trong dòng bình luận',products:'Một ô sản phẩm trong giỏ',productTitle:'Tên sản phẩm trong ô',productNumber:'Số thứ tự trong ô sản phẩm — nếu có',pinned:'Trạng thái ghim — không bắt buộc',unpinButton:'Nút Bỏ ghim trong ô sản phẩm — nếu có',bundleOpen:'Nút Thêm sản phẩm',bundleTab:'Mục Bộ sản phẩm TRỰC TIẾP — nếu có',bundleCards:'Một bộ sản phẩm có sẵn',bundleTitle:'Tên của bộ sản phẩm',bundleConfirm:'Nút xác nhận Thêm sản phẩm',bundleReady:'Danh sách sản phẩm trong phiên LIVE'};
const sharedFields=Object.keys(setupLabels),relativeParents={user:'rows',text:'rows',productTitle:'products',productNumber:'products',pinned:'products',unpinButton:'products',bundleTitle:'bundleCards'};
for(const [id,label] of Object.entries(setupLabels)){const row=document.createElement('div'),button=document.createElement('button'),status=document.createElement('span'),input=document.createElement('input'),advanced=document.createElement('label');button.textContent='Chọn '+label;button.dataset[relativeParents[id]?'relative':'pick']=id;if(relativeParents[id])button.dataset.parent=relativeParents[id];status.id=id+'Picked';status.className='picked';status.textContent='Chưa chọn';row.append(button,status);$('pickFields').append(row);input.id=id;advanced.textContent=label+' — mã vị trí';advanced.append(input);$('advancedFields').append(advanced);}
for(const box of ui.querySelectorAll('[data-time]')){const id=box.dataset.time,input=document.createElement('input'),label=document.createElement('span'),out=document.createElement('output');input.id=id;input.type='hidden';input.value=box.dataset.default;label.textContent=box.dataset.label;out.id=id+'Display';box.className='step';box.append(label);for(const amount of [-10,-1,1,10]){const button=document.createElement('button');button.textContent=(amount>0?'+':'')+amount;button.onclick=()=>{input.value=String(Math.max(Number(box.dataset.min),Math.min(86400,Number(input.value)+amount)));input.dispatchEvent(new Event('change'));};box.append(button);if(amount===-1)box.append(out);}box.append(input);}
const fields=['owner','rules','pins','productMode','replyMode','cooldown','pinMin','pinMax','gapMin','gapMax','bundleName','productBindings',...sharedFields];
const pickErrors=new Map();
function relativeMatches(spec,base){if(spec===':scope'&&base instanceof Element)return [base];return [...base.querySelectorAll(spec)];}
function buttonName(button){return [button.getAttribute('aria-label'),button.getAttribute('title'),button.textContent].filter(Boolean).map(x=>x.trim().replace(/^[^\p{L}\p{N}]+/u,'').replace(/\s+/g,' '));}
function actionButtons(card,kind){const re=kind==='unpin'?/^(Bỏ ghim|Tháo ghim|Unpin)( sản phẩm)?$/i:/^(Ghim|Pin)( sản phẩm)?$/i;return [...card.querySelectorAll('button,[role=button]')].filter(visible).filter(b=>buttonName(b).some(x=>re.test(x)));}
function readNumber(el){const values=[el.textContent,el.getAttribute('aria-label'),el.getAttribute('data-number'),el.getAttribute('data-index')];for(const value of values){const t=String(value||'').trim();if(/^#?\s*[1-9]\d{0,4}[.)]?$/.test(t))return Number(t.replace(/[^\d]/g,''));}return null;}
function inspectField(id,spec){
 if(!spec)return {ok:false,text:id==='pinned'||id==='unpinButton'?'Tự nhận Ghim/Bỏ ghim':'Chưa chọn'};
 try{
  const parent=relativeParents[id];const roots=parent?[...document.querySelectorAll($(parent).value)].filter(visible):[document];
  const matches=roots.flatMap(root=>relativeMatches(spec,root).filter(visible));
  if(!matches.length)return {ok:false,text:'Đã lưu · chưa thấy trên trang này'};
  if(!parent&&!['rows','products','bundleCards'].includes(id)&&matches.length!==1)return {ok:false,text:'Chọn lại · tìm thấy '+matches.length+' chỗ'};
  if(parent&&roots.some(root=>relativeMatches(spec,root).filter(visible).length>1))return {ok:false,text:'Chọn lại · một khung khớp nhiều chỗ'};
  if(id==='productNumber'){
   const numbers=matches.map(readNumber);if(matches.length!==roots.length||numbers.some(x=>x===null)||new Set(numbers).size!==numbers.length)return {ok:false,text:'Không đọc được số riêng · dùng Chọn sản phẩm từ giỏ hiện tại'};
   return {ok:true,text:'Đọc được: '+numbers.slice(0,5).join(', ')};
  }
  if(id==='products'){if(matches.some(card=>actionButtons(card,'pin').length+unpinButtons(card,read()).length!==1))return {ok:false,text:'Chọn lại khung bao trọn một món và đúng một nút Ghim/Bỏ ghim'};return {ok:true,text:'Đọc được '+matches.length+' ô sản phẩm cùng nút Ghim/Bỏ ghim'};}
  if(['productTitle','bundleTitle'].includes(id)&&roots.some(root=>{const found=relativeMatches(spec,root).filter(visible);return found.length!==1||!found[0].textContent.trim();}))return {ok:false,text:'Chọn lại · có khung không đọc được tên riêng'};
  const text=(matches[0].textContent||matches[0].getAttribute('aria-label')||'').trim();
  if(id==='pinned'&&!/^(Đã ghim|Pinned|Bỏ ghim|Tháo ghim|Unpin|Ghim|Pin)$/i.test(text.replace(/^[^\p{L}\p{N}]+/u,'')))return {ok:false,text:'Không đọc được trạng thái · tự nhận nút Ghim/Bỏ ghim'};
  if(['account','live','productTitle','bundleTitle','user','text'].includes(id)&&!text)return {ok:false,text:'Chọn lại · đang đọc ra chữ rỗng'};
  return {ok:true,text:text?'Đọc được: '+text.slice(0,65):'Đã tìm thấy '+matches.length+' mục'};
 }catch(e){return {ok:false,text:'Chọn lại · vị trí không còn hợp lệ'};}
}
function refreshFields(){
 for(const box of ui.querySelectorAll('[data-time]'))$(box.dataset.time+'Display').textContent=$(box.dataset.time).value+' giây';
 for(const id of sharedFields){const result=inspectField(id,$(id).value),error=pickErrors.get(id);$(id+'Picked').textContent=error||result.text;$(id+'Picked').style.color=error||!result.ok?'#9a5614':'#267440';}
 $('pins').placeholder=$('productMode').value==='number'?'1\n3\n5':'Vietmap Live Pro\nBộ sạc 4 trong 1';
 try{const count=NBL.parse($('rules').value,'rule').length;$('rulesHint').textContent=count?'Đã nhập '+count+' quy tắc trả lời.':'Chưa có quy tắc. Chữ mẫu mờ không phải nội dung đã nhập.';}catch(e){$('rulesHint').textContent='Chưa dùng được quy tắc: '+e.message;}
}
const manager=new NBLModules.Modules();let activeModule='',tickBusy=false,connectionLost=false;
// 4.0.3: every reason a module stops goes to the error report.
{const stopModule=manager.stop.bind(manager);manager.stop=(key,error='')=>{if(error&&key!=='all'){const item=manager.items[key];if(item&&(item.running||item.error!==error))report('loi','Chrome · '+({pin:'Ghim sản phẩm',reply:'Trả lời bình luận'}[key]||key)+' đã dừng',error);}return stopModule(key,error);};}
let cfg={},running=false,busy=false,started=0,prev=-1,lastSend=0,done=new Set(),seen=new Set(),pending=[],snapshot='',timerLast=-1,replyAt=new Map(),suggestions=[];
// 4.0.3: what the tab did and what failed go to NBL's reports (bao_cao\hoat_dong / bao_cao\loi).
const reportQueue=[];
function report(kind,title,detail){reportQueue.push({kind,title:String(title).slice(0,200),detail:String(detail||'').slice(0,500)});if(reportQueue.length>20)reportQueue.shift();}
function takeReports(){return reportQueue.splice(0);}
const ACTIVITY=[[/^Đã ghim: (.*)/,'Chrome · Đã ghim sản phẩm'],[/^Đã tháo ghim: (.*)/,'Chrome · Đã tháo ghim sản phẩm'],[/^Đã thấy bình luận chủ phòng: (.*)/,'Chrome · Đã trả lời bình luận'],[/^Đã thêm bộ sản phẩm(.*)/,'Chrome · Đã thêm bộ sản phẩm'],[/^Đã tự đóng thông báo: (.*)/,'Chrome · Tự đóng thông báo'],[/^Giỏ hàng: (.*)/,'Chrome · Thêm giỏ chưa được','loi']];
const log=s=>{$('log').textContent=new Date().toLocaleTimeString()+' '+s+'\n'+$('log').textContent.slice(0,6500);for(const [re,title,kind] of ACTIVITY){const m=String(s).match(re);if(m){report(kind||'hoat_dong',title,m[1].trim());break;}}};
// 4.0.3: warning popups on the LIVE dashboard ("Phiên LIVE đã bị hạn chế", "Vi phạm
// của video LIVE"...) are closed with their own OK-type button so pinning and replies
// continue, instead of stopping both. Never clicked: captcha, security checks, ended
// LIVE, delete, log out, payment.
const NOTICE_TEXT=/vi phạm|hạn chế|cảnh báo|violation|restricted|warning/i;
const NEVER_CLOSE=/captcha|xác minh|verify|verification|kết thúc|\bhas ended\b|\blive ended\b|xóa|xoá|delete|đăng xuất|log ?out|thanh toán|payment/i;
const CLOSE_BUTTON=/^(OK|Đã hiểu|Tôi đã hiểu|Đóng|Bỏ qua|Để sau|Got it|Close)$/i;
const closedAt=new WeakMap();
function closeNotices(){
 if(typeof controlBusy!=='undefined'&&controlBusy)return;   // the tool's own "add bundle" dialog is open
 const dialogs=[...document.querySelectorAll('[role=dialog],[role=alertdialog],[role=alert],.arco-modal,.ant-modal')].filter(visible);
 const clicked=new Set();
 for(const d of dialogs){
  const text=(d.textContent||'').replace(/\s+/g,' ').trim();
  if(!NOTICE_TEXT.test(text)||NEVER_CLOSE.test(text))continue;
  const buttons=[...d.querySelectorAll('button,[role=button]')].filter(visible).filter(b=>buttonName(b).some(x=>CLOSE_BUTTON.test(x)));
  if(buttons.length!==1||clicked.has(buttons[0]))continue;
  const before=closedAt.get(d);
  if(before&&Date.now()-before<3000)continue;
  if(before&&Date.now()-before>=3000)throw Error('Thông báo trên trang không đóng được: '+text.slice(0,120));
  clicked.add(buttons[0]);closedAt.set(d,Date.now());buttons[0].click();log('Đã tự đóng thông báo: '+text.slice(0,160));
 }
}
function stillBlocked(){return [...document.querySelectorAll('[role=dialog],[role=alertdialog],[role=alert]')].filter(visible).find(e=>NEVER_CLOSE.test(e.textContent)&&/captcha|xác minh|verify|verification|Phiên LIVE đã kết thúc|LIVE has ended/i.test(e.textContent));}
function stop(reason='Đã dừng'){cancelControl();for(const s of sleepers)s.resolve();sleepers=[];manager.stop('all',reason.startsWith('Mất kết nối')?reason:'');running=false;pending=[];suggestions=[];renderSuggestions();renderModules();log(reason);}
function renderModules(){running=NBLModules.keys.some(k=>manager.items[k].running);$('modules').replaceChildren();for(const k of NBLModules.keys){const names={pin:'Ghim sản phẩm',reply:'Trả lời bình luận'},state=manager.items[k],row=document.createElement('div'),label=document.createElement('p'),on=document.createElement('button'),off=document.createElement('button');label.textContent=names[k]+': '+(state.error|| (state.running?(state.detail||'Đang kiểm tra'):'Đã dừng'));on.textContent='BẬT / THỬ LẠI';off.textContent='DỪNG';on.onclick=()=>startModule(k);off.onclick=()=>{manager.stop(k);renderModules();};row.append(label,on,off);$('modules').append(row);}$('state').textContent=running?'Đang chạy · chức năng độc lập':'Đã dừng';}
const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
function one(selector,base=document){if(!selector)throw Error('Chưa chọn vị trí trên trang');const a=relativeMatches(selector,base).filter(visible);if(a.length!==1)throw Error('Vị trí đã chọn phải khớp đúng một mục; hiện tìm được '+a.length);return a[0];}
function read(){return Object.fromEntries(fields.map(id=>[id,$(id).value.trim()]));}
function prepare(key){const c=read();if(!c.owner&&key!=='pin')throw Error('Nhập tên chủ phòng');
if(key==='pin'){c.pinJobs=NBLPins.parseProducts(c.pins,c.productMode);if(!c.pinJobs.length)throw Error('Chưa chọn sản phẩm muốn ghim');for(const pair of [['pinMin','pinMax'],['gapMin','gapMax']]){for(const id of pair)c[id]=Number(c[id]);NBLPins.validateRange(c[pair[0]],c[pair[1]]);}if(!c.products||!c.productTitle)throw Error('Chọn một ô sản phẩm và tên sản phẩm trước');}
if(key==='reply'){c.replyRules=NBL.parse(c.rules,'rule');if(!c.replyRules.length&&c.replyMode!=='suggest')throw Error('Chưa có câu trả lời theo từ khóa · nhập nội dung thật vào ô, chữ mẫu mờ chưa được tính');c.cooldown=Number(c.cooldown);if(!Number.isFinite(c.cooldown)||c.cooldown<15)throw Error('Nghỉ trả lời tối thiểu 15 giây');if(c.replyRules.some(x=>[...x.text].length>100))throw Error('Mỗi câu trả lời tối đa 100 ký tự');}return c;}
function startModule(key,override){void saveConfig().catch(e=>log('Chưa lưu: '+e.message));if(tickBusy)return 'Đang xác nhận thao tác trước; thử lại sau vài giây.';try{if(key==='reply'){suggestions=[];renderSuggestions();}if(override)for(const id of fields)if(override[id]!=null)$(id).value=String(override[id]);const state=manager.start(key,()=>{const c=prepare(key);cfg=c;identity();liveTime();if(key==='pin'){const cards=productCards();if(!cards.length)log('Giỏ đang trống; chờ sản phẩm xuất hiện.');else{for(const job of c.pinJobs)pin(job);}}else{one(c.input);one(c.send);chat();if(!c.rows||!c.user||!c.text)throw Error('Chọn tên khách và câu hỏi trong dòng bình luận trước');}return c;});cfg=state.config;state.snapshot=identity();state.timerLast=liveTime();state.pinCycle=new NBLPins.Cycle(state.config.pinJobs||[]);state.nextPinAt=Date.now();state.detail=key==='pin'?'Đang kiểm tra món đã chọn':'Đang chờ bình luận mới';state.seen=new Set(key==='pin'?[]:chat().map(keyOf));connectionLost=false;renderModules();log('Bật '+key);return '';}catch(e){manager.stop(key,e.message);renderModules();log(key+': '+e.message);return e.message;}}
function identity(){return one(cfg.account).textContent.trim();}
function liveTime(){const s=one(cfg.live).textContent.match(/\b\d{2,}:\d{2}:\d{2}\b/);if(!s)throw Error('Không đọc được đồng hồ LIVE');return NBL.seconds(s[0]);}
const rowKeys=new WeakMap();let nextRowKey=0;
// 4.0: a row without its own name/question (system line, gift, pinned notice) is skipped
// instead of stopping the whole reply module; only a fully unreadable chat is an error.
function chat(){if(!cfg.rows)return [];const rows=[...document.querySelectorAll(cfg.rows)].filter(visible);let bad=0;const out=[];for(const row of rows){let result;try{result={user:one(cfg.user,row).textContent.trim(),text:one(cfg.text,row).textContent.trim()};}catch(e){bad++;continue;}if(!result.user||!result.text){bad++;continue;}if(!rowKeys.has(row))rowKeys.set(row,++nextRowKey);Object.defineProperty(result,'key',{value:rowKeys.get(row)+'\u0000'+result.user+'\u0000'+result.text});out.push(result);}if(rows.length>=3&&!out.length)throw Error('Không đọc được tên/câu hỏi ở dòng bình luận nào; chọn lại vị trí trong dòng bình luận.');return out;}
function keyOf(r){return r.key||r.user+'\u0000'+r.text;}
function assertContext(){closeNotices();const warning=stillBlocked();if(warning)throw Error('Trang yêu cầu chú ý (captcha / xác minh / LIVE đã kết thúc); dừng mục và kiểm tra.');if(location.pathname!='/streamer/live/product/dashboard')throw Error('Đã rời bảng LIVE');if(identity()!==snapshot)throw Error('Tài khoản đã đổi');const t=liveTime();if(t<timerLast)throw Error('Đồng hồ LIVE quay lại: có thể đã đổi phiên');timerLast=t;}
function productCards(){return [...document.querySelectorAll(cfg.products)].filter(visible);}
function bindings(){try{const data=JSON.parse(cfg.productBindings||'[]');return Array.isArray(data)?data.filter(x=>Number.isSafeInteger(x.number)&&x.number>0&&typeof x.key==='string'&&typeof x.title==='string'):[];}catch(e){throw Error('Danh sách món đã chọn bị lỗi; bấm Chọn sản phẩm từ giỏ hiện tại rồi tích lại.');}}
function cardKey(card){const title=one(cfg.productTitle,card).textContent.trim();if(!title)throw Error('Tên sản phẩm đang rỗng; chọn lại Tên sản phẩm trong ô.');const id=card.getAttribute('data-product-id')||card.getAttribute('data-id');return id?'id:'+id:'title:'+NBL.norm(title);}
function pin(product){
 const cards=productCards();
 if(product.mode==='number'){
  // 4.1: numbers are the cart order of THIS LIVE (owner, 19/10/2026): the set is
  // added fresh each LIVE with the main products on top. Saved bindings from an
  // older cart are not used, they would point at products of another set.
  if(cfg.productNumber&&cards.length){const rows=cards.map(card=>{const labels=relativeMatches(cfg.productNumber,card).filter(visible);return {card,number:labels.length===1?readNumber(labels[0]):null};});
   if(rows.every(x=>x.number!==null)&&new Set(rows.map(x=>x.number)).size===rows.length)return rows.find(x=>x.number===product.number)?.card||null;}
  return cards[product.number-1]||null;
 }
 const matches=cards.filter(card=>{const titles=relativeMatches(cfg.productTitle,card).filter(visible);return titles.length===1&&NBL.norm(titles[0].textContent).includes(NBL.norm(product.text));});if(matches.length>1)throw Error('Tên khớp nhiều sản phẩm: '+product.text);return matches[0]||null;
}
function unpinButtons(card,c=cfg){const automatic=actionButtons(card,'unpin');if(automatic.length)return automatic;if(actionButtons(card,'pin').length)return [];if(!c.unpinButton)return [];return relativeMatches(c.unpinButton,card).filter(visible).map(sendTarget);}
function pinned(card){
 if(!card)return false;
 if(actionButtons(card,'unpin').length)return true;
 if(actionButtons(card,'pin').length)return false;
 const label=cfg.pinned?relativeMatches(cfg.pinned,card).filter(visible):[];
 if(label.length===1&&/^(đã ghim|pinned)$/i.test(label[0].textContent.trim()))return true;
 if(label.length===1&&/^(chưa ghim|not pinned)$/i.test(label[0].textContent.trim()))return false;
 throw Error('Chưa nhận được nút Ghim/Bỏ ghim trong ô sản phẩm; chọn lại khung bao trọn tên và nút.');
}
function productIdentity(card){const title=one(cfg.productTitle,card).textContent.trim();return {card,title,key:card.getAttribute('data-product-id')||card.getAttribute('data-id')||NBL.norm(title)};}
function trackedCard(item){if(!item)return null;if(item.card.isConnected&&productCards().includes(item.card)&&productIdentity(item.card).key===item.key)return item.card;const matches=productCards().filter(c=>productIdentity(c).key===item.key);if(matches.length>1)throw Error('Không phân biệt được sản phẩm đang ghim');return matches[0]||null;}
let sleepers=[];
const delay=ms=>new Promise(resolve=>sleepers.push({at:Date.now()+ms,resolve}));
function pulse(){const now=Date.now(),due=sleepers.filter(s=>s.at<=now);sleepers=sleepers.filter(s=>s.at>now);for(const s of due)s.resolve();}
async function wait(test){const end=Date.now()+8000;while(Date.now()<end){if(!manager.items[activeModule]?.running)throw Error('Mục đã dừng');assertContext();if(test())return;await delay(250);}throw Error('Không xác nhận được kết quả, dừng để tránh gửi/ghim lặp');}
function inputText(input){return input.value??input.textContent;}
function changeInput(input,text){if(input instanceof HTMLInputElement||input instanceof HTMLTextAreaElement){const proto=input instanceof HTMLInputElement?HTMLInputElement.prototype:HTMLTextAreaElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(input,text);}else input.textContent=text;input.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text}));}
async function send(text){assertContext();const before=chat().filter(r=>r.user===cfg.owner&&r.text===text).length;const input=one(cfg.input);if(inputText(input).trim())throw Error('Ô nhập đang có chữ của bạn, không ghi đè');if([...text].length>100)throw Error('Câu vượt 100 ký tự');const state=manager.items[activeModule],generation=state.generation;let submitted=false;
try{input.focus();changeInput(input,text);await delay(250);if(!state.running||state.generation!==generation)return;assertContext();if(inputText(input)!==text)throw Error('Ô nhập đã được thay đổi; dừng để giữ chữ của bạn.');const button=sendTarget(one(cfg.send));if(button.disabled||button.getAttribute('aria-disabled')==='true')throw Error('Nút gửi chưa hoạt động');button.click();submitted=true;lastSend=Date.now();await wait(()=>chat().filter(r=>r.user===cfg.owner&&r.text===text).length>before);log('Đã thấy bình luận chủ phòng: '+text);}
finally{if(!submitted&&inputText(input)===text)changeInput(input,'');}}
async function doPin(product){assertContext();const card=pin(product);if(!card)return null;const item=productIdentity(card);if(!pinned(card)){const buttons=actionButtons(card,'pin');if(buttons.length!==1)throw Error('Chưa tìm được nút Ghim trong ô sản phẩm');if(buttons[0].disabled||buttons[0].getAttribute('aria-disabled')==='true')throw Error('Nút ghim đang bị khóa');buttons[0].click();await wait(()=>pinned(trackedCard(item)));}log('Đã ghim: '+item.title);return item;}
async function doUnpin(item){assertContext();const card=trackedCard(item);if(!card)throw Error('Sản phẩm đang ghim không còn trong danh sách; chưa xác nhận tháo ghim');if(!pinned(card))return;let buttons=unpinButtons(card);if(buttons.length!==1)throw Error('Chưa tìm được nút Bỏ ghim trong ô sản phẩm');const button=sendTarget(buttons[0]);if(button.disabled||button.getAttribute('aria-disabled')==='true')throw Error('Nút Bỏ ghim đang bị khóa');button.click();await wait(()=>{const current=trackedCard(item);return current&&!pinned(current);});log('Đã tháo ghim: '+item.title);}
function sendTarget(el){if(el instanceof SVGElement)el=el.closest('button,[role=button]')||el.closest('svg').parentElement;if(!el||typeof el.click!=='function')throw Error('Chọn nút gửi hoặc phần bao quanh biểu tượng gửi');return el;}
function relative(el,parent){const parts=[];while(el&&el!==parent){let s=el.tagName.toLowerCase();const peers=[...el.parentElement.children].filter(x=>x.tagName===el.tagName);if(peers.length>1)s+=':nth-of-type('+(peers.indexOf(el)+1)+')';parts.unshift(s);el=el.parentElement;}if(!parts.length){if(el===parent)return ':scope';throw Error('Hãy bấm bên trong khung đã chọn');}return ':scope>'+parts.join('>');}
function clearCatalog(id){if(['products','productTitle','productNumber'].includes(id)){$('productBindings').value='';$('productChoices').replaceChildren();}}
function commitPick(id,spec){
 const result=inspectField(id,spec);if(!result.ok)throw Error(result.text);
 $(id).value=spec;pickErrors.delete(id);clearCatalog(id);refreshFields();
 void chrome.storage.local.set({nblSharedSetup:Object.fromEntries(sharedFields.map(k=>[k,$(k).value]))});void saveConfig();log(setupLabels[id]+': '+result.text);
}
for(const button of ui.querySelectorAll('[data-relative]'))button.onclick=()=>{
 if(running||controlBusy){log('Dừng các mục trước khi chọn lại vị trí.');return;}
 const id=button.dataset.relative;log(id==='bundleTitle'?'Mở bảng bộ sản phẩm trước, rồi bấm đúng tên bộ bên trong khung đã chọn.':'Bấm vị trí cần đọc trên trang; nhấn Esc để hủy.');$('body').hidden=true;
 const click=e=>{if(e.composedPath().includes(host))return;e.preventDefault();e.stopImmediatePropagation();try{
  let target=e.target;const spec=$(button.dataset.parent).value;if(!spec)throw Error('Chọn khung bao quanh trước rồi mới chọn chữ bên trong.');
  if(id==='pinned')target=target.closest('button,[role=button]')||target;
  const parent=target.closest(spec);if(!parent)throw Error('Chưa mở đúng bảng hoặc khung đã chọn không bao quanh chữ này.');
  commitPick(id,relative(target,parent));
 }catch(err){pickErrors.set(id,'Chưa chọn được · '+err.message);refreshFields();log(err.message);}clean();};
 const esc=e=>{if(e.key==='Escape')clean();};function clean(){document.removeEventListener('click',click,true);document.removeEventListener('keydown',esc,true);$('body').hidden=false;}
 document.addEventListener('click',click,true);document.addEventListener('keydown',esc,true);
};
function selector(el,repeated=false){if(repeated){const classes=[...el.classList].filter(x=>!x.includes('active')&&!x.includes('selected'));if(classes.length)return el.tagName.toLowerCase()+classes.map(x=>'.'+CSS.escape(x)).join('');}if(el.id)return '#'+CSS.escape(el.id);const parts=[];while(el&&el!==document.documentElement){let s=el.tagName.toLowerCase();const peers=[...el.parentElement.children].filter(x=>x.tagName===el.tagName);if(peers.length>1)s+=':nth-of-type('+(peers.indexOf(el)+1)+')';parts.unshift(s);el=el.parentElement;}return 'html>'+parts.join('>');}
for(const button of ui.querySelectorAll('[data-pick]'))button.onclick=()=>{if(running||controlBusy){log('Dừng các mục trước khi chọn lại nút.');return;}const id=button.dataset.pick;log('Bấm đúng vị trí trên trang; nhấn Esc để hủy.');$('body').hidden=true;let target=null,originalOutline='',chooser=null;
function highlight(next){if(target)target.style.outline=originalOutline;target=next;originalOutline=target.style.outline;target.style.outline='3px solid #ff8c30';}
function save(){if(!target)return;try{commitPick(id,selector(target,['rows','products','bundleCards'].includes(id)));}catch(e){pickErrors.set(id,'Chưa chọn được · '+e.message);refreshFields();log(e.message);}clean();}
const click=e=>{if(e.composedPath().includes(host))return;e.preventDefault();e.stopImmediatePropagation();let chosen=e.target;if(id==='send'||id==='bundleOpen'||id==='bundleConfirm')chosen=sendTarget(chosen);highlight(chosen);if(!['rows','products','bundleCards'].includes(id)){save();return;}document.removeEventListener('click',click,true);chooser=document.createElement('div');const text=document.createElement('p');text.textContent='Chọn khung bao quanh đúng một '+(id==='rows'?'bình luận gồm tên và câu hỏi':id==='products'?'sản phẩm gồm tên và nút Ghim':'bộ sản phẩm')+'. Khung đang chọn có viền cam.';chooser.append(text);for(const [name,fn] of [['Khung lớn hơn',()=>{if(target.parentElement&&target.parentElement!==document.body&&target.parentElement!==document.documentElement)highlight(target.parentElement);}],['Dùng khung này',save],['Hủy',clean]]){const b=document.createElement('button');b.textContent=name;b.onclick=fn;chooser.append(b);}ui.querySelector('section').append(chooser);};
const esc=e=>{if(e.key==='Escape')clean();};function clean(){document.removeEventListener('click',click,true);document.removeEventListener('keydown',esc,true);if(target)target.style.outline=originalOutline;chooser?.remove();$('body').hidden=false;}document.addEventListener('click',click,true);document.addEventListener('keydown',esc,true);};
$('fold').onclick=()=>{$('body').hidden=!$('body').hidden;$('fold').textContent=$('body').hidden?'Mở':'Thu';};
let saveTail=Promise.resolve(),lastSaved='',lastAppAck='',boundAccount='',switchBusy=false;
async function switchAccount(account){if(switchBusy)return;switchBusy=true;stop('Đã đổi nick; tải nội dung của nick đang mở');boundAccount=account;try{const stored=await chrome.storage.local.get(['nblAccount:'+account,'nblSharedSetup']);const own=stored['nblAccount:'+account]||{owner:account,rules:'',pins:'',bundleName:'',productMode:'number'};for(const id of fields)if(!sharedFields.includes(id))$(id).value=String(own[id]??(id==='owner'?account:id==='productBindings'?'':id==='productMode'?'number':['rules','pins','bundleName'].includes(id)?'':$(id).value));for(const id of sharedFields)if(stored.nblSharedSetup?.[id])$(id).value=stored.nblSharedSetup[id];refreshFields();lastSaved='';}finally{switchBusy=false;}}
function saveConfig(){if(switchBusy)return Promise.resolve();const c=read(),serialized=JSON.stringify(c);if(serialized===lastSaved)return saveTail;saveTail=saveTail.catch(()=>{}).then(async()=>{let account='';try{account=one(c.account).textContent.trim();}catch(e){}if(account&&boundAccount&&account!==boundAccount){void switchAccount(account);return;}if(account)boundAccount=account;const values={nblConfig:c};if(account)values['nblAccount:'+account]=c;await chrome.storage.local.set(values);lastSaved=serialized;});return saveTail;}
function stopForEdit(id){
 const pinFields=new Set(['pins','productMode','productBindings','pinMin','pinMax','gapMin','gapMax','products','productTitle','productNumber','pinned','unpinButton']);
 const replyFields=new Set(['owner','rules','replyMode','cooldown','input','send','rows','user','text']);
 for(const key of NBLModules.keys){if(manager.items[key].running&&(id==='account'||id==='live'||(key==='pin'?pinFields:replyFields).has(id))){manager.stop(key,'Đã đổi thiết lập · bấm BẬT / THỬ LẠI để dùng bản mới');if(key==='reply'){suggestions=[];renderSuggestions();}log('Đã lưu thay đổi; bật lại '+key+' để áp dụng.');}}
 renderModules();
}
for(const id of fields)$(id).addEventListener('change',()=>{stopForEdit(id);refreshFields();if(sharedFields.includes(id)){pickErrors.delete(id);clearCatalog(id);}if(sharedFields.includes(id))void chrome.storage.local.set({nblSharedSetup:Object.fromEntries(sharedFields.map(k=>[k,$(k).value]))});void saveConfig().catch(e=>log('Chưa lưu: '+e.message));});
$('shareSetup').onclick=()=>chrome.storage.local.set({nblSharedSetup:Object.fromEntries(sharedFields.map(k=>[k,$(k).value]))}).then(()=>log('Đã lưu cách chọn nút dùng chung giữa các nick.'));
$('useShared').onclick=async()=>{if(running||controlBusy){log('Dừng các mục trước khi đổi cách chọn nút.');return;}const saved=await chrome.storage.local.get('nblSharedSetup');for(const [k,v] of Object.entries(saved.nblSharedSetup||{}))if(sharedFields.includes(k))$(k).value=v;refreshFields();await saveConfig();log('Đã dùng cách chọn nút chung; giữ nguyên nội dung nick này.');};
$('rules').addEventListener('input',refreshFields);
$('productMode').addEventListener('change',()=>{$('productChoices').replaceChildren();$('pins').value='';void saveConfig();log('Đã đổi cách chọn. Bấm Chọn sản phẩm từ giỏ hiện tại rồi tích lại món.');});
$('readProducts').onclick=()=>{
 if(running||controlBusy){log('Dừng Ghim và Trả lời trước khi đọc lại giỏ; tránh đổi danh sách giữa một lần ghim.');return;}
 const before=cfg;try{
  cfg=read();const cards=productCards(),area=$('productChoices');area.replaceChildren();
  if(!cards.length){log('Chưa đọc được sản phẩm. Chọn lại khung một ô sản phẩm bao trọn tên và nút.');return;}
  const rows=cards.map((card,index)=>{const title=one(cfg.productTitle,card).textContent.trim(),key=cardKey(card);let number=null;if(cfg.productNumber){const labels=relativeMatches(cfg.productNumber,card).filter(visible);if(labels.length===1)number=readNumber(labels[0]);}return {title,key,number,index};});
  const native=rows.every(x=>x.number!==null)&&new Set(rows.map(x=>x.number)).size===rows.length;
  const keys=rows.map(x=>x.key);if(new Set(keys).size!==keys.length)throw Error('Hai ô sản phẩm không phân biệt được. Chọn lại khung từng món có mã riêng.');
  const old=bindings();const selected=NBLPins.parseProducts(cfg.pins,cfg.productMode);const chosenKeys=new Set(selected.flatMap(job=>job.mode==='name'?rows.filter(x=>NBL.norm(x.title)===NBL.norm(job.text)).map(x=>x.key):old.some(x=>x.number===job.number)?old.filter(x=>x.number===job.number).map(x=>x.key):[]));
  const catalog=rows.map((x,i)=>({...x,number:native?x.number:i+1,source:native?'page':'nbl'}));
  $('productBindings').value=JSON.stringify(catalog.map(({number,key,title,source})=>({number,key,title,source})));
  // Preserve prior numeric selection only when page numbers are actually verified.
  if(native&&!old.length)for(const job of selected)if(job.mode==='number'){const row=catalog.find(x=>x.number===job.number);if(row)chosenKeys.add(row.key);}
  const selectedValues=catalog.filter(x=>chosenKeys.has(x.key)).map(x=>cfg.productMode==='number'?String(x.number):x.title);$('pins').value=selectedValues.join('\n');
  for(const row of catalog){const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.style.width='auto';check.checked=chosenKeys.has(row.key);const value=cfg.productMode==='number'?String(row.number):row.title;label.append(check,document.createTextNode((native?' #':' Số NBL #')+row.number+' · '+row.title));
   check.onchange=()=>{const chosen=new Set($('pins').value.split($('productMode').value==='number'?/[\n,;]+/:/\n+/).map(x=>x.trim()).filter(Boolean));if(check.checked)chosen.add(value);else chosen.delete(value);$('pins').value=[...chosen].join('\n');$('pins').dispatchEvent(new Event('change'));};area.append(label);
  }
  void saveConfig();refreshFields();log(native?'Đã đọc '+rows.length+' món và số trên trang; tích các món muốn ghim.':'Không đọc được số trên trang. Đã đánh số NBL và nhớ từng món; hãy tích lại món muốn ghim.');
 }catch(e){log(e.message);}finally{cfg=before;}
};

$('save').onclick=()=>saveConfig().then(()=>log('Đã lưu Chrome; app tự lưu khi đang kết nối.')).catch(e=>log(e.message));
$('check').onclick=()=>{refreshFields();if(tickBusy){log('Chờ thao tác đang chạy xác nhận xong.');return;}for(const k of NBLModules.keys){try{const c=prepare(k);cfg=c;log(k+': tài khoản '+identity()+'; LIVE '+liveTime());if(k==='pin'){const found=c.pinJobs.filter(j=>pin(j)).length;log('Tìm thấy '+found+'/'+c.pinJobs.length+' món đã chọn; món thiếu sẽ bỏ qua');if(!found)throw Error('Chưa tìm được món nào đã chọn; đọc lại giỏ rồi tích món.');}else{one(c.input);one(c.send);chat();}log(k+': kiểm tra đọc trang đạt');}catch(e){log(k+': '+e.message);}}};
$('stop').onclick=()=>stop();
$('start').onclick=()=>{for(const k of NBLModules.keys)startModule(k);};
async function tick(){if(tickBusy||!running||connectionLost||controlBusy)return;tickBusy=true;try{
 for(const module of NBLModules.keys)await manager.guard(module,async state=>{
 if(connectionLost)return;activeModule=module;cfg=state.config;snapshot=state.snapshot;timerLast=state.timerLast;assertContext();state.timerLast=timerLast;
 const elapsed=(Date.now()-state.started)/1000;
 if(module==='pin'){
  if(Date.now()>=state.nextPinAt){const cycle=state.pinCycle,generation=state.generation;
   if(cycle.phase==='hold'){await doUnpin(cycle.current);if(!state.running||generation!==state.generation)return;const seconds=cycle.afterUnpin(cfg.gapMin,cfg.gapMax);state.nextPinAt=Date.now()+seconds*1000;state.detail='Đang nghỉ không ghim · '+seconds+' giây';log('Nghỉ không ghim sản phẩm trong '+seconds+' giây');}
   else{let choice=null,fallback=null;for(let attempt=0;attempt<cfg.pinJobs.length;attempt++){const candidate=cycle.next(),card=pin(candidate);if(!card)continue;if(productIdentity(card).key===state.lastProductKey){fallback=candidate;continue;}choice=candidate;break;}choice=choice||fallback;const item=choice?await doPin(choice):null;if(!state.running||generation!==state.generation)return;if(item){state.lastProductKey=item.key;const seconds=cycle.afterPin(item,cfg.pinMin,cfg.pinMax);state.nextPinAt=Date.now()+seconds*1000;state.detail='Đang giữ ghim: '+item.title;log('Giữ sản phẩm trong '+seconds+' giây');}else{state.nextPinAt=Date.now()+30000;state.detail='Đang chờ món đã chọn · chưa ghim được món nào';log('Chưa có món đã chọn trong giỏ; thử đọc lại sau 30 giây');}}
  }
 }else{
  for(const r of chat()){const k=keyOf(r);if(state.seen.has(k))continue;state.seen.add(k);if(state.seen.size>5000)state.seen.delete(state.seen.values().next().value);if(r.user===cfg.owner||r.user.includes('Chủ phòng'))continue;const response=NBL.answer(cfg.replyRules,r.text);
   if(Date.now()-(state.replyAt.get(r.user)||0)<cfg.cooldown*1000)continue;
   if(response||cfg.replyMode==='suggest'){state.replyAt.set(r.user,Date.now());if(state.replyAt.size>5000)state.replyAt.delete(state.replyAt.keys().next().value);if(cfg.replyMode==='suggest')addSuggestion(r,response||'Anh/chị muốn hỏi sản phẩm nào trong giỏ ạ?');else if(state.pending.length<20)state.pending.push({text:response,expires:Date.now()+60000});}
  }
 }
 state.prev=elapsed;if(state.done.size>2000)state.done=new Set([...state.done].slice(-500));state.pending=state.pending.filter(j=>j.expires>Date.now());
 if(module!=='pin'&&state.running&&state.pending.length&&Date.now()-lastSend>=15000){const job=state.pending.shift();await send(job.text);}
 });
 renderModules();
 }finally{tickBusy=false;activeModule='';}}
// Work is triggered by app -> service worker -> content messages, never a hidden-tab interval.
let controlResult={};let controlBusy=false;let controlEpoch=0;let controlOwner=0;
function cancelControl(){controlEpoch++;if(controlBusy&&controlResult.state==='running')controlResult={...controlResult,state:'cancelled',error:'Đã dừng thêm giỏ'};}
// 4.1: cart preparation BEFORE the LIVE (owner's decisions 19/10/2026): the app picks
// "bộ số N" (1 = first set from the top); a cart that already has products is left
// alone; a partial add ("Đã thêm 8/10", sold-out items) counts as success.
function textOf(el){return (el&&(el.innerText||el.textContent)||'').replace(/\s+/g,' ').trim();}
function clickables(root=document){return [...root.querySelectorAll('button,[role=button],[role=tab],a,.arco-tabs-header-title,.arco-btn')].filter(visible);}
function byText(re,root=document){return clickables(root).filter(el=>re.test(textOf(el)));}
function safeOne(spec){try{return spec?one(spec):null;}catch(e){return null;}}
function addDrawer(){return [...document.querySelectorAll('[role=dialog],.arco-drawer,.ant-drawer,.arco-modal')].filter(visible).find(d=>/Thêm sản phẩm mới|Add new products?/i.test(textOf(d)))||null;}
function emptyCart(){return [...document.querySelectorAll('div,p,span')].filter(visible).some(e=>e.children.length===0&&/^Chưa có sản phẩm$|^No products( yet)?$/i.test(textOf(e)));}
function cartCount(c){if(c.products){const old=cfg;cfg=c;try{const n=productCards().length;if(n)return n;}catch(e){}finally{cfg=old;}}
 if(emptyCart())return 0;const list=[...document.querySelectorAll('div,p,span')].filter(visible).find(e=>e.children.length===0&&/^Danh sách sản phẩm trong LIVE này$/i.test(textOf(e)));return list?1:-1;}
function closeIconIn(root){const box=root.getBoundingClientRect();
 const found=[...root.querySelectorAll('[aria-label],[title],[class*=close i]')].filter(visible).filter(el=>/close|đóng/i.test([el.getAttribute('aria-label'),el.getAttribute('title'),String(el.className&&el.className.baseVal!==undefined?el.className.baseVal:el.className)].join(' ')))
  .map(el=>el.closest('button,[role=button],[class*=close i]')||el).filter(el=>{const r=el.getBoundingClientRect();return r.width<=64&&r.height<=64&&r.top-box.top<120;});
 const unique=[...new Set(found)];unique.sort((a,b)=>{const ra=a.getBoundingClientRect(),rb=b.getBoundingClientRect();return (rb.right-rb.top)-(ra.right-ra.top);});return unique[0]||null;}
function pressEscape(root){const targets=[root,document.activeElement,document].filter(Boolean);for(const t of [...new Set(targets)])for(const type of ['keydown','keyup'])t.dispatchEvent(new KeyboardEvent(type,{key:'Escape',code:'Escape',keyCode:27,bubbles:true}));}
// 4.1.3: the end-of-LIVE "Chúc mừng…" box was not always a [role=dialog]/.arco-modal
// and its X is a bare icon, so it stayed open (owner, 19/10/2026 03:33). Find it by
// its text, climb to the box, and click the X like a real mouse (pointer + click).
const SUMMARY_TEXT=/Chúc mừng bạn đã hoàn thành|Chúc mừng|Phiên LIVE đã kết thúc|LIVE (has )?ended|Congratulations/i;
function summaryDialog(){
 const direct=[...document.querySelectorAll('[role=dialog],.arco-modal,[class*=modal i],[class*=dialog i]')].filter(visible).filter(d=>SUMMARY_TEXT.test(textOf(d)));
 if(direct.length){direct.sort((a,b)=>textOf(a).length-textOf(b).length);return direct[0];}
 const heads=[...document.querySelectorAll('h1,h2,h3,h4,div,span,p')].filter(el=>el.children.length===0&&/Chúc mừng bạn đã hoàn thành/i.test(textOf(el))).filter(visible);
 for(const head of heads){let el=head;for(let i=0;i<10&&el&&el!==document.body;i++){el=el.parentElement;if(!el)break;const r=el.getBoundingClientRect();if(r.width>=320&&r.height>=200)return el;}}
 return null;}
function fireClick(el){const r=el.getBoundingClientRect(),o={bubbles:true,cancelable:true,view:window,clientX:r.left+r.width/2,clientY:r.top+r.height/2,button:0};
 for(const type of ['pointerdown','mousedown','pointerup','mouseup']){try{el.dispatchEvent(new (type.startsWith('pointer')&&typeof PointerEvent==='function'?PointerEvent:MouseEvent)(type,o));}catch(e){}}
 if(typeof el.click==='function')el.click();else el.dispatchEvent(new MouseEvent('click',o));}
function cornerX(root){const box=root.getBoundingClientRect();
 const small=[...root.querySelectorAll('button,[role=button],svg,i,span')].filter(visible).filter(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.width<=40&&r.height<=40&&box.right-r.right<=60&&r.top-box.top<=60&&!textOf(el);});
 small.sort((a,b)=>{const ra=a.getBoundingClientRect(),rb=b.getBoundingClientRect();return (ra.top-box.top+box.right-ra.right)-(rb.top-box.top+box.right-rb.right);});
 const el=small[0];return el?(el.closest('button,[role=button]')||el):null;}
async function closeSummary(){const dialog=summaryDialog();if(!dialog)return false;
 const names=/^(Đóng|Xong|Hoàn tất|OK|Close|Done)$/i;
 const targets=[clickables(dialog).find(b=>[textOf(b),b.getAttribute('aria-label')||'',b.getAttribute('title')||''].some(x=>names.test(x.trim()))),closeIconIn(dialog),cornerX(dialog)].filter(Boolean);
 for(const target of [...new Set(targets),'esc']){
  if(target==='esc'){pressEscape(dialog);}else{try{fireClick(target);}catch(e){continue;}}
  for(let i=0;i<8;i++){await delay(300);if(!summaryDialog()){log('Đã đóng bảng tổng kết LIVE');report('hoat_dong','Chrome · Đã đóng bảng tổng kết LIVE','');return true;}}
 }
 throw Error('Chưa đóng được bảng tổng kết LIVE trên Chrome');}
// 4.1.5: empty the cart before a schedule adds its own set. "Tất cả" (select all) in
// the product list → the remove button that appears → confirm. Any step missing:
// leave the cart as it is (the new set still goes on TOP, so pin numbers 1, 2, 3…
// are the new set) and say so.
async function clearCart(c,valid){
 const inPanel=el=>!el.closest('[role=dialog],.arco-drawer,.arco-modal');
 const boxes=[...document.querySelectorAll('label,[class*=checkbox i]')].filter(visible).filter(inPanel).filter(el=>/^(Tất cả|Chọn tất cả|Select all|All)$/i.test(textOf(el))&&(el.querySelectorAll('input[type=checkbox]').length||/checkbox/i.test(String(el.className))));
 const all=boxes[0];
 if(boxes.length!==1){log('Chưa thấy ô "Tất cả" của giỏ; thêm bộ mới lên đầu giỏ.');report('loi','Chrome · Chưa xoá được giỏ cũ','Không thấy ô Tất cả; bộ mới được thêm lên đầu giỏ');return false;}
 fireClick(all);
 const removeRe=/^(Xóa|Xoá|Gỡ|Gỡ bỏ|Xóa sản phẩm|Xoá sản phẩm|Gỡ sản phẩm|Remove|Delete)(\s*\(?\d+\)?)?$/i;
 const btn=await waitFor(()=>clickables().filter(inPanel).find(b=>removeRe.test(textOf(b))&&!b.disabled)||null,3000,valid);
 if(!btn){fireClick(all);log('Chưa thấy nút xoá giỏ; thêm bộ mới lên đầu giỏ.');report('loi','Chrome · Chưa xoá được giỏ cũ','Không thấy nút Xoá sau khi chọn Tất cả');return false;}
 fireClick(btn);
 const okRe=/^(Xóa|Xoá|Gỡ|Gỡ bỏ|Xác nhận|Đồng ý|OK|Delete|Remove|Confirm)$/i;
 const ok=await waitFor(()=>{const d=[...document.querySelectorAll('[role=dialog],[role=alertdialog],.arco-modal,.arco-popconfirm,[class*=popconfirm i],[class*=modal i]')].filter(visible);
  for(const x of d){const b=clickables(x).find(b=>okRe.test(textOf(b)));if(b)return b;}return null;},3000,valid);
 if(ok)fireClick(ok);
 const gone=await waitFor(()=>cartCount(c)===0?true:null,10000,valid);
 if(!gone){log('Chưa xoá hết giỏ cũ; thêm bộ mới lên đầu giỏ.');report('loi','Chrome · Chưa xoá hết giỏ cũ','Bộ mới được thêm lên đầu giỏ');return false;}
 log('Đã xoá giỏ cũ của lịch trước.');report('hoat_dong','Chrome · Đã xoá giỏ cũ trước khi thêm bộ mới','');return true;}
// Closed whenever it shows up (also when the app's "finish" command came too early).
let summaryTriedAt=0,summaryWarned=false;
function autoCloseSummary(){if(controlBusy||Date.now()-summaryTriedAt<5000||!summaryDialog())return;summaryTriedAt=Date.now();
 closeSummary().then(()=>{summaryWarned=false;}).catch(e=>{if(!summaryWarned){summaryWarned=true;log(e.message);report('loi','Chrome · '+e.message,'');}});}
function bundleRows(d){const radios=[...d.querySelectorAll('input[type=radio]')].map(r=>r.closest('label,[role=radio],.arco-radio')||r);
 const roles=radios.length?radios:[...d.querySelectorAll('[role=radio],.arco-radio')];
 return [...new Set(roles)].filter(el=>visible(el)||visible(el.parentElement));}
function rowTitle(radio){let el=radio;for(let i=0;i<6&&el;i++){el=el.parentElement;const t=textOf(el);if(/sản phẩm|products?/i.test(t))return t.split(/\d+\s*sản phẩm|\d+\s*products?/i)[0].replace(/[>›]\s*$/,'').trim().slice(0,120);}return '';}
function nextPage(d){return [...d.querySelectorAll('.arco-pagination-item-next,[aria-label*=next i],[class*=next i]')].filter(visible).find(el=>!el.disabled&&!/disabled/i.test(String(el.className))&&el.getAttribute('aria-disabled')!=='true')||null;}
async function waitFor(test,ms,valid){const end=Date.now()+ms;while(Date.now()<end){valid();const r=test();if(r)return r;await delay(250);}return null;}
async function prepareBundle(command){const generation=++controlEpoch;controlOwner=generation;controlBusy=true;controlResult={id:command.id,state:'running'};const c=read();
 const valid=()=>{if(generation!==controlEpoch||connectionLost||Date.now()>command.deadline*1000)throw Error('Đã hủy hoặc hết thời gian thêm giỏ');if(command.expectedAccount&&one(c.account).textContent.trim()!==command.expectedAccount)throw Error('Nick trên Chrome khác nick của lịch; không thêm giỏ');};
 try{valid();
  if(!command.preLive){const oldCfg=cfg;cfg=c;try{liveTime();}finally{cfg=oldCfg;}}
  try{await closeSummary();}catch(e){log(e.message);}valid();
  const count=cartCount(c);
  // 4.1.5 (owner, 19/10/2026 04:40): several schedules saved at once — the next one
  // found the PREVIOUS schedule's products still in the cart, skipped, and never
  // added its own set. Now a schedule with a set number REPLACES the cart (remove
  // all, then add its set). "Bộ số 0" = keep the cart the owner filled by hand.
  if(command.keepCart){
   if(count>0){controlResult={id:command.id,state:'done',skipped:'cart',count};log('Giữ giỏ đang có (lịch chọn giữ giỏ tự thêm tay).');report('hoat_dong','Chrome · Giữ giỏ đang có, không thêm bộ','');return;}
   throw Error('Giỏ đang trống mà lịch chọn "giữ giỏ tự thêm tay"; thêm sản phẩm vào giỏ hoặc chọn bộ số');}
  if(count>0&&!command.replace){controlResult={id:command.id,state:'done',skipped:'cart',count};log('Giỏ đã có sản phẩm; bỏ qua bước thêm bộ.');report('hoat_dong','Chrome · Giỏ đã có sẵn sản phẩm, bỏ qua thêm bộ','');return;}
  let replaced=false;
  if(count!==0&&command.replace){replaced=await clearCart(c,valid);valid();}
  const index=Math.floor(Number(command.bundleIndex)||0),title=String(command.bundle||'').trim();
  if(index<1&&!title)throw Error('Lịch chưa chọn bộ sản phẩm số mấy');
  const open=(c.bundleOpen&&safeOne(c.bundleOpen))||byText(/^(\+\s*)?(Thêm sản phẩm|Thêm|Add products?)$/i).find(b=>!addDrawer()||!addDrawer().contains(b));
  if(!open)throw Error('Chưa thấy nút "Thêm sản phẩm" trên bảng LIVE');
  open.click();
  const d=await waitFor(addDrawer,6000,valid);if(!d)throw Error('Bấm Thêm sản phẩm nhưng chưa mở bảng "Thêm sản phẩm mới"');
  const tab=byText(/^Bộ sản phẩm TRỰC TIẾP$|^LIVE product sets?$/i,d)[0]||(c.bundleTab&&safeOne(c.bundleTab));
  if(!tab)throw Error('Chưa thấy mục "Bộ sản phẩm TRỰC TIẾP"');
  tab.click();await delay(700);valid();
  let target=null,remaining=index;
  for(let page=0;page<20&&!target;page++){
   const rows=await waitFor(()=>{const r=bundleRows(d);return r.length?r:null;},6000,valid);
   if(!rows)throw Error('Chưa đọc được danh sách bộ sản phẩm');
   if(index>=1){if(remaining<=rows.length){target=rows[remaining-1];break;}remaining-=rows.length;}
   else{target=rows.find(r=>NBL.norm(rowTitle(r))===NBL.norm(title))||null;if(target)break;}
   const next=nextPage(d);if(!next)break;next.click();await delay(900);valid();
  }
  if(!target)throw Error(index>=1?'Không có bộ sản phẩm số '+index+' (danh sách ít bộ hơn)':'Không tìm thấy bộ: '+title);
  const name=rowTitle(target)||('bộ số '+index);
  target.click();
  const chosen=await waitFor(()=>textOf(d).match(/(\d+)\s*\/\s*(\d+)\s*sản phẩm sẽ được thêm|(\d+)\s*\/\s*(\d+)\s*products? will be added/i),4000,valid);
  if(!chosen)throw Error('Chọn '+name+' nhưng chưa thấy dòng "x/y sản phẩm sẽ được thêm"');
  const confirm=byText(/^Thêm sản phẩm$|^Add products?$/i,d).filter(b=>!b.disabled&&b.getAttribute('aria-disabled')!=='true'&&!/disabled/i.test(String(b.className)));
  if(confirm.length!==1)throw Error('Nút "Thêm sản phẩm" chưa sẵn sàng');
  confirm[0].click();
  const outcome=await waitFor(()=>{const t=textOf(d);const ok=t.match(/(?:Đã thêm|Added)\s*(\d+)\s*\/\s*(\d+)/i);if(ok&&Number(ok[1])>0)return {ok};if(/Không thể thêm sản phẩm nào|Could not add any products/i.test(t))return {fail:true};return null;},Math.max(5000,command.deadline*1000-Date.now()-3000),valid);
  if(!outcome)throw Error('Chưa thấy "Đã thêm x/y" sau khi chờ; kiểm tra giỏ trên Chrome, không tự bấm lại');
  if(outcome.fail){const left=cartCount(c);if(!(command.replace&&!replaced&&left>0))throw Error('TikTok báo không thêm được sản phẩm nào của '+name+' (nick có thể đang bị hạn chế)');log('Bộ '+name+' đã nằm sẵn trong giỏ; giữ nguyên.');}
  const icon=closeIconIn(d);if(icon)sendTarget(icon).click();else pressEscape();
  await waitFor(()=>!addDrawer(),4000,()=>{});
  controlResult={id:command.id,state:'done',bundle:name,index,added:outcome.ok[1],total:outcome.ok[2]};
  log('Đã thêm bộ sản phẩm ('+outcome.ok[1]+'/'+outcome.ok[2]+') · '+name);
 }catch(e){if(generation===controlEpoch&&controlResult.id===command.id){controlResult={id:command.id,state:'failed',error:e.message};log('Giỏ hàng: '+e.message);}}
 finally{if(controlOwner===generation){controlBusy=false;controlOwner=0;}}}
$('addBundle').onclick=()=>{if(running||controlBusy){log('Dừng các mục và đợi thao tác trước kết thúc rồi thêm bộ.');return;}const c=read();let account;try{account=one(c.account).textContent.trim();}catch(e){log(e.message);return;}const v=String(c.bundleName||'').trim(),n=/^\d+$/.test(v)?Number(v):0;void prepareBundle({id:'manual-'+Date.now(),expectedAccount:account,bundle:n?'':v,bundleIndex:n,preLive:true,deadline:Date.now()/1000+150});};
async function finishLive(command){const c=read();if(command.expectedAccount&&one(c.account).textContent.trim()!==command.expectedAccount)throw Error('Nick khác; không đóng cửa sổ tổng kết');
 // 4.1: the summary can appear seconds after Studio ends; it only has an X icon.
 const end=Date.now()+60000;while(Date.now()<end){if(summaryDialog()){await closeSummary();return;}await delay(1000);}}
const handled=new Set();
// 4.0 watchdog: if the app stops talking to this tab (app closed or crashed), stop
// pinning/replying after 30 s instead of waiting forever with modules switched on.
let lastTickAt=0,lastSentConfig='',lastSentConfigAt=0,runningSince=0,lastConnectionId='',connectionNeedsConfig=true;
setInterval(()=>{if(!running){runningSince=0;return;}if(!runningSince)runningSince=Date.now();if(Date.now()-Math.max(lastTickAt,runningSince)>30000)stop('Mất kết nối app quá 30 giây; đã dừng các mục để an toàn. Mở NBL LIVE rồi bật lại.');},5000);
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
 if(message.type==='version'){respond({protocol:402});return;}
 if(message.type==='disconnect'){connectionNeedsConfig=true;cancelControl();if(message.terminal){stop(message.reason||'Đã ngắt ghép đôi');}else{connectionLost=true;if(tickBusy&&activeModule)manager.stop(activeModule,'Mất kết nối khi thao tác; kiểm tra kết quả rồi bật lại mục này.');for(const s of sleepers)s.resolve();sleepers=[];$('state').textContent='Tạm chờ kết nối app';log(message.reason||'Mất kết nối app; chờ nối lại đúng nick/phiên.');}respond({ok:true});return;}
 if(message.type!=='tick')return;
 const now=Date.now(),connectionChanged=Boolean(lastConnectionId&&message.connectionId&&lastConnectionId!==message.connectionId);
 const staleConnection=Boolean(lastTickAt&&now-lastTickAt>30000);
 if(staleConnection||connectionChanged||message.closing){stop(message.closing?'App đang đóng; đã dừng các mục.':'Đã đổi kết nối hoặc mất kết nối quá 30 giây; bật lại các mục khi sẵn sàng.');}
 if(message.connectionId!==lastConnectionId){connectionNeedsConfig=true;lastConnectionId=message.connectionId||'';}
 lastTickAt=now;
 let currentAccount='';try{currentAccount=one(read().account).textContent.trim();}catch(e){}
 if(currentAccount&&boundAccount&&currentAccount!==boundAccount){void switchAccount(currentAccount);respond({account:currentAccount,accountVerified:Boolean(currentAccount),modules:manager.status(),acks:(message.commands||[]).map(c=>({id:c.id,error:'Đang đổi nội dung theo nick; thử lại sau.'})),config:{},control:controlResult});return;}
 if(switchBusy){respond({account:currentAccount||'Đang đọc trang',accountVerified:Boolean(currentAccount),modules:manager.status(),acks:[],config:{},control:controlResult});return;}
 if(currentAccount)boundAccount=currentAccount;
 if(connectionLost){connectionLost=false;for(const key of NBLModules.keys){const state=manager.items[key];state.pending=[];if(state.nextPinAt)state.nextPinAt=Math.max(state.nextPinAt,Date.now());}log('Đã nối lại; kiểm tra nick/phiên trước khi tiếp tục.');}
 if(message.configAck&&message.configAck!==lastAppAck){lastAppAck=message.configAck;log('App đã lưu cấu hình nick.');}
 try{closeNotices();}catch(e){log(e.message);}
 try{autoCloseSummary();}catch(e){}
 pulse();
 const acks=[];
 for(const c of message.commands||[]){if(handled.has(c.id))continue;handled.add(c.id);if(handled.size>500)handled.delete(handled.values().next().value);if(c.deadline*1000<Date.now()){acks.push({id:c.id,error:'Bỏ lệnh quá hạn'});continue;}let error='';if(c.action==='stop'){if(c.module==='all')cancelControl();manager.stop(c.module);if(c.module==='reply'||c.module==='all'){suggestions=[];renderSuggestions();}renderModules();}else if(c.action==='finish_live'){try{void finishLive(c).catch(e=>log(e.message));}catch(e){error=e.message;}}else if(c.action==='cart_check'){let n=-1;try{n=cartCount(read());}catch(e){}controlResult={id:c.id,state:'done',count:n};
}else if(c.action==='prepare_bundle'){if(controlBusy||running){error='Dừng tương tác và đợi thao tác chuẩn bị trước';controlResult={id:c.id,state:'failed',error,busy:'1'};}else void prepareBundle(c);}else if(c.action==='start'){if(message.closing){acks.push({id:c.id,error:'App đang đóng'});continue;}if(c.expectedAccount){const previousConfig=cfg;try{cfg=read();if(identity()!==c.expectedAccount)throw Error('Tài khoản khác với phiên đã gắn trong app.');}catch(e){error=e.message;}finally{cfg=previousConfig;}}if(!error){if(c.module==='reply'){suggestions=[];renderSuggestions();}error=startModule(c.module,c.config);}}acks.push({id:c.id,error});}
 let account='Chưa chọn tài khoản';try{const previousConfig=cfg;cfg=read();try{account=identity();}finally{cfg=previousConfig;}}catch(e){}
 // Return immediately; potentially slow confirmations don't block the connection heartbeat.
 void saveConfig().catch(()=>{});const current=read(),serialized=JSON.stringify(current);let config;if(connectionNeedsConfig||!message.configAck||serialized!==lastSentConfig||Date.now()-lastSentConfigAt>60000){config=current;connectionNeedsConfig=false;lastSentConfig=serialized;lastSentConfigAt=Date.now();}
 respond({account,accountVerified:Boolean(account&&account!=='Chưa chọn tài khoản'),modules:manager.status(),acks,...(config?{config}:{}),control:controlResult,reports:takeReports()});void tick();return false;
});
document.addEventListener('keydown',e=>{if(e.altKey&&e.shiftKey&&e.code==='KeyX'){stop('Dừng khẩn cấp bằng Alt+Shift+X');}});
document.addEventListener('visibilitychange',()=>{if(!running)return;$('state').textContent=document.hidden?'Chạy nền qua app':'Đang chạy';log(document.hidden?'Chuyển tab: giữ lịch; bỏ các mốc quá hạn, không chạy bù':'Tab hiện lại: tiếp tục kiểm tra tài khoản/phiên');});

function renderSuggestions(){const area=$('suggestions');area.replaceChildren();for(const item of suggestions){const box=document.createElement('div'),label=document.createElement('p'),input=document.createElement('input'),button=document.createElement('button');label.textContent=item.user+': '+item.question;input.value=item.reply;button.textContent='Gửi câu này';button.onclick=()=>{if(!manager.items.reply.running){log('Bật Trả lời trước khi gửi câu đã duyệt');return;}if(Date.now()-item.created>120000){log('Gợi ý đã quá 2 phút, bỏ qua');suggestions=suggestions.filter(x=>x!==item);renderSuggestions();return;}const text=input.value.trim();if(!text||[...text].length>100){log('Câu trả lời phải từ 1 đến 100 ký tự');return;}if(manager.items.reply.pending.length>=20){log('Hàng đợi đầy');return;}manager.items.reply.pending.push({text,expires:Date.now()+60000});suggestions=suggestions.filter(x=>x!==item);renderSuggestions();};box.append(label,input,button);area.append(box);}}
function addSuggestion(r,reply){suggestions.push({user:r.user,question:r.text,reply,created:Date.now()});suggestions=suggestions.filter(x=>Date.now()-x.created<120000).slice(-5);renderSuggestions();}
$('export').onclick=()=>{try{const c=read();const data=Object.fromEntries(fields.map(k=>[k,c[k]]));const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify({version:3,config:data},null,2)],{type:'application/json'}));a.href=url;a.download='NBL_cau_hinh.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){log(e.message);}};
$('import').onclick=()=>{if(running){log('Dừng tool trước khi nhập cấu hình');return;}$('importFile').click();};
$('importFile').onchange=async()=>{const file=$('importFile').files[0];if(!file)return;const previous=Object.fromEntries(fields.map(k=>[k,$(k).value]));try{if(file.size>1000000)throw Error('Tệp quá lớn');const data=JSON.parse(await file.text());if(!data.config||typeof data.config!=='object')throw Error('Tệp cấu hình không hợp lệ');for(const k of fields)if(data.config[k]!=null)$(k).value=String(data.config[k]);read();refreshFields();log('Đã nhập; kiểm tra kết nối trang rồi lưu.');}catch(e){for(const k of fields)$(k).value=previous[k];log('Nhập lỗi: '+e.message);}$('importFile').value='';};
const panel=ui.querySelector('section'),handle=ui.querySelector('h3');let drag=null;
function place(x,y){panel.style.right='auto';panel.style.left=Math.max(0,Math.min(x,innerWidth-panel.offsetWidth))+'px';panel.style.top=Math.max(0,Math.min(y,innerHeight-50))+'px';panel.style.maxHeight=Math.max(100,innerHeight-parseFloat(panel.style.top)-12)+'px';}
handle.onpointerdown=e=>{if(e.target.closest('button'))return;const r=panel.getBoundingClientRect();drag={x:e.clientX-r.left,y:e.clientY-r.top};handle.setPointerCapture(e.pointerId);e.preventDefault();};
handle.onpointermove=e=>{if(drag)place(e.clientX-drag.x,e.clientY-drag.y);};
handle.onpointerup=()=>{if(!drag)return;drag=null;chrome.storage.local.set({nblPanel:{x:parseFloat(panel.style.left),y:parseFloat(panel.style.top)}});};handle.onpointercancel=()=>{drag=null;};
$('resetPosition').onclick=()=>{place(innerWidth-panel.offsetWidth-12,Math.max(0,innerHeight-panel.offsetHeight-12));chrome.storage.local.set({nblPanel:{x:parseFloat(panel.style.left),y:parseFloat(panel.style.top)}});};
window.addEventListener('resize',()=>{const r=panel.getBoundingClientRect();place(r.left,r.top);});
let pendingShared=null;
chrome.storage.onChanged?.addListener((changes,area)=>{if(area!=='local'||!changes.nblSharedSetup?.newValue)return;pendingShared=changes.nblSharedSetup.newValue;if(running||controlBusy){log('Cách chọn nút chung đã đổi; dừng các mục rồi bấm Dùng cách chọn nút đã lưu.');return;}for(const id of sharedFields)if(pendingShared[id]!=null)$(id).value=pendingShared[id];pendingShared=null;refreshFields();lastSaved='';});
const position=await chrome.storage.local.get('nblPanel');if(position.nblPanel)place(position.nblPanel.x,position.nblPanel.y);

renderModules();
const saved=await chrome.storage.local.get(['nblConfig','nblAccounts','nblSharedSetup']);let restored=saved.nblConfig;
if(restored?.account){try{const account=one(restored.account).textContent.trim();const perAccount=await chrome.storage.local.get('nblAccount:'+account);restored=perAccount['nblAccount:'+account]||saved.nblAccounts?.[account]||{...restored,owner:account,rules:'',pins:'',bundleName:''};}catch(e){}}
if(restored)for(const id of fields)if(restored[id]!=null)$(id).value=String(restored[id]);
if(restored&&!restored.productMode&&restored.pins){$('pins').value=restored.pins.split(/\n/).map(line=>line.replace(/^\s*\d+:\d+:\d+\s*\|\s*/,'' )).join('\n');$('productMode').value='name';}
if(saved.nblSharedSetup)for(const id of sharedFields)if(saved.nblSharedSetup[id]!=null)$(id).value=saved.nblSharedSetup[id];try{boundAccount=one(read().account).textContent.trim();}catch(e){}refreshFields();
})();
