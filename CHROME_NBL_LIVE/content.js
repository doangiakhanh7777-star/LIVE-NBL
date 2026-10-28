(async()=>{
'use strict';
if(document.getElementById('nbl-live-extension'))return;
// 4.2.1: opened by NBL with #nbl=<code> → pair this tab by itself, then hide the code.
{const m=/[#&]nbl=([a-f0-9]{32})/.exec(location.hash);if(m){try{chrome.runtime.sendMessage({type:'pair_self',token:m[1]});}catch(e){}history.replaceState(null,'',location.pathname+location.search);}}
const host=document.createElement('div');host.id='nbl-live-extension';host.style.display='none';document.documentElement.append(host);   // 4.3.0: cầu nối — không hiện gì trên trang, mọi thiết lập nằm trong app NBL
const ui=host.attachShadow({mode:'open'});
ui.innerHTML=`<style>:host{all:initial}section{position:fixed;right:12px;bottom:12px;width:min(390px,calc(100vw - 40px));max-height:84vh;overflow:auto;z-index:2147483647;background:#fff;color:#3b2414;padding:16px;border:2px solid #f97316;border-radius:20px;font:14px Arial;box-shadow:0 7px 28px #c2410c30}h3{margin:0 0 12px;cursor:move;touch-action:none;position:sticky;top:0;background:#fff;z-index:2;color:#ea580c}label{display:block;margin-top:11px;font-weight:600}input,textarea,select{box-sizing:border-box;width:100%;padding:9px;margin-top:5px;background:#fffaf4;color:#3b2414;border:1px solid #fdba74;border-radius:10px;font:14px Arial}textarea{height:76px}button{background:#fff1e3;color:#9a3412;border:1px solid #fdba74;border-radius:11px;padding:9px;margin:5px 4px 5px 0;cursor:pointer;font:13px Arial}button:hover{background:#fed7aa}pre{white-space:pre-wrap;font:12px Arial;max-height:160px;overflow:auto}.red{background:#fff0ed;color:#ae3723;border-color:#ffc0ad}.bar{background:#ff993f;color:#382100;border-color:#f28629}.step{display:flex;align-items:center;gap:6px;margin-top:5px}.step output{min-width:84px;text-align:center;background:#fff1e3;padding:8px;border-radius:10px}.step button{margin:0}.hint{font-size:12px;line-height:1.45;color:#526e80}.selectors{display:none}details{margin:14px 0;padding:10px;background:#fff7ed;border-radius:12px}summary{cursor:pointer;font-weight:600}.picked{font-size:12px;font-weight:400;color:#267440}</style>
<section><h3>NBL LIVE • 4.3.0 <button id="fold">Thu gọn</button></h3><div id="body">
<p class="hint">Giỏ hàng và trả lời bình luận trên Chrome. Tin nhắn định kỳ và Chào khách cài trong app NBL LIVE.</p>
<label>Tên chủ phòng trong bình luận<input id="owner" placeholder="Khánh Car Auto"></label>
<label>Câu trả lời tự động<textarea id="rules" placeholder="bơm lốp;bom lop | Anh xem sản phẩm bơm lốp trong giỏ nhé."></textarea></label><p id="rulesHint" class="hint">Chưa có quy tắc. Chữ mẫu mờ không phải nội dung đã nhập.</p><p class="hint">Mỗi dòng: từ khóa | câu trả lời. Nhiều từ khóa cùng câu: ngăn bằng dấu ;</p>
<div id="insertBox" class="hint" style="background:#fff1e3;border:1px solid #fdba74;border-radius:10px;padding:8px;margin-top:10px"><b>Ghim chèn theo kịch bản clip</b>: soạn trong app NBL LIVE (mục Kịch bản ghim giỏ hàng). Khi LIVE phát clip có kịch bản, món chèn được ghim đúng giây đã cắm cờ, xong thì ghim xáo trộn chạy tiếp. <span id="insertState">Chưa có kịch bản từ app.</span></div>
<label>Chọn sản phẩm ghim bằng<select id="productMode"><option value="number">Số thứ tự trong giỏ</option><option value="name">Tên sản phẩm</option></select></label>
<button id="readProducts">Chọn sản phẩm từ giỏ hiện tại</button><p class="hint">Nếu số trên trang không đọc được, app đánh số NBL và nhớ đúng món đã tích. Không cần chọn chữ Đã ghim khi nút Ghim/Bỏ ghim đã đọc được.</p><div id="productChoices"></div><input id="productBindings" type="hidden"><div id="cycleBox"><label>Sản phẩm muốn ghim<textarea id="pins" placeholder="1&#10;3&#10;5"></textarea></label><p class="hint">Mỗi dòng một SỐ THỨ TỰ, hoặc 3–4 chữ đầu tên sản phẩm (NBL gõ vào ô tìm kiếm của trang). Tự xáo trộn mỗi vòng; món không có trong giỏ được bỏ qua.</p><button id="testPins">🔍 Tìm thử các món</button><button id="checkColumn">Kiểm tra cột số</button><p id="findResult" class="hint"></p>
<label>Giữ sản phẩm đang ghim</label><div data-time="pinMin" data-zero="1" data-default="30" data-min="0" data-label="Ít nhất"></div><div data-time="pinMax" data-zero="1" data-default="40" data-min="0" data-label="Nhiều nhất"></div>
<label>Nghỉ sau khi tháo ghim</label><div data-time="gapMin" data-zero="1" data-default="30" data-min="0" data-label="Ít nhất"></div><div data-time="gapMax" data-zero="1" data-default="40" data-min="0" data-label="Nhiều nhất"></div><p class="hint">Ghim → giữ → tháo ghim → nghỉ không ghim món nào → ghim món tiếp theo. Để cả 4 ô bằng 0 (hoặc không chọn món nào) = TẮT ghim xáo trộn.</p></div>
<label>Trả lời bình luận<select id="replyMode"><option value="auto">Tự gửi theo từ khóa</option><option value="suggest">Hiện gợi ý để tôi duyệt</option></select></label><label>Nghỉ trước khi trả lời lại cùng khách</label><div data-time="cooldown" data-default="60" data-min="15" data-label="Khoảng nghỉ"></div><div id="suggestions"></div>
<details><summary>Chọn các nút trên trang — làm một lần</summary><p class="hint">Bấm Chọn rồi bấm đúng vị trí trên trang. Nhấn Esc để hủy. Các vị trí đã chọn được dùng chung giữa các nick; nội dung lưu riêng từng nick.</p><div id="pickFields"></div><button id="shareSetup">Lưu cách chọn nút để dùng chung</button><button id="useShared">Dùng cách chọn nút đã lưu</button>
<details><summary>Cài đặt nâng cao</summary><div id="advancedFields"></div></details></details>
<label>Bộ sản phẩm (số thứ tự từ trên xuống, hoặc tên bộ)<input id="bundleName" placeholder="1"></label><button id="addBundle">Thêm bộ vào phiên LIVE</button><p class="hint">Lịch LIVE trong app tự thêm bộ đã chọn trước giờ phát. Nút này để thêm tay. Giỏ đã có sản phẩm thì không thêm nữa; món hết hàng được bỏ qua.</p>
<button id="save">Lưu ngay</button><button id="check">Kiểm tra kết nối trang</button><button id="start" class="bar">Bật các mục</button><button id="stop" class="red">Dừng các mục</button><div id="modules"></div>
<details><summary>Sao lưu và vị trí bảng</summary><button id="export">Xuất bản sao cài đặt</button><button id="import">Nhập bản sao cài đặt</button><input id="importFile" type="file" accept=".json" hidden><button id="resetPosition">Đưa bảng về góc dưới bên phải</button></details><p id="state">Đã dừng</p><pre id="log"></pre></div></section>`;
const $=id=>ui.getElementById(id);
const setupLabels={account:'Tên tài khoản',live:'Đồng hồ LIVE',input:'Ô nhập tin nhắn',send:'Nút gửi tin nhắn',rows:'Một dòng bình luận gồm tên và câu hỏi',user:'Tên khách trong dòng bình luận',text:'Câu hỏi trong dòng bình luận',products:'Một ô sản phẩm trong giỏ',productTitle:'Tên sản phẩm trong ô',numberCell:'Một ô số thứ tự (cột số bên trái mỗi món)',productNumber:'Số thứ tự trong ô sản phẩm — không bắt buộc',pinned:'Trạng thái ghim — không bắt buộc',unpinButton:'Nút Bỏ ghim trong ô sản phẩm — nếu có',bundleOpen:'Nút Thêm sản phẩm',bundleTab:'Mục Bộ sản phẩm TRỰC TIẾP — nếu có',bundleConfirm:'Nút xác nhận Thêm sản phẩm',bundleReady:'Danh sách sản phẩm trong phiên LIVE'};
const sharedFields=Object.keys(setupLabels),relativeParents={user:'rows',text:'rows',productTitle:'products',productNumber:'products',pinned:'products',unpinButton:'products'};
for(const [id,label] of Object.entries(setupLabels)){const row=document.createElement('div'),button=document.createElement('button'),status=document.createElement('span'),input=document.createElement('input'),advanced=document.createElement('label');button.textContent='Chọn '+label;button.dataset[relativeParents[id]?'relative':'pick']=id;if(relativeParents[id])button.dataset.parent=relativeParents[id];status.id=id+'Picked';status.className='picked';status.textContent='Chưa chọn';row.append(button,status);$('pickFields').append(row);input.id=id;advanced.textContent=label+' — mã vị trí';advanced.append(input);$('advancedFields').append(advanced);}
for(const box of ui.querySelectorAll('[data-time]')){const id=box.dataset.time,input=document.createElement('input'),label=document.createElement('span'),out=document.createElement('output');input.id=id;input.type='hidden';input.value=box.dataset.default;label.textContent=box.dataset.label;out.id=id+'Display';box.className='step';box.append(label);for(const amount of [-10,-1,1,10]){const button=document.createElement('button');button.textContent=(amount>0?'+':'')+amount;button.onclick=()=>{input.value=String(Math.max(Number(box.dataset.min),Math.min(86400,Number(input.value)+amount)));input.dispatchEvent(new Event('change'));};box.append(button);if(amount===-1)box.append(out);}box.append(input);}
const fields=['owner','rules','pins','productMode','replyMode','cooldown','pinMin','pinMax','gapMin','gapMax','bundleName','productBindings',...sharedFields];
const pickErrors=new Map();
function relativeMatches(spec,base){if(spec===':scope'&&base instanceof Element)return [base];return [...base.querySelectorAll(spec)];}
function buttonName(button){return [button.getAttribute('aria-label'),button.getAttribute('title'),button.textContent].filter(Boolean).map(x=>x.trim().replace(/^[^\p{L}\p{N}]+/u,'').replace(/\s+/g,' '));}
function actionButtons(card,kind){const re=kind==='unpin'?/^(Bỏ ghim|Tháo ghim|Unpin)( sản phẩm)?$/i:/^(Ghim|Pin)( sản phẩm)?$/i;return [...card.querySelectorAll('button,[role=button]')].filter(visible).filter(b=>buttonName(b).some(x=>re.test(x)));}
function readNumber(el){const box=el&&el.matches&&el.matches('input')?el:el&&el.querySelector?el.querySelector('input'):null;const values=[box&&box.value,box&&box.getAttribute('value'),el.textContent,el.getAttribute('aria-label'),el.getAttribute('data-number'),el.getAttribute('data-index')];for(const value of values){const t=String(value||'').trim();if(/^#?\s*[1-9]\d{0,4}[.)]?$/.test(t))return Number(t.replace(/[^\d]/g,''));}return null;}
function inspectField(id,spec){
 if(!spec)return {ok:false,text:id==='pinned'||id==='unpinButton'?'Tự nhận Ghim/Bỏ ghim':'Chưa chọn'};
 try{
  const parent=relativeParents[id];const roots=parent?[...document.querySelectorAll($(parent).value)].filter(visible):[document];
  const matches=roots.flatMap(root=>relativeMatches(spec,root).filter(visible));
  if(!matches.length)return {ok:false,text:'Đã lưu · chưa thấy trên trang này'};
  if(!parent&&!['rows','products','bundleCards'].includes(id)&&matches.length!==1)return {ok:false,text:'Chọn lại · tìm thấy '+matches.length+' chỗ'};
  if(parent&&roots.some(root=>relativeMatches(spec,root).filter(visible).length>1))return {ok:false,text:'Chọn lại · một khung khớp nhiều chỗ'};
  if(id==='numberCell'){const rows=numberRows();return rows.length?{ok:true,text:'Đọc được '+rows.length+' ô số: '+rows.slice(0,6).map(r=>r.number).join(', ')+' · nút Ghim: '+rows.filter(r=>r.pin||r.unpin).length+'/'+rows.length}:{ok:false,text:'Chưa đọc được ô số nào; bấm đúng vào ô số 1, 2, 3… bên trái một món'};}
  if(id==='productNumber'){
   // 4.1.11: lenient — a card without a readable number is counted by its place.
   const numbers=matches.map(readNumber).filter(x=>x!==null);if(!numbers.length)return {ok:false,text:'Không đọc được số · NBL sẽ đếm thứ tự từ trên xuống (không bắt buộc)'};if(new Set(numbers).size!==numbers.length)return {ok:false,text:'Có số trùng nhau · chọn lại đúng ô số'};
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
if(key==='pin'){c.pinJobs=String(c.pins||'').trim()?NBLPins.parseProducts(c.pins,c.productMode):[];const times=['pinMin','pinMax','gapMin','gapMax'];for(const id of times)c[id]=Number(c[id]||0);
 // 4.1.11 (owner): all four times 0, or no product chosen = cycle OFF (inserts from the clip script still run).
 c.cycle=c.pinJobs.length>0&&times.some(id=>c[id]>0);
 if(c.cycle){if(times.some(id=>c[id]<1))throw Error('Ghim xáo trộn: để 0 cả 4 ô để tắt, hoặc điền đủ 4 ô (ít nhất 1 giây)');for(const pair of [['pinMin','pinMax'],['gapMin','gapMax']])NBLPins.validateRange(c[pair[0]],c[pair[1]]);}}
if(key==='reply'){c.replyRules=NBL.parse(c.rules,'rule');if(!c.replyRules.length&&c.replyMode!=='suggest'&&c.replyMode!=='ai')throw Error('Chưa có câu trả lời theo từ khóa · nhập nội dung thật vào ô, chữ mẫu mờ chưa được tính');c.cooldown=Number(c.cooldown);if(!Number.isFinite(c.cooldown)||c.cooldown<15)throw Error('Nghỉ trả lời tối thiểu 15 giây');if(c.replyRules.some(x=>[...x.text].length>100))throw Error('Mỗi câu trả lời tối đa 100 ký tự');}return c;}
function startModule(key,override){void saveConfig().catch(e=>log('Chưa lưu: '+e.message));if(tickBusy)return 'Đang xác nhận thao tác trước; thử lại sau vài giây.';try{if(key==='reply'){suggestions=[];renderSuggestions();}if(override)for(const id of fields)if(override[id]!=null)$(id).value=String(override[id]);const state=manager.start(key,()=>{const c=prepare(key);cfg=c;identity();liveTime();if(key==='pin'){const rows=numberRows();if(!rows.length)log('Chưa thấy ô số thứ tự nào trong giỏ; NBL sẽ tìm lại khi ghim.');if(!c.cycle)log('Ghim xáo trộn đang TẮT (để 0); chỉ chạy ghim chèn theo kịch bản clip.');}else{one(c.input);one(c.send);chat();if(!c.rows||!c.user||!c.text)throw Error('Chọn tên khách và câu hỏi trong dòng bình luận trước');}return c;});cfg=state.config;state.snapshot=identity();state.timerLast=liveTime();state.pinCycle=new NBLPins.Cycle(state.config.pinJobs||[]);state.nextPinAt=Date.now();state.detail=key==='pin'?'Đang kiểm tra món đã chọn':'Đang chờ bình luận mới';state.seen=new Set(key==='pin'?[]:chat().map(keyOf));connectionLost=false;renderModules();log('Bật '+key);return '';}catch(e){manager.stop(key,e.message);renderModules();log(key+': '+e.message);return e.message;}}
// 4.3.0 (owner, 28/10/2026): the extension finds everything itself (measured on the
// LIVE dashboard 28/10/2026); a picked position from an older version is still used.
function autoAccount(){const W=innerWidth;const handle=t=>/^[A-Za-z0-9._]{2,40}$/.test(t)&&!/^(VN|EN|LIVE|Flash|Sale)$/i.test(t);
 const leaves=[...document.querySelectorAll('span,div')].filter(e=>!host.contains(e)&&e.children.length===0&&visible(e)&&handle((e.textContent||'').trim()));
 const inHeader=e=>{for(let p=e.parentElement,i=0;p&&i<8;p=p.parentElement,i++){const c=String(p.className||'');if(/\bfixed\b/.test(c)&&/\bh-60\b|\bz-1\d\d\b/.test(c))return true;}return false;};
 const byHeader=leaves.filter(inHeader);if(byHeader.length)return byHeader[byHeader.length-1];
 const byPlace=leaves.filter(e=>{const r=e.getBoundingClientRect();return r.top<60&&r.left>W*0.55;});
 if(!byPlace.length)throw Error('Chưa đọc được tên tài khoản TikTok Shop (chưa đăng nhập?)');return byPlace.sort((a,b)=>b.getBoundingClientRect().left-a.getBoundingClientRect().left)[0];}
function autoLiveEl(){const c=[...document.querySelectorAll('span,div')].filter(e=>!host.contains(e)&&e.children.length===0&&visible(e)&&/^\d{2,}:\d{2}:\d{2}$/.test((e.textContent||'').trim()));if(c.length)return c[0];throw Error('Không đọc được đồng hồ LIVE trên trang');}
const NUM_CELL='input[data-tid="m4b_input_number"]';
function autoCards(){const out=[];for(const input of document.querySelectorAll(NUM_CELL)){if(!visible(input)||host.contains(input))continue;let el=input.parentElement,card=null;for(let i=0;el&&i<12;i++,el=el.parentElement){const inputs=el.querySelectorAll(NUM_CELL).length;if(inputs>1)break;if([...el.querySelectorAll('button,[role=button]')].some(b=>visible(b)&&buttonName(b).some(x=>/^(Ghim|Bỏ ghim|Pin|Unpin)( sản phẩm)?$/i.test(x)))){card=el;break;}}if(card&&!out.includes(card))out.push(card);}return out;}
function autoTitle(card){const pick=[...card.querySelectorAll('[class*="text-body-m-regular"] span,[class*="text-body-m-regular"]')].filter(visible).map(e=>(e.textContent||'').trim()).filter(t=>t&&!/^Ghim$|^Bỏ ghim$|₫/.test(t));if(pick.length)return pick[0];const leaves=[...card.querySelectorAll('span,div')].filter(e=>e.children.length===0&&visible(e)).map(e=>(e.textContent||'').trim()).filter(t=>t.length>8&&!/₫|Lượt nhấp|Còn:|Ghim/.test(t));return leaves.sort((a,b)=>b.length-a.length)[0]||'';}
function titleOf(card){if(cfg.productTitle){const t=relativeMatches(cfg.productTitle,card).filter(visible);if(t.length===1)return t[0].textContent.trim();}return autoTitle(card);}
function identity(){return (cfg.account?one(cfg.account):autoAccount()).textContent.trim();}
function liveTime(){const s=(cfg.live?one(cfg.live):autoLiveEl()).textContent.match(/\b\d{2,}:\d{2}:\d{2}\b/);if(!s)throw Error('Không đọc được đồng hồ LIVE');return NBL.seconds(s[0]);}
const rowKeys=new WeakMap();let nextRowKey=0;
// 4.0: a row without its own name/question (system line, gift, pinned notice) is skipped
// instead of stopping the whole reply module; only a fully unreadable chat is an error.
function chat(){if(!cfg.rows)return [];const rows=[...document.querySelectorAll(cfg.rows)].filter(visible);let bad=0;const out=[];for(const row of rows){let result;try{result={user:one(cfg.user,row).textContent.trim(),text:one(cfg.text,row).textContent.trim()};}catch(e){bad++;continue;}if(!result.user||!result.text){bad++;continue;}if(!rowKeys.has(row))rowKeys.set(row,++nextRowKey);Object.defineProperty(result,'key',{value:rowKeys.get(row)+'\u0000'+result.user+'\u0000'+result.text});out.push(result);}if(rows.length>=3&&!out.length)throw Error('Không đọc được tên/câu hỏi ở dòng bình luận nào; chọn lại vị trí trong dòng bình luận.');return out;}
function keyOf(r){return r.key||r.user+'\u0000'+r.text;}
function assertContext(){closeNotices();const warning=stillBlocked();if(warning)throw Error('Trang yêu cầu chú ý (captcha / xác minh / LIVE đã kết thúc); dừng mục và kiểm tra.');if(location.pathname!='/streamer/live/product/dashboard')throw Error('Đã rời bảng LIVE');if(identity()!==snapshot)throw Error('Tài khoản đã đổi');const t=liveTime();if(t<timerLast)throw Error('Đồng hồ LIVE quay lại: có thể đã đổi phiên');timerLast=t;}
function productCards(){return cfg.products?[...document.querySelectorAll(cfg.products)].filter(visible):autoCards();}
function bindings(){try{const data=JSON.parse(cfg.productBindings||'[]');return Array.isArray(data)?data.filter(x=>Number.isSafeInteger(x.number)&&x.number>0&&typeof x.key==='string'&&typeof x.title==='string'):[];}catch(e){throw Error('Danh sách món đã chọn bị lỗi; bấm Chọn sản phẩm từ giỏ hiện tại rồi tích lại.');}}
function cardKey(card){const title=titleOf(card);if(!title)throw Error('Tên sản phẩm đang rỗng; chọn lại Tên sản phẩm trong ô.');const id=card.getAttribute('data-product-id')||card.getAttribute('data-id');return id?'id:'+id:'title:'+NBL.norm(title);}
function pin(product){
 const cards=productCards();
 if(product.mode==='number'){
  // 4.1: numbers are the cart order of THIS LIVE (owner, 19/10/2026): the set is
  // added fresh each LIVE with the main products on top. Saved bindings from an
  // older cart are not used, they would point at products of another set.
  if(cfg.productNumber&&cards.length){const rows=cards.map(card=>{const labels=relativeMatches(cfg.productNumber,card).filter(visible);return {card,number:labels.length===1?readNumber(labels[0]):null};});
   const known=rows.filter(x=>x.number!==null);
   if(known.length&&new Set(known.map(x=>x.number)).size===known.length){const hit=known.find(x=>x.number===product.number);if(hit)return hit.card;if(known.length===rows.length)return null;}}
  return cards[product.number-1]||null;
 }
 const nn=x=>NBL.norm(x).replace(/\s+/g,' '),want=nn(product.text),named=cards.map(card=>({card,title:nn(titleOf(card))}));
 const exact=named.filter(x=>x.title&&x.title===want);if(exact.length)return exact[0].card;
 const matches=named.filter(x=>x.title&&x.title.includes(want));if(matches.length>1)throw Error('Tên khớp nhiều sản phẩm: '+product.text);return matches[0]?.card||null;
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
function productIdentity(card){const title=titleOf(card);return {card,title,key:card.getAttribute('data-product-id')||card.getAttribute('data-id')||NBL.norm(title)};}
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
// 4.1.13 (owner, 26/10/2026 20:26): "lựa chọn số thứ tự là 1 vùng dọc từ trên xuống" — the
// number boxes (1, 2, 3…) form a column on the left of the product list. NBL reads only
// that column, takes the Ghim / Bỏ ghim button on the same row (between this number and
// the next), and scrolls the list until the number shows. Names go through the page's own
// "Tìm ID hoặc tên sản phẩm" box: 3–4 first words are enough; several results → the one
// whose name starts with those words, otherwise the first; the box is cleared after.
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let manualScrollAt=0,findBusy=false;
document.addEventListener('wheel',e=>{if(!e.composedPath().includes(host))manualScrollAt=Date.now();},{capture:true,passive:true});
const nn=x=>NBL.norm(x).replace(/\s+/g,' ');
function searchBox(){return [...document.querySelectorAll('input')].filter(visible).find(i=>!host.contains(i)&&/Tìm ID hoặc tên sản phẩm|Search.*(ID|product)/i.test(i.getAttribute('placeholder')||''))||null;}
function numberSpec(el){const input=el.matches&&el.matches('input')?el:el.querySelector&&el.querySelector('input')||el;const s=selector(input,true);return /^[a-z]+\./.test(s)?s:'input';}
function numberCells(){const search=searchBox();const spec=(cfg&&cfg.numberCell)||($('numberCell')&&$('numberCell').value)||NUM_CELL;let cells=[];try{cells=[...document.querySelectorAll(spec)];}catch(e){cells=[];}if(cells.filter(e=>visible(e)&&readNumber(e)!==null).length<2)cells=[...document.querySelectorAll('input')];
 cells=cells.filter(e=>visible(e)&&!host.contains(e)&&e!==search).map(e=>{const v=readNumber(e);const r=e.getBoundingClientRect();return v===null?null:{el:e,number:v,x:r.left+r.width/2,top:r.top,bottom:r.bottom,right:r.right};}).filter(Boolean);
 if(!cells.length)return [];
 // the column = the x where most number boxes sit (the cart column), ±30 px
 const xs=cells.map(c=>Math.round(c.x/20)),count=new Map();for(const x of xs)count.set(x,(count.get(x)||0)+1);const col=[...count.entries()].sort((a,b)=>b[1]-a[1])[0][0]*20;
 return cells.filter(c=>Math.abs(c.x-col)<=30).sort((a,b)=>a.top-b.top);}
function numberRows(){const cells=numberCells();if(!cells.length)return [];
 const pins=actionButtons(document,'pin').filter(b=>!host.contains(b)),unpins=actionButtons(document,'unpin').filter(b=>!host.contains(b));
 const pitch=cells.length>1?(cells[cells.length-1].top-cells[0].top)/(cells.length-1):200;
 return cells.map((c,k)=>{const end=k+1<cells.length?cells[k+1].top:c.top+Math.max(120,pitch);const inRow=b=>{const r=b.getBoundingClientRect(),y=r.top+r.height/2;return y>=c.top-12&&y<end-2&&r.left>c.right;};
  const pin=pins.filter(inRow),unpin=unpins.filter(inRow);
  let box=c.el;while(box&&box.parentElement&&!(pin.concat(unpin)).every(b=>box.contains(b)))box=box.parentElement;
  const text=(box&&(pin.length||unpin.length)?box.textContent:'').replace(/\s+/g,' ').trim();
  return {number:c.number,cell:c.el,pin:pin[0]||null,unpin:unpin[0]||null,pinned:unpin.length>0,text,top:c.top};});}
function listBox(){const c=numberCells()[0];let el=c&&c.el.parentElement;while(el&&el!==document.body&&el!==document.documentElement){const st=getComputedStyle(el);if(/(auto|scroll)/.test(st.overflowY||'')&&el.scrollHeight>el.clientHeight+20)return el;el=el.parentElement;}return null;}
async function scrollTo(box,top){box.scrollTop=Math.max(0,top);box.dispatchEvent(new Event('scroll',{bubbles:true}));await pause(350);}
async function waitOwner(){const end=Date.now()+15000;while(Date.now()-manualScrollAt<3000&&Date.now()<end)await pause(400);}
async function rowOf(number,{scroll=true}={}){
 let row=numberRows().find(r=>r.number===number);if(row||!scroll)return row||null;
 const box=listBox();if(!box)return null;await waitOwner();
 for(let i=0;i<15;i++){const all=numberRows();if(!all.length)break;row=all.find(r=>r.number===number);if(row)return row;const rows=all.filter(r=>!r.pinned).filter((r,k,a)=>!k||r.number>a[k-1].number);if(!rows.length)break;
  const first=rows[0],last=rows[rows.length-1],pitch=rows.length>1&&last.number!==first.number?Math.max(40,(last.top-first.top)/(last.number-first.number)):Math.max(80,box.clientHeight/4);
  const ref=number<first.number?first:last,before=box.scrollTop;await scrollTo(box,before+(number-ref.number)*pitch);if(Math.abs(box.scrollTop-before)<1)break;}
 row=numberRows().find(r=>r.number===number);if(row)return row;
 await scrollTo(box,0);for(let i=0;i<150;i++){row=numberRows().find(r=>r.number===number);if(row)return row;const before=box.scrollTop;await scrollTo(box,before+box.clientHeight*.8);if(Math.abs(box.scrollTop-before)<1)break;}
 row=numberRows().find(r=>r.number===number);if(!row)await scrollTo(box,0);return row||null;}
async function typeSearch(text){const input=searchBox();if(!input)throw Error('Chưa thấy ô "Tìm ID hoặc tên sản phẩm" trên trang');
 const before=JSON.stringify(numberRows().map(r=>r.number));changeInput(input,text);input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));input.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));
 // TikTok searches on its server: wait until the list changed and then stayed the same
 // for 0.7 s (or nothing changed for 2.5 s), at most 5 s.
 const t0=Date.now();let last=before,changedAt=0;await pause(400);
 while(Date.now()-t0<5000){const now=JSON.stringify(numberRows().map(r=>r.number));if(now!==last){last=now;changedAt=Date.now();}
  if(changedAt&&Date.now()-changedAt>=700)break;if(!changedAt&&Date.now()-t0>=2500)break;await pause(250);}
 return input;}
async function clearSearch(){const input=searchBox();if(!input||!String(input.value||'').trim())return;changeInput(input,'');input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));input.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));await pause(1200);}
function chooseResult(rows,text){const want=nn(text);const hits=rows.filter(r=>nn(r.text).includes(want));if(!hits.length)return {row:null,hits};
 // the name usually comes right after the number; the earliest match = "starts with"
 hits.sort((a,b)=>nn(a.text).replace(/^\d+\s*/,'').indexOf(want)-nn(b.text).replace(/^\d+\s*/,'').indexOf(want)||a.top-b.top);return {row:hits[0],hits};}
async function findByName(text){await waitOwner();await typeSearch(text);let rows=numberRows().filter(r=>r.pin||r.unpin);const {row,hits}=chooseResult(rows,text);
 if(!row&&rows.length)return {row:rows[0],hits:rows,loose:true};return {row,hits};}
function isNumberText(t){return /^\s*#?\d{1,4}\s*$/.test(String(t||''));}
const CONFIRM_MS=15000;
function hhmmss(ms){const d=new Date(ms);return [d.getHours(),d.getMinutes(),d.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':');}
async function toTop(force){const box=listBox();if(box&&box.scrollTop>0&&(force||Date.now()-manualScrollAt>3000))await scrollTo(box,0);}
// 4.1.14 (owner, 26/10/2026 21:04): after "Ghim" TikTok moves the product to the TOP of the
// list ("Đã ghim"); the list was still scrolled down, so NBL saw nothing for 8 s, called it
// a failure and the hold / rest times never applied. Now: click → back to the top → only
// then count up to 15 s; never click Ghim a second time; unconfirmed = still held (a note
// in the log, no error), because the page is usually just slow.
async function clickPin(row){if(row.pinned)return {confirmed:true,after:0};if(!row.pin)throw Error('Số '+row.number+': chưa thấy nút Ghim cùng hàng');const b=sendTarget(row.pin);if(b.disabled||b.getAttribute('aria-disabled')==='true')throw Error('Nút Ghim của số '+row.number+' đang bị khóa');
 b.click();await pause(400);await toTop(true);const start=Date.now();
 while(Date.now()-start<CONFIRM_MS){const r=numberRows().find(x=>x.number===row.number);if(r&&r.pinned)return {confirmed:true,after:(Date.now()-start)/1000};await pause(500);await toTop(false);}
 log('Đã bấm Ghim số '+row.number+'; sau 15 giây trang chưa hiện "Đã ghim" — vẫn tính là đang giữ');return {confirmed:false,after:CONFIRM_MS/1000};}
async function doPin(product){assertContext();const wait0=Date.now()+15000;while(findBusy&&Date.now()<wait0)await pause(300);if(findBusy)throw Error('Đang bận tìm thử món khác');findBusy=true;let searched=false;
 try{const text=product.mode==='name'?product.text:String(product.number);
  if(product.mode!=='name'||isNumberText(text)){await clearSearch();const n=Number(String(text).replace(/\D/g,''));const row=await rowOf(n);if(!row){log('Số '+n+': đã cuộn hết danh sách, không thấy');return null;}
   const r=await clickPin(row);log('Bấm Ghim số '+n+(r.confirmed?' → đã lên khung Đã ghim sau '+Math.round(r.after)+' giây':' → chưa thấy xác nhận'));return {number:n,title:'số '+n,key:'#'+n,confirmed:r.confirmed};}
  searched=true;const {row,hits,loose}=await findByName(text);
  if(!row){log('Tìm "'+text+'": không ra món nào');return null;}
  if(hits.length>1||loose)log('Tìm "'+text+'" ra '+hits.length+' món → ghim số '+row.number+': '+row.text.slice(0,60));
  const title=row.text.replace(/^\d+\s*/,'').slice(0,80);const r=await clickPin(row);log('Bấm Ghim số '+row.number+' ('+title+')'+(r.confirmed?' → đã lên khung Đã ghim':' → chưa thấy xác nhận'));return {number:row.number,title,key:'#'+row.number,confirmed:r.confirmed};}
 finally{if(searched){try{await clearSearch();}catch(e){}}try{await toTop(false);}catch(e){}findBusy=false;}}
function pageUnpin(){const all=actionButtons(document,'unpin').filter(b=>!host.contains(b));return all.length===1?all[0]:null;}
async function doUnpin(item){assertContext();
 await toTop(false);const n=item&&item.number;
 let row=n?numberRows().find(r=>r.number===n&&r.pinned):null;
 if(!row&&n){const found=await rowOf(n);row=found&&found.pinned?found:null;if(found&&!found.pinned){await toTop(false);return;}}   // already taken down
 const b=row&&row.unpin?row.unpin:pageUnpin();
 if(!b){log('Chưa thấy nút Bỏ ghim của '+(item&&item.title||'món đang ghim')+'; bỏ qua lần tháo này');await toTop(false);return;}
 sendTarget(b).click();await pause(400);await toTop(true);const start=Date.now();
 while(Date.now()-start<CONFIRM_MS){const r=n?numberRows().find(x=>x.number===n):null;if(r?!r.pinned:!pageUnpin())break;await pause(500);await toTop(false);}
 log('Bấm Bỏ ghim '+(item&&item.title||'')+(Date.now()-start<CONFIRM_MS?' → đã tháo':' → trang chưa cập nhật, vẫn tính là đã tháo'));}

// "Kiểm tra cột số" / "Tìm thử": read-only checks, never click Ghim.
async function checkColumn(){const box=listBox();const seen=new Map();const add=()=>{for(const r of numberRows())seen.set(r.number,r);};add();
 if(box){await waitOwner();await scrollTo(box,0);add();for(let i=0;i<150;i++){const before=box.scrollTop;await scrollTo(box,before+box.clientHeight*.8);add();if(Math.abs(box.scrollTop-before)<1)break;}await scrollTo(box,0);}
 const nums=[...seen.keys()].sort((a,b)=>a-b);if(!nums.length)return 'Chưa đọc được ô số nào. Mở Bảng điều khiển LIVE có giỏ hàng, rồi khoanh lại "Một ô số thứ tự".';
 const missing=[];for(let n=nums[0];n<=nums[nums.length-1];n++)if(!seen.has(n))missing.push(n);const noButton=nums.filter(n=>{const r=seen.get(n);return !r.pin&&!r.unpin;});
 return 'Đọc được '+nums.length+' ô số · từ '+nums[0]+' tới '+nums[nums.length-1]+(missing.length?' · thiếu số: '+missing.slice(0,15).join(', '):' · không thiếu số nào')+(noButton.length?' · số chưa thấy nút Ghim: '+noButton.slice(0,15).join(', '):' · đủ nút Ghim');}
async function findTest(text){text=String(text||'').trim();if(!text)return 'Trống';
 if(isNumberText(text)){await clearSearch();const n=Number(text.replace(/\D/g,''));const row=await rowOf(n);const box=listBox();if(box)await scrollTo(box,0);return row?'Số '+n+': '+row.text.replace(/^\d+\s*/,'').slice(0,80)+(row.pin||row.unpin?'':' (chưa thấy nút Ghim)'):'Số '+n+': không có trong giỏ';}
 try{const {row,hits,loose}=await findByName(text);return !row?'"'+text+'": không tìm thấy':(hits.length>1||loose?'"'+text+'" ra '+hits.length+' món, sẽ ghim: ':'"'+text+'" → ')+'số '+row.number+' · '+row.text.replace(/^\d+\s*/,'').slice(0,80);}
 finally{await clearSearch();}}
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
function save(){if(!target)return;try{commitPick(id,id==='numberCell'?numberSpec(target):selector(target,['rows','products','bundleCards'].includes(id)));}catch(e){pickErrors.set(id,'Chưa chọn được · '+e.message);refreshFields();log(e.message);}clean();}
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
  const rows=cards.map((card,index)=>{const title=titleOf(card),key=cardKey(card);let number=null;if(cfg.productNumber){const labels=relativeMatches(cfg.productNumber,card).filter(visible);if(labels.length===1)number=readNumber(labels[0]);}return {title,key,number,index};});
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
$('check').onclick=()=>{refreshFields();if(tickBusy){log('Chờ thao tác đang chạy xác nhận xong.');return;}for(const k of NBLModules.keys){try{const c=prepare(k);cfg=c;log(k+': tài khoản '+identity()+'; LIVE '+liveTime());if(k==='pin'&&!c.cycle){log('pin: ghim xáo trộn đang tắt (để 0); ghim chèn lấy kịch bản từ app');}else if(k==='pin'){const rows=numberRows();log('pin: đang thấy '+rows.length+' ô số thứ tự; bấm "🔍 Tìm thử các món" để kiểm từng món');}else{one(c.input);one(c.send);chat();}log(k+': kiểm tra đọc trang đạt');}catch(e){log(k+': '+e.message);}}};
$('stop').onclick=()=>stop();
async function exclusive(work){const end=Date.now()+15000;while(findBusy&&Date.now()<end)await pause(300);if(findBusy)throw Error('Đang ghim/tìm món khác; thử lại sau');findBusy=true;try{return await work();}finally{findBusy=false;}}
$('checkColumn').onclick=async()=>{$('findResult').textContent='Đang cuộn kiểm tra cột số…';try{const text=await exclusive(checkColumn);$('findResult').textContent=text;log(text);}catch(e){$('findResult').textContent=e.message;}};
$('testPins').onclick=async()=>{const lines=String($('pins').value||'').split(/[\n;]+/).map(x=>x.trim()).filter(Boolean).slice(0,15);if(!lines.length){$('findResult').textContent='Chưa có món nào trong ô Sản phẩm muốn ghim.';return;}
 const out=[];$('findResult').textContent='Đang tìm thử '+lines.length+' món…';for(const line of lines){try{out.push(await exclusive(()=>findTest(line)));}catch(e){out.push(line+': '+e.message);}$('findResult').textContent=out.join(' | ');}log('Tìm thử: '+out.join(' | '));};
$('start').onclick=()=>{for(const k of NBLModules.keys)startModule(k);};
// 4.1.11 (owner, 26/10/2026): "ghim chèn" — the app sends, every 10 s, the NBL VIDEO
// position AND the pin script of the clip that is playing (made in the app by
// watching the clip and planting flags). A flag pauses the shuffle pin, pins its own
// product (found by NAME) for its own time, then the shuffle pins the next product.
let clipSync=null;
const FATAL=/captcha|xác minh|rời bảng|Tài khoản đã đổi|quay lại|Mục đã dừng/i;
function activeInsert(){const t=NBLPins.clipSeconds(clipSync,Date.now(),0);if(t===null||!clipSync.script?.length)return null;const x=NBLPins.insertAt(clipSync.script,t,clipSync.duration/1000);return x?{...x,t,key:clipSync.clip+'#'+x.index}:null;}
function clock(t){t=Math.max(0,Math.floor(t));return Math.floor(t/60)+':'+String(t%60).padStart(2,'0');}
async function insertTick(state){
 const ins=activeInsert(),generation=state.generation;
 if(!ins){
  if(!state.insKey)return false;
  // the flag is over: take its product down, the shuffle pins its next product at once
  const item=state.insItem;state.insKey=null;state.insItem=null;state.insName='';
  // shuffle on: its next pin replaces the inserted one at once; shuffle off: take it down
  if(item&&!cfg.cycle){try{await doUnpin(item);}catch(e){if(FATAL.test(e.message))throw e;log('Ghim chèn: chưa tháo được ('+e.message+')');}}
  if(state.pinCycle){state.pinCycle.phase='gap';state.pinCycle.current=null;}state.nextPinAt=Date.now();
  state.detail='Hết món chèn · ghim xáo trộn chạy tiếp';return true;}
 if(state.insKey!==ins.key){
  const nn=x=>NBL.norm(x).replace(/\s+/g,' '),same=state.insItem&&nn(state.insName)===nn(ins.name);
  state.insKey=ins.key;state.insTryAt=0;state.insWarned=false;
  if(!same){state.insItem=null;state.insName=ins.name;}
  if(state.pinCycle){state.pinCycle.phase='gap';state.pinCycle.current=null;}     // a new pin replaces the shuffle's pin
  log('Ghim chèn '+clock(ins.at)+': '+ins.name+' trong '+Math.round(ins.end-ins.at)+' giây');}
 if(state.insItem){state.detail='Ghim chèn: '+ins.name+' · tới '+clock(ins.end);return true;}
 if(Date.now()<state.insTryAt){state.detail='Ghim chèn: đang thử lại '+ins.name;return true;}
 state.insTryAt=Date.now()+5000;
 let item=null,why='';
 try{item=await doPin({mode:'name',text:ins.name,key:ins.name});if(!item)why='giỏ chưa có món tên "'+ins.name+'"';}
 catch(e){if(FATAL.test(e.message))throw e;why=e.message;}
 if(!state.running||generation!==state.generation)return true;
 if(item){state.insItem=item;state.insName=ins.name;state.lastProductKey=item.key;state.detail='Ghim chèn: '+ins.name;return true;}
 if(!state.insWarned){state.insWarned=true;log('Ghim chèn '+clock(ins.at)+': '+why+'; thử lại mỗi 5 giây tới hết thời gian của cờ');report('loi','Chrome · Ghim chèn: '+why,'');}
 state.detail='Ghim chèn: chưa ghim được '+ins.name;return true;}
async function tick(){if(tickBusy||!running||connectionLost||controlBusy)return;tickBusy=true;try{
 for(const module of NBLModules.keys)await manager.guard(module,async state=>{
 if(connectionLost)return;activeModule=module;cfg=state.config;snapshot=state.snapshot;timerLast=state.timerLast;assertContext();state.timerLast=timerLast;
 const elapsed=(Date.now()-state.started)/1000;
 if(module==='pin'&&await insertTick(state)){}
 else if(module==='pin'&&!cfg.cycle){state.detail='Ghim xáo trộn đang tắt · chờ món chèn theo kịch bản';}
 else if(module==='pin'){
  if(Date.now()>=state.nextPinAt){const cycle=state.pinCycle,generation=state.generation;
   if(cycle.phase==='hold'){await doUnpin(cycle.current);if(!state.running||generation!==state.generation)return;const seconds=cycle.afterUnpin(cfg.gapMin,cfg.gapMax);state.nextPinAt=Date.now()+seconds*1000;state.detail='Đang nghỉ không ghim · '+seconds+' giây';log('Nghỉ '+seconds+' giây (tới '+hhmmss(state.nextPinAt)+')');}
   else{state.missing=state.missing||new Map();let item=null,tries=0;
    // 4.1.13: no list read beforehand decides any more; each choice is really searched
    // (number column / search box). One that is really absent rests for 10 minutes.
    for(let attempt=0;attempt<cfg.pinJobs.length&&tries<3&&!item;attempt++){const candidate=cycle.next(),k=String(candidate.number||candidate.text);if((state.missing.get(k)||0)>Date.now())continue;if(cfg.pinJobs.length>1&&'#'+candidate.number===state.lastProductKey)continue;tries++;
     let failed=false;try{item=await doPin(candidate);}catch(e){if(FATAL.test(e.message))throw e;failed=true;log('Ghim '+k+': '+e.message);}
     if(!state.running||generation!==state.generation)return;if(!item&&!failed)state.missing.set(k,Date.now()+600000);}
    if(!state.running||generation!==state.generation)return;if(item){state.lastProductKey=item.key;const seconds=cycle.afterPin(item,cfg.pinMin,cfg.pinMax);state.nextPinAt=Date.now()+seconds*1000;state.detail='Đang giữ ghim: '+item.title;log('Giữ '+item.title+' '+seconds+' giây (tới '+hhmmss(state.nextPinAt)+')');}else{state.nextPinAt=Date.now()+30000;state.detail='Đang chờ món đã chọn · chưa ghim được món nào';log('Chưa ghim được món nào trong lần này (món không có trong giỏ được nghỉ 10 phút); thử lại sau 30 giây');}}
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
 // 4.1.8 (owner, 25/10/2026): the box still stayed open and the next cart failed.
 // Last resort: reload the LIVE page (the box is only on the page, the LIVE is over).
 // At most once every 3 minutes so a box that comes back never loops the page.
 if(reloadPage('đóng bảng tổng kết LIVE'))throw Object.assign(Error('Bảng tổng kết LIVE không đóng được; đang tải lại trang LIVE'),{busy:true});
 throw Error('Chưa đóng được bảng tổng kết LIVE trên Chrome');}
function reloadPage(why){if(running)return false;   // 4.1.9: pin/reply on = a LIVE is going; never reload under it
 let last=0;try{last=Number(sessionStorage.getItem('nblReloadAt')||0);}catch(e){}
 if(Date.now()-last<180000)return false;
 try{sessionStorage.setItem('nblReloadAt',String(Date.now()));}catch(e){}
 log('Tải lại trang LIVE để '+why+'.');report('hoat_dong','Chrome · Tải lại trang LIVE để '+why,'');
 setTimeout(()=>location.reload(),4000);return true;}
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
  try{await closeSummary();}catch(e){log(e.message);if(e.busy||summaryDialog())throw Object.assign(Error(e.busy?e.message:'Bảng tổng kết LIVE đang che trang; chưa thêm giỏ'),{busy:e.busy});}valid();
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
  controlResult={id:command.id,state:'done',bundle:name,index,added:outcome.ok[1],total:outcome.ok[2]};titlesAt=0;
  log('Đã thêm bộ sản phẩm ('+outcome.ok[1]+'/'+outcome.ok[2]+') · '+name);
 }catch(e){if(generation===controlEpoch&&controlResult.id===command.id){controlResult={id:command.id,state:'failed',error:e.message,...(e.busy?{busy:'1'}:{})};log('Giỏ hàng: '+e.message);}}
 finally{if(controlOwner===generation){controlBusy=false;controlOwner=0;}}}
$('addBundle').onclick=()=>{if(running||controlBusy){log('Dừng các mục và đợi thao tác trước kết thúc rồi thêm bộ.');return;}const c=read();let account;try{account=one(c.account).textContent.trim();}catch(e){log(e.message);return;}const v=String(c.bundleName||'').trim(),n=/^\d+$/.test(v)?Number(v):0;void prepareBundle({id:'manual-'+Date.now(),expectedAccount:account,bundle:n?'':v,bundleIndex:n,preLive:true,deadline:Date.now()/1000+150});};
async function finishLive(command){const c=read();if(command.expectedAccount&&one(c.account).textContent.trim()!==command.expectedAccount)throw Error('Nick khác; không đóng cửa sổ tổng kết');
 // 4.1: the summary can appear seconds after Studio ends; it only has an X icon.
 const end=Date.now()+60000;while(Date.now()<end){if(summaryDialog()){await closeSummary();return;}await delay(1000);}}
const handled=new Set();
// 4.1.11: product names of the cart, every 15 s, so the app can check its pin scripts.
let titlesAt=0,findResult={};
// 4.1.16 (owner, 27/10/2026): a captcha / security check on the LIVE page is reported to
// the app on every tick (the app sends it to Telegram 5 times in a row). Also TikTok's
// own captcha box, which is not always a [role=dialog].
function captchaText(){try{const box=[...document.querySelectorAll('[role=dialog],[role=alertdialog],[role=alert],[id*=captcha i],[class*=captcha i],[class*=verify i],iframe[src*=captcha i],iframe[src*=verify i]')].filter(e=>visible(e)&&!host.contains(e)).find(e=>e.tagName==='IFRAME'||/captcha|xác minh|verify|verification|kéo thanh trượt|trượt để|ghép hình|drag the slider/i.test(e.textContent||'')||/captcha/i.test(String(e.id||'')+' '+String(e.className&&e.className.baseVal!==undefined?e.className.baseVal:e.className||'')));
 return box?(String(box.textContent||'').replace(/\s+/g,' ').trim().slice(0,150)||'Trang TikTok Shop đang hiện ô xác minh / captcha'):'';}catch(e){return '';}}
let cartTitlesAt=0,cartTitlesLast="";
function cartTitlesUpdate(c){   // 4.3.0: product names for the AI in NBL (every 30 s, only when changed)
 if(Date.now()-cartTitlesAt<30000)return {};cartTitlesAt=Date.now();
 let t=[];try{const old=cfg;cfg=c||read();try{t=productCards().map(titleOf).filter(Boolean).slice(0,200);}finally{cfg=old;}}catch(e){return {};}
 const k=JSON.stringify(t);if(k===cartTitlesLast)return {};cartTitlesLast=k;return {cartTitles:t};
}
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
 // 4.3.4: NBL's own Chrome reads which NBL connection this page has (exact tab link) and that it is alive
 try{const d=document.documentElement;d.setAttribute('data-nbl-client',String(message.connectionId||'').split(':').pop());d.setAttribute('data-nbl-beat',String(now));}catch(e){}
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
}else if(c.action==='find_product'){const id=c.id,text=String(c.text||'').slice(0,120);findResult={id,state:'running'};void exclusive(()=>findTest(text)).then(t=>{findResult={id,state:'done',text:t};},e=>{findResult={id,state:'failed',text:e.message};});
}else if(c.action==='reload_extension'){if(running||controlBusy)error='Đang ghim/thêm giỏ; nạp lại sau';else{log('NBL vừa cập nhật: nạp lại tiện ích.');setTimeout(()=>{try{chrome.runtime.sendMessage({type:'reload_self'});}catch(e){}setTimeout(()=>location.reload(),2500);},500);}
}else if(c.action==='clip_sync'){clipSync={position:Number(c.position)||0,duration:Number(c.duration)||0,playing:Boolean(c.playing),at:Number(c.at)||0,received:Date.now(),clip:String(c.clip||''),script:NBLPins.cleanScript(c.script)};try{$('insertState').textContent=clipSync.script.length?'Đang dùng kịch bản '+clipSync.script.length+' cờ của clip '+(c.clipName||'')+'.':'Clip đang phát chưa có kịch bản.';}catch(e){}
}else if(c.action==='reload_page'){if(controlBusy)error='Đang thêm giỏ; chưa tải lại trang';else{if(running&&c.stopModules){manager.stop('all');renderModules();}if(running)error='Đang ghim/trả lời; không tải lại trang';else{log('App tải lại trang LIVE trước khi thêm giỏ / trước giờ phát.');report('hoat_dong','Chrome · Tải lại trang LIVE (chuẩn bị giỏ/phát)','');setTimeout(()=>location.reload(),1500);}}
}else if(c.action==='prepare_bundle'){if(running&&c.stopModules&&!controlBusy){manager.stop('all');suggestions=[];renderSuggestions();renderModules();log('Tắt ghim/trả lời của phiên LIVE trước để chuẩn bị giỏ.');}if(controlBusy||running){error='Dừng tương tác và đợi thao tác chuẩn bị trước';controlResult={id:c.id,state:'failed',error,busy:'1'};}else void prepareBundle(c);}else if(c.action==='start'){if(message.closing){acks.push({id:c.id,error:'App đang đóng'});continue;}if(c.expectedAccount){const previousConfig=cfg;try{cfg=read();if(identity()!==c.expectedAccount)throw Error('Tài khoản khác với phiên đã gắn trong app.');}catch(e){error=e.message;}finally{cfg=previousConfig;}}if(!error){if(c.module==='reply'){suggestions=[];renderSuggestions();}error=startModule(c.module,c.config);}}acks.push({id:c.id,error});}
 let account='Chưa chọn tài khoản';try{const previousConfig=cfg;cfg=read();try{account=identity();}finally{cfg=previousConfig;}}catch(e){}
 // Return immediately; potentially slow confirmations don't block the connection heartbeat.
 void saveConfig().catch(()=>{});const current=read(),serialized=JSON.stringify(current);let config;if(connectionNeedsConfig||!message.configAck||serialized!==lastSentConfig||Date.now()-lastSentConfigAt>60000){config=current;connectionNeedsConfig=false;lastSentConfig=serialized;lastSentConfigAt=Date.now();}
 respond({account,accountVerified:Boolean(account&&account!=='Chưa chọn tài khoản'),modules:manager.status(),acks,...(config?{config}:{}),...cartTitlesUpdate(current),...(findResult.id?{findResult}:{}),captcha:captchaText(),control:controlResult,reports:takeReports(),version:(chrome.runtime.getManifest?chrome.runtime.getManifest().version:'')});void tick();return false;
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
