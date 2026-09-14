/* Final runtime wiring for requested AquaGold Preview fixes. */
(()=>{
 const previous=window.app;if(typeof previous!=='function')return;
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const fa=n=>Number(n).toLocaleString('fa-IR',{useGrouping:false});
 const persianParts=value=>{const d=value?new Date(value):new Date(),parts=new Intl.DateTimeFormat('en-US-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d),out={};for(const p of parts)if(['year','month','day','hour','minute'].includes(p.type))out[p.type]=Number(p.value);return out};
 const gFromJ=(jy,jm,jd)=>{const start=Date.UTC(Number(jy)+621,2,1,8);for(let i=0;i<400;i++){const d=new Date(start+i*86400000),p=persianParts(d);if(p.year===Number(jy)&&p.month===Number(jm)&&p.day===Number(jd))return{year:d.getUTCFullYear(),month:d.getUTCMonth()+1,day:d.getUTCDate()}}return null};
 const pad=n=>String(Number(n)||0).padStart(2,'0');
 const months=['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
 window.app=function(){
  const s=previous(),baseSubmit=s.submitAquaText?.bind(s),baseRun=s.runAquaAction?.bind(s),baseOpen=s.openExpenseEdit?.bind(s),baseSave=s.saveExpenseEdit?.bind(s),baseInit=s.init?.bind(s);
  s.expenseJalali=s.expenseJalali||{year:'',month:'',day:'',hour:'',minute:''};
  s.daysInJalaliMonth=function(y,m){if(Number(m)<=6)return 31;if(Number(m)<=11)return 30;return gFromJ(Number(y),12,30)?30:29};
  s.syncExpenseJalaliToTimestamp=function(){const p=this.expenseJalali,g=gFromJ(p.year,p.month,p.day);if(!g||!this.expenseEdit)return false;this.expenseEdit.expense_date=`${g.year}-${pad(g.month)}-${pad(g.day)}T${pad(p.hour)}:${pad(p.minute)}:00+03:30`;return true};
  s.ensureExpenseJalaliPicker=function(){
   const legacy=[...document.querySelectorAll('label')].find(x=>x.textContent?.includes('تاریخ و ساعت هزینه'));if(!legacy)return;
   legacy.style.display='none';let host=document.getElementById('expenseJalaliPicker');if(!host){host=document.createElement('div');host.id='expenseJalaliPicker';host.className='glass rounded-2xl p-3';legacy.insertAdjacentElement('afterend',host)}
   const p=this.expenseJalali;if(!p.year){Object.assign(p,persianParts(this.expenseEdit?.expense_date||new Date()))}host.replaceChildren();
   const title=document.createElement('div');title.className='text-sm muted mb-2';title.textContent='تاریخ شمسی هزینه';host.appendChild(title);
   const grid=document.createElement('div');grid.className='aq-jalali-grid';host.appendChild(grid);
   const make=(parent,label,items,current,key)=>{const wrap=document.createElement('label');wrap.className='text-xs muted';wrap.append(document.createTextNode(label));const select=document.createElement('select');select.className='field mt-1 min-h-11';for(const item of items){const o=document.createElement('option');o.value=String(item.value);o.textContent=item.label;o.selected=String(item.value)===String(current);select.appendChild(o)}select.onchange=()=>{p[key]=Number(select.value);if(key==='year'||key==='month'){p.day=Math.min(Number(p.day),this.daysInJalaliMonth(p.year,p.month));this.ensureExpenseJalaliPicker()}this.syncExpenseJalaliToTimestamp()};wrap.appendChild(select);parent.appendChild(wrap)};
   const years=[];for(let y=Number(p.year)-3;y<=Number(p.year)+3;y++)years.push({value:y,label:fa(y)});make(grid,'سال',years,p.year,'year');make(grid,'ماه',months.map((x,i)=>({value:i+1,label:x})),p.month,'month');make(grid,'روز',Array.from({length:this.daysInJalaliMonth(p.year,p.month)},(_,i)=>({value:i+1,label:fa(i+1)})),p.day,'day');
   const time=document.createElement('div');time.className='aq-jalali-time';host.appendChild(time);make(time,'ساعت',Array.from({length:24},(_,i)=>({value:i,label:fa(String(i).padStart(2,'0'))})),p.hour,'hour');make(time,'دقیقه',Array.from({length:60},(_,i)=>({value:i,label:fa(String(i).padStart(2,'0'))})),p.minute,'minute');this.syncExpenseJalaliToTimestamp();
  };
  s.openExpenseEdit=function(expense){const out=baseOpen?.(expense),p=persianParts(expense?.expense_date||new Date());this.expenseJalali={year:p.year,month:p.month,day:p.day,hour:p.hour||0,minute:p.minute||0};setTimeout(()=>this.ensureExpenseJalaliPicker(),0);return out};
  s.saveExpenseEdit=async function(...args){if(!this.syncExpenseJalaliToTimestamp())return alert('تاریخ شمسی معتبر نیست');return baseSave?.(...args)};
  s.mountRouteControlsBelowMap=function(){const controls=document.getElementById('aqst-controls'),frame=document.querySelector('.aq-map-frame'),details=document.getElementById('aqst-tour-details');if(!controls||!frame)return;const target=details||frame.nextElementSibling;if(controls.parentElement===frame||!controls.classList.contains('aqst-controls-outside')){controls.classList.add('aqst-controls-outside');if(target?.parentNode)target.parentNode.insertBefore(controls,target);else frame.insertAdjacentElement('afterend',controls)}};
  s.showAriaAddress=function(location){if(!location||!Number.isFinite(Number(location.latitude))||!Number.isFinite(Number(location.longitude)))return false;this.ariaLocation={...location};this.page='map';setTimeout(()=>{try{this.renderMainMap?.();const m=this.mainMap;if(!m||!window.L)return;if(this.ariaSearchMarker)try{this.ariaSearchMarker.remove()}catch{}const icon=L.divIcon({className:'aq-aria-marker',html:'<span aria-hidden="true">◆</span>',iconSize:[38,42],iconAnchor:[19,38]});this.ariaSearchMarker=L.marker([Number(location.latitude),Number(location.longitude)],{icon}).addTo(m).bindPopup(`<div dir="rtl"><b>${this.escapeHtml?.(location.title||location.name||'نتیجه آدرس')||'نتیجه آدرس'}</b><br>${this.escapeHtml?.(location.formatted_address||location.address||'')||''}</div>`).openPopup();m.setView([Number(location.latitude),Number(location.longitude)],17);m.invalidateSize?.()}catch(e){console.warn('aria map render failed',e)}},260);return true};
  s.runAquaAction=function(action){if(action?.type==='show_address_on_map')return this.showAriaAddress(action.location);if(action?.customer?.kind==='address')return this.showAriaAddress(action.customer);return baseRun?.(action)};
  s.submitAquaText=async function(value,source='text',voiceRunId=0){
   const before=this.aquaMessages?.length||0,result=await baseSubmit?.(value,source,voiceRunId);
   const messages=(this.aquaMessages||[]).slice(before);const msg=[...messages].reverse().find(x=>x?.role==='assistant');
   if(msg?.action)this.runAquaAction?.(msg.action);
   if(!msg?.action&&Array.isArray(msg?.results)&&msg.results.length===1)this.showAriaAddress?.(msg.results[0]);
   return result;
  };
  s.init=async function(){await baseInit?.();for(let i=0;i<8;i++){this.mountRouteControlsBelowMap();await sleep(180)}const obs=new MutationObserver(()=>this.mountRouteControlsBelowMap());const section=document.getElementById('mainMap')?.closest('section');if(section)obs.observe(section,{childList:true,subtree:true})};
  return s;
 };
})();
