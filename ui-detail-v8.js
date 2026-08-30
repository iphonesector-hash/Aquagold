/* AquaGold v8 detail polish: coherent dashboard palette, Persian date contract and money formatting. */
(()=>{
 const previous=window.app;
 if(typeof previous!=='function')return;
 const persianDigits=s=>String(s??'').replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[Number(d)]);
 const monthName=m=>({1:'فروردین',2:'اردیبهشت',3:'خرداد',4:'تیر',5:'مرداد',6:'شهریور',7:'مهر',8:'آبان',9:'آذر',10:'دی',11:'بهمن',12:'اسفند'})[Number(m)]||'';
 const weekdayName=d=>new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',weekday:'long'}).format(d);
 const jalaliParts=d=>{let p={};new Intl.DateTimeFormat('en-US-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(d).forEach(x=>{if(['year','month','day'].includes(x.type))p[x.type]=Number(x.value)});return p};
 const prettyDate=value=>{if(!value)return'';let d=value instanceof Date?value:(/^\d{4}-\d{2}-\d{2}$/.test(String(value))?new Date(String(value)+'T12:00:00+03:30'):new Date(value));if(Number.isNaN(d.getTime()))return String(value);let p=jalaliParts(d);return `${weekdayName(d)} / ${persianDigits(String(p.day).padStart(2,'0'))} / ${monthName(p.month)} / ${persianDigits(p.year)}`};
 const prettyMoney=value=>{let n=Number(String(value??0).replace(/[٬،,\s]/g,''));if(!Number.isFinite(n))n=0;return new Intl.NumberFormat('fa-IR',{maximumFractionDigits:0}).format(Math.round(n)).replace(/٬/g,'،')};
 const style=document.createElement('style');
 style.id='ops-v8-detail-style';
 style.textContent=`
 .ops-clock{direction:rtl;text-align:right}.ops-clock strong{display:block;white-space:pre-line;direction:rtl;unicode-bidi:plaintext;text-align:right;line-height:1.7}
 .ops-today{border-color:rgba(73,183,255,.32)!important;background:radial-gradient(circle at 15% 0,rgba(35,167,255,.16),transparent 40%),linear-gradient(150deg,rgba(8,42,82,.97),rgba(3,20,45,.98))!important}
 .ops-today .btn{color:#fff!important;background:linear-gradient(135deg,#075fbd,#078edc 54%,#18b8e8)!important;border:1px solid rgba(121,218,255,.32)!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.18),0 10px 24px rgba(0,109,201,.24)!important;transition:transform .14s ease,filter .14s ease,box-shadow .18s ease!important}
 .ops-today .btn:hover{filter:brightness(1.08)}
 .aqua-action[data-tone]{background:radial-gradient(circle at 50% 10%,rgba(41,175,255,.21),transparent 48%),linear-gradient(160deg,rgba(8,54,103,.97),rgba(3,24,52,.99))!important;border-color:rgba(93,196,255,.29)!important;transition:transform .14s ease,filter .14s ease,box-shadow .18s ease!important}
 .aqua-action[data-tone] .aqua-action-orb{color:#7be8ff!important;background:radial-gradient(circle at 35% 25%,rgba(103,229,255,.34),rgba(8,111,189,.56) 45%,rgba(3,30,63,.96) 78%)!important;border-color:rgba(115,219,255,.34)!important}
 .aqua-action[data-tone] .aqua-action-chevron{color:#70dfff!important}
 `;
 if(!document.getElementById(style.id))document.head.appendChild(style);
 window.app=function(){
  const s=previous();
  s.money=prettyMoney;
  s.moneyToman=value=>`${prettyMoney(value)} تومان`;
  s.persianDate=prettyDate;
  s.formatDashboardDate=prettyDate;
  s.updateTehranClock=function(){try{let now=new Date(),time=new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now);this.tehranNow=`${prettyDate(now)}\n${time}`}catch{this.tehranNow=''}};
  if(Array.isArray(s.quickActions))s.quickActions=s.quickActions.map(x=>({...x,tone:'blue'}));
  const oldPolish=s.applyDashboardPolish?.bind(s);
  s.applyDashboardPolish=function(){oldPolish?.();let dash=[...document.querySelectorAll('section')].find(x=>(x.getAttribute('x-show')||'').includes("page==='dashboard'"));if(!dash)return;dash.querySelectorAll('button,a,[role="button"]').forEach(el=>{el.dataset.opsTone='blue'});let today=dash.querySelector('.ops-today');if(today){let title=today.querySelector('b');if(title)title.textContent='کارهای روزانه';today.querySelectorAll('button').forEach(b=>{b.classList.remove('primary','soft');b.classList.add('ops-daily-blue')})}this.normalizeMoneyLabels?.()};
  s.normalizeMoneyLabels=function(root=document.querySelector('main.content')){if(!root)return;let walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);for(let node of nodes){let p=node.parentElement;if(!p||['SCRIPT','STYLE','TEXTAREA','INPUT','OPTION'].includes(p.tagName))continue;let t=node.nodeValue||'',n=t.replace(/([۰-۹])٬(?=[۰-۹]{3}(?:\D|$))/g,'$1،').replace(/([۰-۹]+(?:[،][۰-۹]{3})*)\s+ت(?=\s|$|•|،)/g,'$1 تومان');if(n!==t)node.nodeValue=n}};
  const oldGo=s.go;if(oldGo)s.go=async function(page){let r=await oldGo.call(this,page);setTimeout(()=>this.normalizeMoneyLabels(),30);return r};
  const oldRefresh=s.refreshAll?.bind(s);if(oldRefresh)s.refreshAll=async function(...a){let r=await oldRefresh(...a);setTimeout(()=>this.normalizeMoneyLabels(),30);return r};
  const oldInit=s.init?.bind(s);if(oldInit)s.init=async function(...a){let r=await oldInit(...a);this.updateTehranClock?.();setTimeout(()=>{this.applyDashboardPolish?.();this.normalizeMoneyLabels?.()},80);return r};
  return s;
 };
})();
