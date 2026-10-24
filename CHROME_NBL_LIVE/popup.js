(async()=>{
 const $=id=>document.getElementById(id);
 const tabs=await chrome.tabs.query({url:['https://shop.tiktok.com/*']});
 for(const t of tabs){const o=document.createElement('option');o.value=t.id;o.textContent=(t.title||'Bảng LIVE')+' · '+t.id;$('tabs').append(o);}
 // 4.0: pairings live in nblPairs (3.9 only read the old nblPair key, so the code was never prefilled).
 const {nblPairs={},nblPair}=await chrome.storage.local.get(['nblPairs','nblPair']);const known=Object.values(nblPairs)[0]||nblPair;if(known?.token)$('token').value=known.token;
 const paired=new Set(Object.keys(nblPairs));for(const o of $('tabs').options)if(paired.has(o.value))o.textContent='✓ '+o.textContent;
 $('state').textContent=tabs.length?'Chọn tab rồi bấm Kết nối.':'Mở trang Bảng điều khiển LIVE của TikTok Shop trước.';
 $('pair').onclick=async()=>{try{const r=await chrome.runtime.sendMessage({type:'pair',tabId:Number($('tabs').value),token:$('token').value.trim()});$('state').textContent=r.ok?'Đã yêu cầu kết nối; kiểm tra trạng thái trong app.':r.error;}catch(e){$('state').textContent=e.message;}};
 $('stop').onclick=async()=>{await chrome.runtime.sendMessage({type:'unpair',tabId:Number($('tabs').value)});$('state').textContent='Đã ngắt kết nối.';};
})();
