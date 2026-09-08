/* Map-only bridge: make every drawn route visibly startable on iPhone. */
(()=>{'use strict';
if(window.__aquaRouteStartFix)return;window.__aquaRouteStartFix=true;
const $=(s,r=document)=>r.querySelector(s);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let lastLegacySignature='';
function state(){try{return window.Alpine?.$data?.(document.body)||document.body?._x_dataStack?.[0]||null}catch{return null}}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function toast(msg){try{window.alert(msg)}catch{}}
function ensureCTA(){
  let cta=$('#aqst-route-start-cta');if(cta)return cta;
  const frame=$('.aq-map-frame');if(!frame)return null;
  cta=document.createElement('div');cta.id='aqst-route-start-cta';cta.hidden=true;
  cta.innerHTML='<div class="aqst-route-start-copy"><small>مسیر آماده است</small><b id="aqst-route-start-title">شروع مسیریابی</b><span id="aqst-route-start-meta"></span></div><button type="button" id="aqst-route-start-button">▶ شروع مسیریابی</button>';
  frame.appendChild(cta);return cta;
}
function hideCTA(){const cta=$('#aqst-route-start-cta');if(cta)cta.hidden=true}
function showCTA({title='شروع مسیریابی',meta='',onStart}){
  const cta=ensureCTA();if(!cta)return;
  $('#aqst-route-start-title').textContent=title;
  $('#aqst-route-start-meta').textContent=meta||'';
  const btn=$('#aqst-route-start-button');
  btn.disabled=false;btn.textContent='▶ شروع مسیریابی';btn.onclick=async()=>{
    if(btn.disabled)return;btn.disabled=true;btn.textContent='در حال شروع…';
    try{await onStart?.()}catch(e){toast(e?.message||'شروع مسیریابی ممکن نشد')}finally{btn.disabled=false;btn.textContent='▶ شروع مسیریابی'}
  };
  cta.hidden=false;
}
function stopLabel(stop){return stop?.map_label||stop?.name||[stop?.first_name,stop?.last_name].filter(Boolean).join(' ')||'مقصد اول'}
function legacySignature(s){const plan=s?.routePlan||[];return plan.map(x=>String(x?.id||'')+':'+String(x?.latitude||'')+':'+String(x?.longitude||'')).join('|')}
async function bridgeLegacyStop(stop){
  const id=String(stop?.id||'');
  if(!id)throw Error('شناسه مقصد اول پیدا نشد');
  const input=$('#aqst-customer-search');
  if(!input)throw Error('بخش مسیریابی هوشمند هنوز آماده نشده');
  const query=String(stop?.phone||stop?.map_label||stop?.name||stop?.address||'').trim();
  if(!query)throw Error('اطلاعات مقصد برای شروع مسیر کافی نیست');
  input.value=query;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();
  let result=null;
  for(let i=0;i<18;i++){
    await sleep(180);
    result=document.querySelector(`.aqst-result[data-id="${CSS.escape(id)}"]`);
    if(result)break;
  }
  if(!result){
    input.value=stop?.address||stopLabel(stop);input.dispatchEvent(new Event('input',{bubbles:true}));
    for(let i=0;i<18;i++){await sleep(180);result=document.querySelector(`.aqst-result[data-id="${CSS.escape(id)}"]`);if(result)break}
  }
  if(!result)throw Error('مقصد اول در جستجوی مشتری پیدا نشد');
  result.click();
  for(let i=0;i<12;i++){
    await sleep(120);const start=$('#aqst-start-selected');
    if(start){hideCTA();start.click();return}
  }
  throw Error('دکمه شروع مقصد آماده نشد');
}
function syncLegacyCTA(){
  const s=state(),plan=s?.routePlan||[];
  if(!plan.length){lastLegacySignature='';return}
  const sig=legacySignature(s);if(!sig)return;
  if(sig===lastLegacySignature&&!$('#aqst-route-start-cta')?.hidden)return;
  lastLegacySignature=sig;
  const first=plan[0],count=plan.length,meta=[count>1?`مقصد ۱ از ${new Intl.NumberFormat('fa-IR').format(count)}`:'مقصد اول',first?.address||''].filter(Boolean).join(' • ');
  showCTA({title:stopLabel(first),meta,onStart:()=>bridgeLegacyStop(first)});
}
function hookSelectedRoute(){
  document.addEventListener('click',e=>{
    const show=e.target.closest?.('#aqst-show-route');if(!show)return;
    setTimeout(()=>{
      const start=$('#aqst-start-selected');if(!start)return;
      const title=$('#aqst-selected b')?.textContent?.trim()||'مقصد انتخاب‌شده';
      const meta=$('#aqst-selected small')?.textContent?.trim()||'';
      showCTA({title,meta,onStart:async()=>{hideCTA();start.click()}});
    },650);
  },true);
}
function monitor(){
  const nav=$('#aqst-nav');if(nav&&!nav.hidden){hideCTA();return}
  const s=state();if(s?.routePlan?.length)syncLegacyCTA();
}
hookSelectedRoute();
const style=document.createElement('style');style.id='aqst-route-start-style';style.textContent=`
.aq-map-frame{position:relative!important}
#aqst-route-start-cta{position:absolute;z-index:950;left:12px;right:12px;bottom:12px;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 12px;border-radius:18px;background:rgba(4,20,28,.94);border:1px solid rgba(72,204,255,.42);box-shadow:0 14px 38px rgba(0,0,0,.34);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);color:#fff;direction:rtl}
#aqst-route-start-cta[hidden]{display:none!important}.aqst-route-start-copy{display:grid;gap:2px;min-width:0;text-align:right}.aqst-route-start-copy small{font-size:.68rem;color:#9adfff;font-weight:850}.aqst-route-start-copy b{font-size:.9rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.aqst-route-start-copy span{font-size:.69rem;color:#b8c7d1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:48vw}#aqst-route-start-button{border:0;border-radius:14px;padding:11px 14px;white-space:nowrap;background:linear-gradient(135deg,#0aa7ff,#20d5ff);color:#00131d;font-weight:950;box-shadow:0 8px 24px rgba(0,174,255,.28)}#aqst-route-start-button:disabled{opacity:.62}@media(max-width:520px){#aqst-route-start-cta{left:8px;right:8px;bottom:8px;padding:9px 10px;border-radius:16px}.aqst-route-start-copy span{max-width:42vw}#aqst-route-start-button{padding:10px 11px;font-size:.78rem}}
`;document.head.appendChild(style);
setInterval(monitor,350);setTimeout(monitor,500);setTimeout(monitor,1300);
})();
