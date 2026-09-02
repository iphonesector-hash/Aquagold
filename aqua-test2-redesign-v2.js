(()=>{
  if(window.__aquaTest2RedesignV2)return;
  window.__aquaTest2RedesignV2=true;

  const qs=(s,r=document)=>r.querySelector(s);
  const qsa=(s,r=document)=>[...r.querySelectorAll(s)];

  const tehranNow=()=>{
    const d=new Date();
    const date=new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(d).replace(/[،,]\s*$/,'');
    const time=new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);
    return `${date} • ${time}`;
  };

  const clickByText=(needle)=>{
    const el=qsa('button').find(b=>String(b.textContent||'').replace(/\s+/g,' ').includes(needle));
    el?.click();
  };

  async function latestLogo(){
    try{
      const res=await fetch('/ui-visual-polish.js?v=20260902-test2-logo-v2',{cache:'no-store'});
      const text=await res.text();
      const m=text.match(/const LOGO='([^']+)'/);
      if(m?.[1])return m[1];
    }catch{}
    return '/assets/brand-sector.svg';
  }

  async function mountSplash(){
    document.getElementById('aqBootScreen')?.remove();
    document.querySelector('.aq-v2-splash')?.remove();
    const d=document.createElement('div');
    d.className='aq-v2-splash';
    d.innerHTML=`<div class="aq-v2-splash-inner"><img class="aq-v2-splash-logo" alt="Aqua sector"><div class="aq-v2-splash-brand">AQUA • SECTOR</div><div class="aq-v2-progress"><span></span></div><small>در حال آماده‌سازی مرکز خدمات هوشمند…</small></div>`;
    document.body.appendChild(d);
    const logo=await latestLogo();
    const img=qs('.aq-v2-splash-logo',d);if(img)img.src=logo;
    setTimeout(()=>{d.classList.add('out');setTimeout(()=>d.remove(),600)},2500);
    setTimeout(()=>d.remove(),4000);
  }

  function mountMobileDashboard(){
    const dash=qsa('section').find(s=>(s.getAttribute('x-show')||'').includes("page==='dashboard'"));
    if(!dash||qs('#aq-v2-mobile-head',dash))return;
    const head=document.createElement('div');
    head.id='aq-v2-mobile-head';
    head.innerHTML=`
      <div class="aq-v2-welcome">
        <div class="aq-v2-brandline"><div><b>AquaGold</b><div class="aq-v2-date" id="aq-v2-date"></div></div><span class="aq-v2-badge">SECTOR • SMART WATER</span></div>
        <button type="button" class="aq-v2-search" id="aq-v2-search"><span>جستجوی مشتری، شماره تماس، پلاک یا آدرس…</span><strong>⌕</strong></button>
      </div>
      <div class="aq-v2-shortcuts">
        <button type="button" class="aq-v2-shortcut" data-aq-go="ثبت هوشمند"><i>⚡</i><span>ثبت سریع</span></button>
        <button type="button" class="aq-v2-shortcut" data-aq-go="گزارش روزانه"><i>▣</i><span>کارهای روزانه</span></button>
        <button type="button" class="aq-v2-shortcut" data-aq-go="هوش مصنوعی"><i>✦</i><span>آریا</span></button>
        <button type="button" class="aq-v2-shortcut" data-aq-go="نقشه"><i>⌖</i><span>نقشه مشتریان</span></button>
      </div>`;
    dash.prepend(head);
    const setDate=()=>{const e=qs('#aq-v2-date');if(e)e.textContent=tehranNow()};setDate();setInterval(setDate,30000);
    qs('#aq-v2-search')?.addEventListener('click',()=>{
      const top=qsa('button').find(b=>(b.getAttribute('aria-label')||'').includes('جست'));
      top?.click();
    });
    qsa('[data-aq-go]',head).forEach(btn=>btn.addEventListener('click',()=>clickByText(btn.dataset.aqGo)));
  }

  function refineDashboard(){
    const dash=qsa('section').find(s=>(s.getAttribute('x-show')||'').includes("page==='dashboard'"));
    if(!dash)return;
    const recent=qsa('h3',dash).find(x=>String(x.textContent||'').includes('آخرین سرویس'))?.closest('.card');
    if(recent&&!recent.dataset.v2Collapsible){
      recent.dataset.v2Collapsible='1';
      const header=recent.firstElementChild;
      const rows=[...recent.children].filter((x,i)=>i>0);
      rows.forEach(x=>x.classList.add('aq-v2-recent-row'));
      if(header){
        const toggle=document.createElement('button');toggle.type='button';toggle.className='btn soft !py-2';toggle.textContent='نمایش';
        header.appendChild(toggle);
        rows.forEach(x=>x.style.display='none');
        let open=false;toggle.addEventListener('click',()=>{open=!open;rows.forEach(x=>x.style.display=open?'':'none');toggle.textContent=open?'بستن':'نمایش'});
      }
    }
  }

  function boot(){
    document.documentElement.dataset.aquaUi='test2-v2';
    mountMobileDashboard();
    refineDashboard();
    mountSplash();
    const obs=new MutationObserver(()=>{mountMobileDashboard();refineDashboard()});
    obs.observe(document.body,{subtree:true,childList:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
