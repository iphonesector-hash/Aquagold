(()=>{
const previous=window.app;
if(typeof previous!=='function')return;
window.app=function(){
 const s=previous();
 const oldMount=s.mountEnhancements?.bind(s);
 const patchLoginCopy=()=>{
  try{
   document.title='AquaGold CRM v6.1';
   const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
   let node;
   while((node=walker.nextNode())){
    const value=(node.nodeValue||'').trim();
    if(value==='مشتری، سرویس، GPS و حساب‌وکتاب روزانه در یک پنل امن.')node.nodeValue=node.nodeValue.replace('مشتری، سرویس، GPS و حساب‌وکتاب روزانه در یک پنل امن.','پنل ورودی اکوا گلد نوشته شده توسط peyman.sector');
    if(value==='نسخه v6 • طراحی‌شده برای استفاده سریع روی iPhone')node.nodeValue=node.nodeValue.replace('نسخه v6 • طراحی‌شده برای استفاده سریع روی iPhone','نسخه v6.1');
   }
  }catch{}
 };
 s.mountEnhancements=function(){oldMount?.();
  patchLoginCopy();
  let detail=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='customer-detail'"));
  if(detail&&!detail.querySelector('.aq-quality-card')){let q=document.createElement('div');q.className='card p-5 aq-quality-card';q.innerHTML=`<div class="flex justify-between items-center"><div><h3 class="font-black">کیفیت اطلاعات مشتری</h3><p class="text-xs text-slate-500">شماره، آدرس، GPS، دستگاه و جزئیات ثبت‌شده</p></div><b class="text-2xl" :class="profileTone(profileScore(selectedCustomer||{}))" x-text="profileScore(selectedCustomer||{})+'٪'"></b></div><div class="h-2 rounded-full bg-slate-100 overflow-hidden mt-3"><div class="h-full bg-teal-500 transition-all" :style="'width:'+profileScore(selectedCustomer||{})+'%'"></div></div>`;detail.insertBefore(q,detail.children[1]||null);if(window.Alpine)Alpine.initTree(q)}
  let h=document.querySelector('header');if(h&&!h.querySelector('.aq-network')){let n=document.createElement('span');n.className='aq-network hidden sm:inline-flex chip';n.setAttribute(':class',"online?'bg-emerald-50 text-emerald-700':'bg-red-50 text-red-600'");n.setAttribute('x-text',"online?'● آنلاین':'● آفلاین'");let row=h.querySelector('.flex.gap-2.items-center');row?.prepend(n);if(window.Alpine)Alpine.initTree(n)}
 };
 const oldInit=s.init.bind(s);
 s.init=async function(){await oldInit();patchLoginCopy();setTimeout(patchLoginCopy,50);setTimeout(patchLoginCopy,500);let open=new URLSearchParams(location.search).get('open');if(open&&['smart','customers','map','finance','daily','expense','reminders'].includes(open)){setTimeout(()=>this.go(open),120)}};
 s.login=async function(){
  this.busy=true;this.error='';
  try{
   const d=await this.api('/login',{method:'POST',body:JSON.stringify(this.loginForm)});
   try{localStorage.removeItem('aq_logout_pending')}catch{}
   this.token=true;this.user=d.user;this.authReady=true;
   const timeout=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));
   Promise.race([(async()=>{try{await this.bindOfflineUser(d.user)}catch{}try{if(window.AquaOffline)await AquaOffline.cachePut('/api/session',{authenticated:true,user:d.user,expires_at:d.expires_at})}catch{}})(),timeout(900)]).catch(()=>{});
   Promise.race([this.refreshAll(),timeout(2200)]).catch(error=>console.warn('AquaGold post-login refresh fallback',error));
  }catch(e){
   this.token=false;this.user=null;
   this.error=e.status===429?'تلاش‌های ورود بیش از حد است؛ کمی بعد دوباره امتحان کن':e.status===401?'نام کاربری یا رمز عبور نادرست است':(!navigator.onLine||!e.status)?'برای ورود اولیه اتصال اینترنت لازم است':(e.message||'ورود انجام نشد');
  }finally{this.busy=false;this.authReady=true;patchLoginCopy()}
 };
 if(typeof MutationObserver!=='undefined')new MutationObserver(patchLoginCopy).observe(document.documentElement,{childList:true,subtree:true});
 return s;
};
})();
