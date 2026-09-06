(()=>{
  if(window.__aquaRound7UserFixes)return;
  window.__aquaRound7UserFixes=true;

  const dailySection=()=>[...document.querySelectorAll('section')].find(el=>(el.getAttribute('x-show')||'').includes("page==='daily'"));

  const patchDailyTemplate=()=>{
    const section=dailySection();
    if(!section)return;
    const tpl=[...section.querySelectorAll('template')].find(el=>(el.getAttribute('x-for')||'').includes('d.completedJobs'));
    if(!tpl)return;
    tpl.innerHTML=`<div class="px-4 py-3 border-b flex items-center justify-between gap-3" style="border-color:var(--line)" data-aqua-daily-completed-row>
      <b class="min-w-0 truncate" x-text="dailySurname(j)"></b>
      <div class="flex items-center gap-2 shrink-0">
        <b class="text-emerald-500" x-text="money(j.received_amount)+' تومان'"></b>
        <button type="button" @click="openServiceEdit(j)" class="btn soft !py-1.5 !px-3 no-print" data-aqua-daily-edit>ویرایش</button>
      </div>
    </div>`;
  };

  const patchRenderedRows=()=>{
    const section=dailySection();
    if(!section)return;
    const completedBlocks=[...section.querySelectorAll('[x-show="d.completedJobs.length"]')];
    for(const block of completedBlocks){
      const rows=[...block.querySelectorAll(':scope > div.px-4.py-3.border-b')];
      for(const row of rows){
        if(row.querySelector('[data-aqua-daily-edit]'))continue;
        let scope=null;try{scope=window.Alpine?.$data?.(row)}catch{}
        const job=scope?.j;
        if(!job)continue;
        const action=document.createElement('button');
        action.type='button';action.textContent='ویرایش';action.className='btn soft !py-1.5 !px-3 no-print';action.dataset.aquaDailyEdit='1';
        action.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();let live=null;try{live=window.Alpine?.$data?.(row)}catch{};const s=live||scope;const current=s?.j||job;if(typeof s?.openServiceEdit==='function')s.openServiceEdit(current)});
        const tail=row.lastElementChild;
        if(tail&&tail.tagName==='DIV')tail.appendChild(action);else row.appendChild(action);
      }
    }
  };

  // Round 5 rewrites the daily markup during parsing. Patch the final template
  // immediately before Alpine compiles it, then keep a native fallback for iOS.
  document.addEventListener('alpine:init',patchDailyTemplate,{once:true});
  document.addEventListener('alpine:initialized',()=>{patchRenderedRows();setTimeout(patchRenderedRows,120);setTimeout(patchRenderedRows,700)},{once:true});
  const startObserver=()=>{const root=document.body;if(!root)return;const observer=new MutationObserver(()=>patchRenderedRows());observer.observe(root,{childList:true,subtree:true});setTimeout(patchRenderedRows,250)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',startObserver,{once:true});else startObserver();
})();
