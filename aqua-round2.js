(()=>{
  if(window.__aquaRound2Ui)return;
  window.__aquaRound2Ui=true;
  const previous=window.app;
  if(typeof previous!=='function')return;

  window.app=function(){
    const state=previous();

    const oldLoadBale=state.loadBaleJobs?.bind(state);
    state.loadBaleJobs=async function(tab=null){
      if(tab)this.baleTab=tab;
      const result=await oldLoadBale?.(tab);
      const wanted=String(this.baleTab||'new');
      if(wanted!=='all')this.baleJobs=(this.baleJobs||[]).filter(job=>String(job?.status||'')===wanted);
      return result;
    };

    const oldCancelBale=state.confirmBaleCancel?.bind(state);
    state.confirmBaleCancel=async function(){
      const id=String(this.baleCancelJob?.id||'');
      const result=await oldCancelBale?.();
      if(id){
        this.baleJobs=(this.baleJobs||[]).filter(job=>String(job?.id||'')!==id);
        try{await this.loadBaleCounts?.()}catch{}
      }
      return result;
    };

    const oldCompleteBale=state.confirmBaleComplete?.bind(state);
    state.confirmBaleComplete=async function(){
      const id=String(this.baleCompleteJob?.id||'');
      const result=await oldCompleteBale?.();
      if(id&&this.baleTab==='new')this.baleJobs=(this.baleJobs||[]).filter(job=>String(job?.id||'')!==id);
      return result;
    };

    const oldRegisterSmart=state.registerSmart?.bind(state);
    state.registerSmart=async function(){
      const pending=this.baleSmartJob?{id:String(this.baleSmartJob.id||'')}:null;
      const result=await oldRegisterSmart?.();
      if(!pending?.id)return result;
      try{
        let fresh=await this.api('/bale/jobs?status=new&_='+Date.now());
        let remains=(fresh||[]).some(job=>String(job?.id||'')===pending.id);
        const smartCleared=!String(this.smartText||'').trim()&&!this.smartParsed;
        if(remains&&smartCleared){
          try{
            await this.api('/bale/jobs/'+pending.id+'/finalize',{method:'POST',body:'{}'});
            this.baleSmartJob=null;
          }catch(error){
            const message=String(error?.message||'');
            if(!/قبلاً تعیین تکلیف|already/i.test(message))this.toast?.(message||'ثبت انجام شد ولی بستن کار بله کامل نشد','error');
          }
          fresh=await this.api('/bale/jobs?status=new&_='+Date.now());
        }
        if(this.baleTab==='new')this.baleJobs=(fresh||[]).filter(job=>String(job?.status||'')==='new');
        await this.loadBaleCounts?.();
      }catch(error){
        console.warn('Aqua Bale post-register refresh',error);
      }
      return result;
    };

    state.requestAquaNotificationAccess=async function(){
      const ios=/iPhone|iPad|iPod/i.test(navigator.userAgent);
      const standalone=(window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true;
      const tell=(message,type='info')=>this.toast?this.toast(message,type):alert(message);
      if(ios&&!standalone){
        tell('برای نوتیف آیفون، AquaGold را از آیکون Home Screen باز کن و دوباره این دکمه را بزن.','error');
        return;
      }
      await this.enableAquaPush?.();
      await this.refreshPushStatus?.();
    };

    return state;
  };

  const mount=()=>{
    if(!document.getElementById('aqua-round2-style')){
      const style=document.createElement('style');
      style.id='aqua-round2-style';
      style.textContent=`
        .aq-map-marker span{background:#ef3340!important;border-color:#fff!important;box-shadow:0 4px 14px rgba(239,51,64,.42)!important}
        #monthlyChart,#yearlyChart,#serviceChart{display:block!important;width:100%!important;height:270px!important;max-height:270px!important;min-height:270px!important}
        #financeDonutChart,#financePolarChart{display:block!important;width:100%!important;height:280px!important;max-height:280px!important;min-height:280px!important}
        section[x-show="page==='finance'"] .card{min-width:0!important;overflow:hidden!important}
        section[x-show="page==='finance'"] canvas{box-sizing:border-box!important}
        @media(max-width:520px){
          #monthlyChart,#yearlyChart,#serviceChart{height:235px!important;max-height:235px!important;min-height:235px!important}
          #financeDonutChart,#financePolarChart{height:245px!important;max-height:245px!important;min-height:245px!important}
        }
      `;
      document.head.appendChild(style);
    }

    const pushCard=document.getElementById('aqua-ios-push-card');
    const primary=pushCard?.querySelector('button.btn.primary');
    if(primary&&!primary.dataset.round2Push){
      primary.dataset.round2Push='1';
      primary.removeAttribute('x-text');
      primary.setAttribute('@click','requestAquaNotificationAccess()');
      primary.textContent='دادن دسترسی نوتیف آیفون';
    }
  };

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
