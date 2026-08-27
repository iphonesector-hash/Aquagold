/* Helpful commerce zero-states plus AquaGold v6.1 login resilience. */
(()=>{
  const base=window.app;if(typeof base!=='function')return;
  window.app=function(){
    const s=base();
    s.enhanceCommerceEmptyStates=function(){
      let productSection=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='products'"));
      if(productSection&&!productSection.querySelector('.aqua-product-empty')){
        let empty=document.createElement('div');empty.setAttribute('x-show','!catalogProducts.length');empty.className='card empty aqua-product-empty';
        empty.innerHTML=`<div class="empty-icon" x-html="icon('products')"></div><b>کاتالوگ آماده دریافت اطلاعات است</b><p class="text-sm muted mt-2">کاتالوگ پایه با به‌روزرسانی دیتابیس اضافه می‌شود؛ مدیر هم می‌تواند محصول اختصاصی بسازد.</p><button x-show="canAdmin" @click="openProductEditor()" class="btn primary mt-4">افزودن اولین محصول</button>`;
        productSection.appendChild(empty);if(window.Alpine)Alpine.initTree(empty)
      }
      let invoiceSection=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='invoices'"));let invoiceEmpty=invoiceSection?.querySelector('.empty');
      if(invoiceEmpty&&!invoiceEmpty.classList.contains('aqua-invoice-empty')){
        invoiceEmpty.classList.add('aqua-invoice-empty');invoiceEmpty.innerHTML=`<div class="empty-icon" x-html="icon('invoices')"></div><b>هنوز فاکتوری صادر نشده</b><p class="text-sm muted mt-2">فاکتور واقعی بساز یا یک محصول را از کاتالوگ مستقیم به فاکتور اضافه کن.</p><div class="flex justify-center gap-2 mt-4"><button @click="newInvoice()" class="btn primary">فاکتور جدید</button><button @click="go('products')" class="btn soft">دیدن محصولات</button></div>`;if(window.Alpine)Alpine.initTree(invoiceEmpty)
      }
    };
    s.login=async function(){
      if(this.busy)return;
      this.busy=true;this.error='';
      try{
        const d=await this.api('/login',{method:'POST',body:JSON.stringify(this.loginForm)});
        try{localStorage.removeItem('aq_logout_pending')}catch{}
        this.token=true;this.user=d.user;this.authReady=true;
        const settleOffline=async()=>{
          try{await Promise.race([this.bindOfflineUser(d.user),new Promise(resolve=>setTimeout(resolve,900))])}catch{}
          try{if(window.AquaOffline)await Promise.race([AquaOffline.cachePut('/api/session',{authenticated:true,user:d.user,expires_at:d.expires_at}),new Promise(resolve=>setTimeout(resolve,900))])}catch{}
        };
        settleOffline();
        await this.refreshAll();
        if(this.refreshCommerce)this.refreshCommerce().catch(()=>{});
      }catch(e){
        this.token=false;this.user=null;
        this.error=e.status===429?'تلاش‌های ورود بیش از حد است؛ کمی بعد دوباره امتحان کن':e.status===401?'نام کاربری یا رمز عبور نادرست است':!navigator.onLine||!e.status?'ارتباط با سرور برقرار نشد؛ اینترنت را بررسی کن':(e.message||'ورود انجام نشد');
      }finally{this.busy=false;this.authReady=true}
    };
    const old=s.init.bind(s);s.init=async function(){await old();if(this.token)[250,700].forEach(ms=>setTimeout(()=>this.enhanceCommerceEmptyStates(),ms))};
    return s
  };

  const patchReleaseCopy=()=>{
    document.title='AquaGold CRM v6.1';
    document.querySelectorAll('main.login-bg div').forEach(el=>{
      const t=(el.textContent||'').trim();
      if(t==='مشتری، سرویس، GPS و حساب‌وکتاب روزانه در یک پنل امن.')el.textContent='پنل ورودی اکوا گلد نوشته شده توسط peyman.sector';
      if(t==='نسخه v6 • طراحی‌شده برای استفاده سریع روی iPhone'||t==='نسخه v6.1 • طراحی‌شده برای استفاده سریع روی iPhone')el.textContent='نسخه v6.1';
    });
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{patchReleaseCopy();setTimeout(patchReleaseCopy,150);setTimeout(patchReleaseCopy,800)});
  else{patchReleaseCopy();setTimeout(patchReleaseCopy,150)}
  new MutationObserver(patchReleaseCopy).observe(document.documentElement,{childList:true,subtree:true});
})();