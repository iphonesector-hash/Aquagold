(()=>{
const previous=window.app;
if(typeof previous!=='function')return;
window.app=function(){
 const s=previous();
 const oldMount=s.mountEnhancements?.bind(s);
 s.mountEnhancements=function(){oldMount?.();
  let detail=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='customer-detail'"));
  if(detail&&!detail.querySelector('.aq-quality-card')){let q=document.createElement('div');q.className='card p-5 aq-quality-card';q.innerHTML=`<div class="flex justify-between items-center"><div><h3 class="font-black">کیفیت اطلاعات مشتری</h3><p class="text-xs text-slate-500">شماره، آدرس، GPS، دستگاه و جزئیات ثبت‌شده</p></div><b class="text-2xl" :class="profileTone(profileScore(selectedCustomer||{}))" x-text="profileScore(selectedCustomer||{})+'٪'"></b></div><div class="h-2 rounded-full bg-slate-100 overflow-hidden mt-3"><div class="h-full bg-teal-500 transition-all" :style="'width:'+profileScore(selectedCustomer||{})+'%'"></div></div>`;detail.insertBefore(q,detail.children[1]||null);if(window.Alpine)Alpine.initTree(q)}
  let h=document.querySelector('header');if(h&&!h.querySelector('.aq-network')){let n=document.createElement('span');n.className='aq-network hidden sm:inline-flex chip';n.setAttribute(':class',"online?'bg-emerald-50 text-emerald-700':'bg-red-50 text-red-600'");n.setAttribute('x-text',"online?'● آنلاین':'● آفلاین'");let row=h.querySelector('.flex.gap-2.items-center');row?.prepend(n);if(window.Alpine)Alpine.initTree(n)}
 };
 const oldInit=s.init.bind(s);
 s.init=async function(){await oldInit();let open=new URLSearchParams(location.search).get('open');if(open&&['smart','customers','map','finance','daily','expense','reminders'].includes(open)){setTimeout(()=>this.go(open),120)}};
 return s;
};
})();
