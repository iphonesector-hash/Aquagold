(()=>{
const previous=window.app;
if(typeof previous!=='function')return;

const patchLoginCopy=()=>{
 try{
  document.title='AquaGold CRM v6.2';
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  let node;
  while((node=walker.nextNode())){
   const value=(node.nodeValue||'').trim();
   if(value==='مشتری، سرویس، GPS و حساب‌وکتاب روزانه در یک پنل امن.')node.nodeValue=node.nodeValue.replace(value,'پنل ورودی اکوا گلد نوشته شده توسط peyman.sector');
   if(value==='نسخه v6 • طراحی‌شده برای استفاده سریع روی iPhone')node.nodeValue=node.nodeValue.replace(value,'نسخه v6.2');
   if(value==='نسخه v6.1')node.nodeValue=node.nodeValue.replace(value,'نسخه v6.2');
  }
 }catch{}
};

window.app=function(){
 const s=previous();
 patchLoginCopy();

 const oldMount=s.mountEnhancements?.bind(s);
 s.mountEnhancements=function(){
  oldMount?.();
  patchLoginCopy();
  let detail=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='customer-detail'"));
  if(detail&&!detail.querySelector('.aq-quality-card')){
   let q=document.createElement('div');q.className='card p-5 aq-quality-card';
   q.innerHTML=`<div class="flex justify-between items-center"><div><h3 class="font-black">کیفیت اطلاعات مشتری</h3><p class="text-xs text-slate-500">شماره، آدرس، GPS، دستگاه و جزئیات ثبت‌شده</p></div><b class="text-2xl" :class="profileTone(profileScore(selectedCustomer||{}))" x-text="profileScore(selectedCustomer||{})+'٪'"></b></div><div class="h-2 rounded-full bg-slate-100 overflow-hidden mt-3"><div class="h-full bg-teal-500 transition-all" :style="'width:'+profileScore(selectedCustomer||{})+'%'"></div></div>`;
   detail.insertBefore(q,detail.children[1]||null);if(window.Alpine)Alpine.initTree(q);
  }
  let h=document.querySelector('header');
  if(h&&!h.querySelector('.aq-network')){
   let n=document.createElement('span');n.className='aq-network hidden sm:inline-flex chip';
   n.setAttribute(':class',"online?'bg-emerald-50 text-emerald-700':'bg-red-50 text-red-600'");
   n.setAttribute('x-text',"online?'● آنلاین':'● آفلاین'");
   h.querySelector('.flex.gap-2.items-center')?.prepend(n);if(window.Alpine)Alpine.initTree(n);
  }
 };

 s.init=async function(){
  this.authReady=false;this.token=false;this.user=null;this.error='';
  patchLoginCopy();
  window.addEventListener('online',()=>{this.online=true});
  window.addEventListener('offline',()=>{this.online=false});
  try{
   const r=await fetch('/api/session',{method:'GET',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
   if(r.ok){
    const d=await r.json();
    if(d?.user){
     this.user=d.user;this.token=true;this.page='dashboard';
     this.authReady=true;
     queueMicrotask(()=>{this.refreshAll?.().catch(e=>console.warn('AquaGold initial refresh',e));});
     setTimeout(()=>{this.mountEnhancements?.();this.mountCommerce?.();},80);
     setTimeout(()=>{this.mountEnhancements?.();this.mountCommerce?.();},300);
     const open=new URLSearchParams(location.search).get('open');
     if(open&&['smart','customers','map','finance','daily','expense','reminders','products','invoices'].includes(open))setTimeout(()=>this.go(open),180);
     return;
    }
   }
  }catch(e){console.warn('AquaGold session bootstrap',e)}
  this.token=false;this.user=null;this.authReady=true;
  patchLoginCopy();
 };

 s.login=async function(){
  if(this.busy)return;
  this.busy=true;this.error='';
  try{
   const response=await fetch('/api/login',{
    method:'POST',credentials:'same-origin',cache:'no-store',
    headers:{'Content-Type':'application/json','Accept':'application/json'},
    body:JSON.stringify(this.loginForm)
   });
   let data={};try{data=await response.json()}catch{}
   if(!response.ok){
    const e=new Error(data.error||'ورود انجام نشد');e.status=response.status;throw e;
   }
   try{localStorage.removeItem('aq_logout_pending')}catch{}
   const verify=await fetch('/api/session',{method:'GET',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
   let session={};try{session=await verify.json()}catch{}
   if(!verify.ok||!session?.user)throw Object.assign(new Error('سشن ورود در مرورگر تأیید نشد'),{status:verify.status||0});
   this.user=session.user;this.token=true;this.page='dashboard';this.authReady=true;
   try{sessionStorage.setItem('aq_login_ok','1')}catch{}
   const clean=location.pathname+(location.search&&location.search!=='?'?location.search:'');
   location.replace(clean||'/');
  }catch(e){
   this.token=false;this.user=null;this.authReady=true;
   this.error=e.status===429?'تلاش‌های ورود بیش از حد است؛ کمی بعد دوباره امتحان کن':e.status===401?'نام کاربری یا رمز عبور نادرست است':e.status===403?'مرورگر اجازه ساخت نشست ورود را نداد':(!navigator.onLine||!e.status)?'ارتباط با سرور برای ورود برقرار نشد':(e.message||'ورود انجام نشد');
   patchLoginCopy();
  }finally{this.busy=false}
 };

 return s;
};
})();
