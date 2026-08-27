(()=>{
const previous=window.app;
if(typeof previous!=='function')return;
window.app=function(){
 const s=previous();
 const oldMount=s.mountEnhancements?.bind(s);
 s.mountEnhancements=function(){
  try{oldMount?.()}catch(e){console.error('enhancements',e)}
  let detail=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='customer-detail'"));
  if(detail&&!detail.querySelector('.aq-quality-card')){
   let q=document.createElement('div');q.className='card p-5 aq-quality-card';
   q.innerHTML=`<div class="flex justify-between items-center"><div><h3 class="font-black">کیفیت اطلاعات مشتری</h3><p class="text-xs text-slate-500">شماره، آدرس، GPS، دستگاه و جزئیات ثبت‌شده</p></div><b class="text-2xl" :class="profileTone(profileScore(selectedCustomer||{}))" x-text="profileScore(selectedCustomer||{})+'٪'"></b></div><div class="h-2 rounded-full bg-slate-100 overflow-hidden mt-3"><div class="h-full bg-teal-500 transition-all" :style="'width:'+profileScore(selectedCustomer||{})+'%'\"></div></div>`;
   detail.insertBefore(q,detail.children[1]||null);if(window.Alpine)Alpine.initTree(q);
  }
 };

 // Canonical navigation kernel. Page changes are immediate; data refreshes never block taps.
 s.go=function(p){
  const page=String(p||'dashboard');
  this.page=page;
  try{window.scrollTo({top:0,left:0,behavior:'auto'})}catch{window.scrollTo(0,0)}
  const core=['dashboard','daily','customers','services','expense','finance','insights','reminders','settings'];
  if(core.includes(page))Promise.resolve(this.refreshAll?.()).catch(e=>console.warn('AquaGold refresh',e));
  if(page==='map')setTimeout(()=>{try{this.renderMainMap?.()}catch(e){console.warn('map render',e)}},60);
  if(page==='finance')setTimeout(()=>{try{this.renderCharts?.()}catch(e){console.warn('chart render',e)}},80);
  if(page==='aqua-ai'){
   try{this.mountAquaAI?.();this.aquaScroll?.();this.loadAquaSettings?.().catch?.(()=>{})}catch(e){console.warn('aqua-ai nav',e)}
  }
  if(page==='bale-jobs'){
   try{this.baleMount?.();Promise.all([this.loadBaleJobs?.(this.baleTab||'new'),this.loadBaleCounts?.()]).catch(e=>console.warn('bale nav',e))}catch(e){console.warn('bale nav',e)}
  }
  if(['products','product-edit','invoices','invoice-new','invoice-view'].includes(page))Promise.resolve(this.refreshCommerce?.()).catch(e=>console.warn('commerce nav',e));
  return Promise.resolve();
 };

 s.init=async function(){
  this.authReady=false;this.token=false;this.user=null;this.error='';
  window.addEventListener('online',()=>{this.online=true});
  window.addEventListener('offline',()=>{this.online=false});
  try{
   const r=await fetch('/api/session',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
   if(r.ok){const d=await r.json();if(d?.user){
    this.user=d.user;this.token=true;this.page='dashboard';this.authReady=true;
    requestAnimationFrame(()=>{try{this.mountEnhancements?.()}catch(e){console.error('enhancements',e)};try{this.mountCommerce?.()}catch(e){console.error('commerce',e)};try{this.mountAquaAI?.()}catch(e){console.error('aqua-ai',e)};try{this.baleMount?.()}catch(e){console.error('bale',e)};});
    setTimeout(()=>{this.refreshAll?.().catch(e=>console.warn('AquaGold refresh',e));try{this.mountEnhancements?.()}catch(e){console.error('enhancements',e)};try{this.mountCommerce?.()}catch(e){console.error('commerce',e)};try{this.mountAquaAI?.()}catch(e){console.error('aqua-ai',e)};try{this.baleMount?.()}catch(e){console.error('bale',e)};},80);
    return;
   }}
  }catch(e){console.warn('AquaGold session bootstrap',e)}
  this.authReady=true;
 };
 s.login=async function(){
  if(this.busy)return;this.busy=true;this.error='';
  try{
   const r=await fetch('/api/login',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify(this.loginForm)});
   let d={};try{d=await r.json()}catch{}
   if(!r.ok){let e=Error(d.error||'ورود انجام نشد');e.status=r.status;throw e}
   const verify=await fetch('/api/session',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
   let session={};try{session=await verify.json()}catch{}
   if(!verify.ok||!session?.user){let e=Error('سشن ورود تأیید نشد');e.status=verify.status||0;throw e}
   try{localStorage.removeItem('aq_logout_pending')}catch{}
   this.user=session.user;this.token=true;this.authReady=true;this.page='dashboard';this.error='';
   await this.$nextTick?.();
   requestAnimationFrame(()=>{window.scrollTo(0,0);try{this.mountEnhancements?.()}catch(e){console.error('enhancements',e)};try{this.mountCommerce?.()}catch(e){console.error('commerce',e)};try{this.mountAquaAI?.()}catch(e){console.error('aqua-ai',e)};try{this.baleMount?.()}catch(e){console.error('bale',e)};});
   setTimeout(()=>{this.refreshAll?.().catch(e=>console.warn('AquaGold refresh',e));try{this.mountEnhancements?.()}catch(e){console.error('enhancements',e)};try{this.mountCommerce?.()}catch(e){console.error('commerce',e)};try{this.mountAquaAI?.()}catch(e){console.error('aqua-ai',e)};try{this.baleMount?.()}catch(e){console.error('bale',e)};},60);
  }catch(e){
   this.token=false;this.user=null;this.authReady=true;
   this.error=e.status===429?'تلاش‌های ورود بیش از حد است؛ کمی بعد دوباره امتحان کن':e.status===401?'نام کاربری یا رمز عبور نادرست است':e.status===403?'مرورگر اجازه ساخت نشست ورود را نداد':(!navigator.onLine||!e.status)?'ارتباط با سرور برای ورود برقرار نشد':(e.message||'ورود انجام نشد');
  }finally{this.busy=false}
 };
 return s;
};
})();
