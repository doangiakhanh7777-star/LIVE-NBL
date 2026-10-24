/* Official-page QR relay. Never reads cookies, passwords, localStorage, or QR contents.
 * Loaded only on the TikTok login/Shop hosts listed in the manifest. The broker
 * chooses the tab from the paired Chrome profile; this script never switches tabs.
 */
(function(root){
 'use strict';
 if(root.NBLShopLogin)return;
 const MAX_IMAGE=230000;
 const normalized=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/đ/g,'d').replace(/\s+/g,' ').trim();
 function officialPage(){
  try{const u=new URL(location.href);return u.protocol==='https:'&&(u.hostname==='shop.tiktok.com'||u.hostname==='www.tiktok.com'||u.hostname==='seller-vn.tiktok.com');}catch(_){return false;}
 }
 function safePage(){try{return location.origin+location.pathname;}catch(_){return '';}}
 function visible(e){
  if(!e||!e.isConnected)return false;
  const r=e.getBoundingClientRect(),s=getComputedStyle(e);
  return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&s.opacity!=='0'&&!e.closest('[aria-hidden="true"], [hidden]');
 }
 function labelledQr(e){
  let node=e;
  for(let i=0;node&&i<4;i++,node=node.parentElement){
   const labels=[node.id,node.className?.baseVal??node.className,node.getAttribute?.('aria-label'),node.getAttribute?.('alt'),node.getAttribute?.('data-e2e'),node.getAttribute?.('data-testid')].join(' ');
   if(/qr.?code|qrcode|ma qr|scan.*qr|quet.*qr/.test(normalized(labels)))return true;
  }
  return false;
 }
 function imageData(e){
  const w=e.tagName==='CANVAS'?e.width:e.naturalWidth,h=e.tagName==='CANVAS'?e.height:e.naturalHeight;
  if(w<100||h<100||w>2048||h>2048||w/h<.75||w/h>1.33)throw Error('Mã QR chưa tải xong.');
  const canvas=document.createElement('canvas'),scale=Math.min(1,512/Math.max(w,h));canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale);
  const ctx=canvas.getContext('2d');ctx.imageSmoothingEnabled=false;ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(e,0,0,canvas.width,canvas.height);
  const data=canvas.toDataURL('image/png');if(data.length>MAX_IMAGE)throw Error('Ảnh mã QR quá lớn.');return data;
 }
 function uniqueControl(pattern,selector){
  let candidates;
  if(selector){try{candidates=[...document.querySelectorAll(selector)];}catch(_){throw Error('Nút đăng nhập đã thay đổi; mở Chrome để kiểm tra.');}}
  else candidates=[...document.querySelectorAll('button,[role="button"],a')].filter(e=>pattern.test(normalized(e.innerText||e.textContent||e.getAttribute('aria-label'))));
  candidates=candidates.filter(visible).filter(e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true');
  if(candidates.length>1)throw Error('Có nhiều nút giống nhau; mở Chrome để chọn đúng nút.');
  return candidates[0]||null;
 }
 function capture(settings={}){
  const base={pageUrl:safePage(),observedAt:Date.now()/1000};
  if(!officialPage())return {...base,state:'unavailable',error:'Chỉ hiển thị mã đăng nhập từ trang TikTok chính thức.'};
  const page=normalized(document.body?.innerText||document.body?.textContent||'');
  if(!/\/login(?:\/|$)|\/passport|\/account\/login/.test(location.pathname)&&!/(log in|sign in|dang nhap)/.test(page))return {...base,state:'unavailable',error:'Chưa mở phần đăng nhập TikTok. Bấm Mở trang trên Chrome.'};
  // Expiry is read from the page, never inferred as successful authentication.
  if(/qr code (has )?expired|ma qr (da )?het han|ma da het han/.test(page))return {...base,state:'expired',error:'Mã QR đã hết hạn. Bấm Lấy mã mới.'};
  let candidates;
  try{candidates=settings.qrSelector?[...document.querySelectorAll(settings.qrSelector)]:[...document.querySelectorAll('canvas,img')].filter(labelledQr);}
  catch(_){return {...base,state:'unavailable',error:'Vị trí mã QR đã thay đổi. Mở Chrome để kiểm tra.'};}
  candidates=candidates.filter(visible).filter(e=>['CANVAS','IMG'].includes(e.tagName));
  const images=[];let lastError='';
  for(const element of candidates){try{const data=imageData(element);if(!images.includes(data))images.push(data);}catch(e){lastError=e.message||'Không đọc được ảnh mã QR.';}}
  if(images.length===1)return {...base,state:'qr',qrDataUrl:images[0]};
  if(images.length>1)return {...base,state:'unavailable',error:'Trang có nhiều mã QR; mở Chrome để chọn đăng nhập.'};
  return {...base,state:'waiting',error:lastError?'Không đọc được ảnh QR từ trang này. Bấm Mở trang trên Chrome.':'Đang chờ mã QR từ trang TikTok. Nếu chưa hiện, bấm Mở trang trên Chrome.'};
 }
 function chooseQr(settings={}){
  if(!officialPage())throw Error('Đây không phải trang TikTok chính thức.');
  const element=uniqueControl(/^(use qr code|log in with qr code|dang nhap bang ma qr|su dung ma qr|quet ma qr)$/,settings.qrModeSelector);
  if(element)element.click();return {changed:Boolean(element)};
 }
 function refresh(settings={}){
  if(!officialPage())throw Error('Đây không phải trang TikTok chính thức.');
  const element=uniqueControl(/^(refresh|refresh qr code|reload qr code|lam moi|tai lai|lay ma moi|lam moi ma qr)$/,settings.qrRefreshSelector);
  if(!element)return {changed:false,error:'Không thấy nút lấy mã mới. Bấm Mở trang trên Chrome.'};
  element.click();return {changed:true};
 }
 root.NBLShopLogin={capture,chooseQr,refresh};
 if(typeof chrome!=='undefined'&&chrome.runtime?.onMessage){
  chrome.runtime.onMessage.addListener((message,sender,respond)=>{
   if(sender.id!==chrome.runtime.id)return;
   const operations={'nbl-shop-login-capture':capture,'nbl-shop-login-choose-qr':chooseQr,'nbl-shop-login-refresh':refresh};
   const operation=operations[message?.type];if(!operation)return;
   try{
    const result=operation(message.settings||{});
    // tabs.sendMessage reaches every matching frame; an empty parent frame must
    // not win the race against the actual QR in TikTok's login iframe.
    if(message.type==='nbl-shop-login-capture'&&!['qr','expired'].includes(result.state))return;
    respond(result);
   }catch(e){if(message.type!=='nbl-shop-login-capture')respond({state:'unavailable',pageUrl:safePage(),observedAt:Date.now()/1000,error:String(e.message||e)});}
  });
 }
})(globalThis);
