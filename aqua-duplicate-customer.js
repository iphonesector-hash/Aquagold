/* Duplicate customer confirmation + history + stable Smart-register idempotency. */
(()=>{
  const previous=window.app;if(typeof previous!=='function')return;
  const digits={'۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9','٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9'};
  const normalizePhone=value=>{let d=String(value||'').replace(/[۰-۹٠-٩]/g,n=>digits[n]).replace(/\D/g,'');if(d.startsWith('0098'))d='0'+d.slice(4);else if(d.startsWith('98'))d='0'+d.slice(2);else if(d.length===10&&d.startsWith('9'))d='0'+d;return d};
  window.app=function(){
    const state=previous();
    Object.assign(state,{smartDuplicateCandidates:[],smartDuplicateHistory:{},smartDuplicateHistoryBusy:false,smartRegisterIdempotency:null});
    const oldAnalyze=state.analyzeSmart?.bind(state);
    const oldSuggestions=state.loadSmartSuggestions?.bind(state);
    const oldRegister=state.registerSmart?.bind(state);

    state.findSmartExactDuplicates=function(){
      const phones=(this.smartParsed?.phones||[]).map(normalizePhone).filter(Boolean);
      if(!phones.length)return [];
      return (this.smartSuggestions||[]).filter(item=>phones.includes(normalizePhone(item.phone)));
    };

    state.renderSmartDuplicateDialog=function(){
      const candidates=this.smartDuplicateCandidates||[];
      let modal=document.getElementById('aquaSmartDuplicateModal');
      if(!candidates.length){modal?.remove();return}
      if(!modal){
        modal=document.createElement('div');modal.id='aquaSmartDuplicateModal';modal.style.cssText='position:fixed;inset:0;z-index:2147482000;background:#0009;padding:16px;display:flex;align-items:center;justify-content:center';
        document.body.appendChild(modal);
      }
      modal.replaceChildren();
      const box=document.createElement('section');box.className='card p-5 w-full max-w-xl max-h-[86vh] overflow-auto';modal.appendChild(box);
      const heading=document.createElement('h3');heading.className='section-title';heading.textContent='این شماره قبلاً ثبت شده';box.appendChild(heading);
      const hint=document.createElement('p');hint.className='text-sm muted mt-2';hint.textContent='برای جلوگیری از ساخت مشتری تکراری، مشتری موجود را بررسی و انتخاب کن. ثبت نهایی تا انتخاب یکی از موارد زیر متوقف می‌ماند.';box.appendChild(hint);
      for(const customer of candidates){
        const row=document.createElement('div');row.className='glass rounded-2xl p-3 mt-3';
        const name=document.createElement('b');name.textContent=[customer.first_name,customer.last_name].filter(Boolean).join(' ')||customer.map_label||customer.phone||'مشتری';row.appendChild(name);
        const detail=document.createElement('div');detail.className='text-sm muted mt-1';detail.textContent=[customer.phone,customer.address].filter(Boolean).join(' • ');row.appendChild(detail);
        const actions=document.createElement('div');actions.className='flex flex-wrap gap-2 mt-3';
        const choose=document.createElement('button');choose.type='button';choose.className='btn primary !py-2';choose.textContent=String(this.smartCustomerId)===String(customer.id)?'✓ انتخاب شده':'انتخاب این مشتری';choose.addEventListener('click',()=>{this.smartCustomerId=String(customer.id);this.smartDuplicateCandidates=this.findSmartExactDuplicates();this.renderSmartDuplicateDialog();this.toast?.('مشتری موجود برای ثبت انتخاب شد','success')});actions.appendChild(choose);
        const history=document.createElement('button');history.type='button';history.className='btn soft !py-2';history.textContent='مشاهده سابقه';history.addEventListener('click',()=>this.loadSmartDuplicateHistory(customer,row));actions.appendChild(history);row.appendChild(actions);
        const historyBox=document.createElement('div');historyBox.dataset.history=String(customer.id);historyBox.className='mt-3';row.appendChild(historyBox);
        const cached=this.smartDuplicateHistory?.[String(customer.id)];if(cached)this.paintSmartDuplicateHistory(historyBox,cached);
        box.appendChild(row);
      }
      const close=document.createElement('button');close.type='button';close.className='btn glass w-full mt-4';close.textContent='فعلاً بستن';close.addEventListener('click',()=>modal.remove());box.appendChild(close);
    };

    state.paintSmartDuplicateHistory=function(host,data){
      host.replaceChildren();const items=data?.items||[];
      if(!items.length){const empty=document.createElement('div');empty.className='text-sm muted';empty.textContent='سابقه سرویسی ثبت نشده';host.appendChild(empty);return}
      for(const job of items.slice(0,10)){
        const line=document.createElement('div');line.className='text-sm border-t border-white/10 py-2';
        line.textContent=`${this.persianDateTime?.(job.date)||job.date||''} • ${job.service_type||'سرویس'} • ${this.money?.(job.received_amount||0)||job.received_amount||0} تومان`;
        host.appendChild(line);
      }
    };

    state.loadSmartDuplicateHistory=async function(customer,row){
      const id=String(customer?.id||'');if(!id||this.smartDuplicateHistoryBusy)return;
      this.smartDuplicateHistoryBusy=true;
      try{
        const data=await this.api(`/customers/${encodeURIComponent(id)}/jobs?per_page=10`);
        this.smartDuplicateHistory={...(this.smartDuplicateHistory||{}),[id]:data};
        const host=row?.querySelector?.(`[data-history="${CSS.escape(id)}"]`);if(host)this.paintSmartDuplicateHistory(host,data);
      }catch(error){alert(error?.message||'خواندن سابقه مشتری انجام نشد')}
      finally{this.smartDuplicateHistoryBusy=false}
    };

    state.analyzeSmart=async function(...args){
      this.smartDuplicateCandidates=[];this.smartDuplicateHistory={};this.smartRegisterIdempotency=null;
      return oldAnalyze?.(...args);
    };

    state.loadSmartSuggestions=async function(...args){
      const result=await oldSuggestions?.(...args);
      this.smartDuplicateCandidates=this.findSmartExactDuplicates();
      if(this.smartDuplicateCandidates.length){
        const selected=this.smartDuplicateCandidates.find(c=>String(c.id)===String(this.smartCustomerId));
        if(!selected)this.smartCustomerId='';
        setTimeout(()=>this.renderSmartDuplicateDialog(),0);
      }
      return result;
    };

    state.registerSmart=async function(...args){
      const exact=this.findSmartExactDuplicates();
      if(exact.length&&!exact.some(c=>String(c.id)===String(this.smartCustomerId))){
        this.smartDuplicateCandidates=exact;this.renderSmartDuplicateDialog();alert('این شماره متعلق به مشتری موجود است؛ ابتدا همان مشتری را انتخاب کن.');return false;
      }
      let successful=false;
      const savedApi=this.api;
      this.api=async (path,opts={})=>{
        if(path==='/smart/register'&&String(opts?.method||'GET').toUpperCase()==='POST'){
          const body=String(opts?.body||'');
          if(!this.smartRegisterIdempotency||this.smartRegisterIdempotency.body!==body)this.smartRegisterIdempotency={body,key:crypto.randomUUID()};
          const headers={...(opts.headers||{}),'Idempotency-Key':this.smartRegisterIdempotency.key};
          try{const out=await savedApi.call(this,path,{...opts,headers});successful=true;return out}
          catch(error){if(error?.status&&error.status<500)this.smartRegisterIdempotency=null;throw error}
        }
        return savedApi.call(this,path,opts);
      };
      try{return await oldRegister?.(...args)}
      finally{this.api=savedApi;if(successful)this.smartRegisterIdempotency=null}
    };
    return state;
  };
})();
