// 4.3.0: cầu nối — popup chỉ hiện trạng thái kết nối, không có gì để thiết lập.
(async()=>{
 const el=document.getElementById('state');
 try{
  const tabs=await chrome.tabs.query({url:['https://shop.tiktok.com/streamer/live/*']});
  const r=await chrome.runtime.sendMessage({type:'status'});const on=(r&&r.tabs||[]).filter(t=>t.connected);
  if(on.length){el.innerHTML='<span class="ok">✓ Đã kết nối NBL</span> · '+on.length+' trang LIVE';}
  else if(tabs.length){el.innerHTML='<span class="no">Chưa kết nối.</span> Mở NBL LIVE, vào trang Giỏ hàng bấm "Mở Chrome &amp; tự ghép".';}
  else{el.innerHTML='<span class="no">Chưa mở trang LIVE.</span> Mở NBL LIVE rồi bấm "Mở Chrome &amp; tự ghép".';}
 }catch(e){el.textContent=e.message;}
})();
