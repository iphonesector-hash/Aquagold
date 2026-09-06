(()=>{'use strict';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const state={view:'today',date:'',period:'daily',sound:localStorage.getItem('aquaMiniSound')!=='0',audio:null,audioUnlocked:false,searchTimer:null,loginBusy:false};
const fmtMoney=new Intl.NumberFormat('fa-IR');
const icon=(name,cls='')=>`<svg class="ui-icon ${cls}"><use href="/assets/aqua-icons.svg#${name}"></use></svg>`;
function escapeHtml(v){return String(v??'').replace(/[&<>'"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[m]))}
function toast(msg,kind=''){const el=$('#toast');el.textContent=msg;el.className=`toast show ${kind}`;clearTimeout(el._t);el._t=setTimeout(()=>el.className='toast',2600)}
function fa(v){return new Intl.NumberFormat('fa-IR').format(Number(v||0))}
function money(v){return `${fmtMoney.format(Number(v||0))} تومان`}
function todayISO(){const p=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const o=Object.fromEntries(p.map(x=>[x.type,x.value]));return `${o.year}-${o.month}-${o.day}`}
function shiftDate(iso,n){const d=new Date(`${iso}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)}
function pDate(iso,long=true){const d=new Date(`${iso}T12:00:00Z`);return new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',weekday:long?'long':undefined,year:'numeric',month:long?'long':'numeric',day:'numeric'}).format(d)}
function pDateTime(iso){if(!iso)return '—';return new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(iso))}
function clock(iso){if(!iso)return '—';return new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit'}).format(new Date(iso))}
function errorText(value,status=0){
  if(value instanceof Error&&value.message)return errorText(value.message,status);
  if(typeof value==='string'&&value.trim()&&value.trim()!=='[object Object]')return value.trim();
  if(Array.isArray(value)){const parts=value.map(x=>errorText(x,0)).filter(Boolean);if(parts.length)return parts.join('، ')}
  if(value&&typeof value==='object'){
    for(const key of ['error','message','detail','description','reason']){if(value[key]){const text=errorText(value[key],0);if(text)return text}}
  }
  const statusMessages={400:'اطلاعات ارسال‌شده معتبر نیست. موارد واردشده را بررسی کن.',401:'نام کاربری یا رمز عبور اشتباه است.',403:'اجازه دسترسی به این بخش را نداری.',404:'بخش درخواستی پیدا نشد.',409:'این درخواست با وضعیت فعلی قابل انجام نیست.',429:'تعداد تلاش‌ها زیاد شده؛ کمی صبر کن و دوباره امتحان کن.',500:'خطای داخلی سرور رخ داد. دوباره تلاش کن.',502:'سرور موقتاً پاسخ نمی‌دهد. چند لحظه دیگر دوباره امتحان کن.',503:'سرویس موقتاً در دسترس نیست. چند لحظه دیگر دوباره امتحان کن.',504:'پاسخ سرور طول کشید. دوباره تلاش کن.'};
  return statusMessages[status]||'خطایی در ارتباط با سرور رخ داد. دوباره تلاش کن.'
}
async function api(path,opts={}){
  let r;
  try{r=await fetch(path,{credentials:'include',headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts})}
  catch{throw new Error(navigator.onLine?'ارتباط با سرور برقرار نشد. دوباره تلاش کن.':'اینترنت دستگاه قطع است. اتصال اینترنت را بررسی کن.')}
  let data={};try{data=await r.json()}catch{}
  if(!r.ok){if(r.status===401&&path!='/api/mini/login')showLogin();throw new Error(errorText(data?.error??data?.message??data,r.status))}
  return data
}

async function ensureAudio(){
  if(!state.sound)return null;
  try{
    const C=window.AudioContext||window.webkitAudioContext;if(!C)return null;
    if(!state.audio||state.audio.state==='closed')state.audio=new C();
    if(state.audio.state==='suspended')await state.audio.resume();
    if(!state.audioUnlocked){
      const ctx=state.audio,b=ctx.createBuffer(1,1,22050),src=ctx.createBufferSource(),g=ctx.createGain();g.gain.value=.00001;src.buffer=b;src.connect(g).connect(ctx.destination);src.start(0);state.audioUnlocked=true;
    }
    return state.audio;
  }catch{return null}
}
async function beep(kind='tap'){
  if(!state.sound)return;
  const ctx=await ensureAudio();if(!ctx)return;
  try{
    const map={tap:[530,.035,.035],nav:[690,.055,.045],open:[790,.075,.05],success:[920,.13,.07],error:[210,.15,.06]};
    const [hz,dur,vol]=map[kind]||map.tap,now=ctx.currentTime,o=ctx.createOscillator(),g=ctx.createGain();
    o.type=kind==='error'?'triangle':'sine';o.frequency.setValueAtTime(hz,now);if(kind==='success')o.frequency.exponentialRampToValueAtTime(1380,now+dur);
    g.gain.setValueAtTime(.0001,now);g.gain.exponentialRampToValueAtTime(vol,now+.008);g.gain.exponentialRampToValueAtTime(.0001,now+dur);o.connect(g).connect(ctx.destination);o.start(now);o.stop(now+dur+.02);
  }catch{}
}
function haptic(){try{navigator.vibrate?.(9)}catch{}}
function interactive(kind='tap'){void beep(kind);haptic()}
async function unlockFromGesture(){if(state.sound)await ensureAudio()}
function updateSoundUI(){const b=$('#soundBtn');if(!b)return;b.classList.toggle('muted',!state.sound);b.classList.toggle('audio-ready',state.sound&&state.audioUnlocked);const dot=b.querySelector('.sound-state');if(dot)dot.title=state.sound?'روشن':'خاموش'}
async function setSound(){state.sound=!state.sound;localStorage.setItem('aquaMiniSound',state.sound?'1':'0');if(state.sound){await ensureAudio();await beep('success')}else if(state.audio?.state==='running'){try{await state.audio.suspend()}catch{}}updateSoundUI();haptic();toast(state.sound?'افکت صوتی روشن شد':'افکت صوتی خاموش شد')}

function showLogin(){$('#root').classList.add('hidden');$('#login').classList.remove('hidden');setTimeout(()=>$('#password')?.focus(),120)}
function showApp(){$('#login').classList.add('hidden');$('#root').classList.remove('hidden');navigate('today',false)}
function hideSplash(){const s=$('#splash');s.classList.add('out');setTimeout(()=>s.classList.add('hidden'),520)}
function setLoginBusy(busy){
  state.loginBusy=busy;const btn=$('#loginForm button[type="submit"]');if(!btn)return;btn.disabled=busy;const label=btn.querySelector('span');if(label)label.textContent=busy?'در حال بررسی...':'ورود به مینی‌اپ'
}

function statusTimeline(job){
  const st=job.status;
  const waitClass=st==='new'?'active':st!=='new'?'done':'';
  const regClass=st==='review'?'active':(['completed','cancelled'].includes(st)?'done':'');
  const finalClass=st==='completed'?'done active':st==='cancelled'?'cancel active':'';
  const seg1=st==='new'?'flow':'filled',seg2=st==='review'?'flow':(['completed','cancelled'].includes(st)?'filled':'');
  const finalLabel=st==='cancelled'?'کنسل شده':'انجام شده';
  return `<div class="timeline"><div class="stage ${waitClass}"><div class="stage-dot"></div><div class="stage-label">در صف انتظار</div></div><div class="segment ${seg1}"></div><div class="stage ${regClass}"><div class="stage-dot"></div><div class="stage-label">ثبت شده</div></div><div class="segment ${seg2}"></div><div class="stage ${finalClass}"><div class="stage-dot"></div><div class="stage-label">${finalLabel}</div></div></div>`
}
function jobCard(j){
  const cls=j.status==='completed'?'completed':j.status==='cancelled'?'cancelled':'';
  const result=j.status==='completed'?`<div class="job-result money">${icon('i-finance')}<span>دریافتی: <b>${money(j.received_amount)}</b></span></div>`:j.status==='cancelled'?`<div class="job-result reason">${icon('i-reminders')}<span>علت کنسلی: <b>${escapeHtml(j.cancel_reason||'ثبت نشده')}</b></span></div>`:'';
  return `<article class="job-card ${cls}"><div class="card-shine"></div><div class="job-top"><div class="job-avatar">${icon('i-customers')}</div><div class="job-main"><div class="job-name">${escapeHtml(j.customer_name||'مشتری بدون نام')}</div><div class="job-type">${escapeHtml(j.job_type||'سرویس')}</div><div class="job-address">${icon('i-map')}${escapeHtml(j.address||j.phone||'بدون آدرس')}</div></div><div class="job-time">${clock(j.received_at)}</div></div>${statusTimeline(j)}${result}</article>`
}
async function loadDay(){
  const list=$('#jobsList');list.innerHTML='<div class="skeleton"></div><div class="skeleton"></div>';
  $('#dayTitle').textContent=state.date===todayISO()?'امروز':'گزارش روز';$('#dayDate').textContent=pDate(state.date,true);
  try{
    const d=await api(`/api/mini/day?date=${encodeURIComponent(state.date)}`);
    const emptyText=state.date===todayISO()?'اتصال به دیتابیس برقرار است؛ برای امروز هنوز سرویس نهایی یا کنسلی ثبت نشده. برای دیدن سوابق، «روز قبل» را بزن.':'برای این روز سرویس نهایی یا کنسلی ثبت نشده است.';
    list.innerHTML=d.jobs.length?d.jobs.map(jobCard).join(''):`<div class="empty">${emptyText}</div>`;
    const s=d.summary;
    $('#daySummary').innerHTML=`<div class="summary-card green">${icon('i-services')}<div><span>انجام شده</span><b>${fa(s.completed)}</b></div></div><div class="summary-card red">${icon('i-reminders')}<div><span>کنسل شده</span><b>${fa(s.cancelled)}</b></div></div><div class="summary-card cyan">${icon('i-finance')}<div><span>دریافتی</span><b>${money(s.received)}</b></div></div><div class="summary-card gold">${icon('i-insights')}<div><span>سهم شرکت</span><b>${money(s.company_share)}</b></div></div>`;
  }catch(e){list.innerHTML=`<div class="empty error">${escapeHtml(errorText(e))}</div>`;$('#daySummary').innerHTML=''}
}
function navigate(view,sound=true){
  state.view=view;$$('.view').forEach(v=>v.classList.add('hidden'));$(`#${view}View`)?.classList.remove('hidden');$$('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.view===view));if(sound)interactive('nav');if(view==='today')loadDay();if(view==='finance')loadFinance();if(view==='customers')setTimeout(()=>$('#customerSearch')?.focus(),120)
}

function customerCard(c){
  const phones=(c.phones||[]).join(' • ')||'بدون شماره',name=[c.first_name,c.last_name].filter(Boolean).join(' ')||'بدون نام';
  return `<article class="customer-card" data-customer="${c.id}"><div class="card-shine"></div><div class="customer-header"><div class="customer-avatar">${icon('i-customers')}</div><div class="customer-id"><div class="customer-name">${escapeHtml(name)}</div><small>${escapeHtml(phones)}</small></div><span class="badge">مشتری فعال</span></div><div class="customer-lines"><div>${icon('i-map')}<span>${escapeHtml(c.address||'آدرس ثبت نشده')}${c.plaque?`، پلاک ${escapeHtml(c.plaque)}`:''}${c.unit_no?`، واحد ${escapeHtml(c.unit_no)}`:''}</span></div><div>${icon('i-daily')}<span>اولین ثبت: ${pDateTime(c.created_at)}</span></div><div>${icon('i-services')}<span>آخرین سرویس: ${pDateTime(c.last_service_at)}</span></div></div><div class="customer-stats"><div class="customer-stat"><span>کل خدمات</span><b>${fa(c.total_services)} مورد</b></div><div class="customer-stat ok"><span>انجام شده</span><b>${fa(c.completed_services)} مورد</b></div><div class="customer-stat bad"><span>کنسل شده</span><b>${fa(c.cancelled_services)} مورد</b></div><div class="customer-stat cyan"><span>مجموع دریافتی</span><b>${money(c.total_received)}</b></div></div></article>`
}
async function searchCustomers(){
  const q=$('#customerSearch').value.trim(),box=$('#customerResults');if(q.length<2){box.innerHTML='<div class="empty">حداقل دو حرف از نام، شماره یا آدرس را بنویس.</div>';return}
  $('#searchBusy').textContent='…';try{const rows=await api(`/api/mini/customers?q=${encodeURIComponent(q)}`);box.innerHTML=rows.length?rows.map(customerCard).join(''):'<div class="empty">مشتری پیدا نشد.</div>'}catch(e){box.innerHTML=`<div class="empty error">${escapeHtml(errorText(e))}</div>`}finally{$('#searchBusy').textContent=''}
}
function historyItem(x){
  const isCancel=x.status==='cancelled',when=x.visited_at||x.completed_at||x.cancelled_at||x.created_at||x.received_at,title=x.service_type||x.job_type||'سرویس';
  const side=isCancel?`<span class="history-side bad">${escapeHtml(x.cancel_reason||'کنسل شده')}</span>`:`<span class="history-side money">${money(x.received_amount)}</span>`;
  return `<div class="history-item ${isCancel?'cancel':''}"><span class="history-dot"></span><div class="history-copy"><b>${escapeHtml(title)}</b><div class="date">${pDateTime(when)} • ${isCancel?'کنسل شده':'انجام شده'}</div>${x.description?`<small>${escapeHtml(x.description)}</small>`:''}</div>${side}</div>`
}
async function openCustomer(id){
  interactive('open');const box=$('#customerResults');box.innerHTML='<div class="skeleton"></div><div class="skeleton"></div>';
  try{
    const d=await api(`/api/mini/customers/${encodeURIComponent(id)}`),c=d.customer,name=[c.first_name,c.last_name].filter(Boolean).join(' ')||'بدون نام';
    const all=[...(d.visits||[]),...(d.bale_jobs||[])].sort((a,b)=>new Date(b.visited_at||b.completed_at||b.cancelled_at||b.created_at||b.received_at)-new Date(a.visited_at||a.completed_at||a.cancelled_at||a.created_at||a.received_at));
    box.innerHTML=`<button id="backSearch" class="back-btn">${icon('i-route')}<span>بازگشت به جستجو</span></button><article class="customer-card detail"><div class="customer-header"><div class="customer-avatar">${icon('i-customers')}</div><div class="customer-id"><div class="customer-name">${escapeHtml(name)}</div><small>${escapeHtml((c.phones||[]).join(' • '))}</small></div></div><div class="customer-lines"><div>${icon('i-map')}<span>${escapeHtml(c.address||'آدرس ثبت نشده')}</span></div><div>${icon('i-daily')}<span>پلاک: ${escapeHtml(c.plaque||'—')} • واحد: ${escapeHtml(c.unit_no||'—')}</span></div>${c.device_model?`<div>${icon('i-services')}<span>مدل دستگاه: ${escapeHtml(c.device_model)}</span></div>`:''}${c.notes?`<div>${icon('i-more')}<span>${escapeHtml(c.notes)}</span></div>`:''}</div><div class="history"><div class="section-title"><span>تاریخچه خدمات</span><i></i></div>${all.length?all.map(historyItem).join(''):'<div class="empty">هنوز سابقه‌ای ثبت نشده است.</div>'}</div></article>`;
    $('#backSearch').onclick=()=>{interactive('nav');searchCustomers()};
  }catch(e){box.innerHTML=`<div class="empty error">${escapeHtml(errorText(e))}</div>`}
}

function periodFa(p){return p==='daily'?'روزانه':p==='weekly'?'هفتگی':'ماهانه'}
async function loadFinance(){
  const cards=$('#financeCards');cards.innerHTML='<div class="skeleton"></div><div class="skeleton"></div>';
  try{
    const d=await api(`/api/mini/finance?period=${state.period}&date=${state.date}`),s=d.summary;
    cards.innerHTML=`<div class="finance-card green">${icon('i-finance')}<span>دریافتی</span><b>${money(s.received_total)}</b><i></i></div><div class="finance-card blue">${icon('i-insights')}<span>سهم شرکت</span><b>${money(s.company_share)}</b><i></i></div><div class="finance-card purple">${icon('i-invoices')}<span>جمع کل</span><b>${money(s.invoice_total)}</b><i></i></div><div class="finance-card gold">${icon('i-sync')}<span>تسویه با شرکت</span><b>${money(s.settled_total)}</b><i></i></div>`;
    const noData=Number(s.service_count||0)===0&&Number(s.received_total||0)===0&&Number(s.invoice_total||0)===0&&Number(s.settled_total||0)===0;
    const info=noData?`<div class="empty">${state.period==='daily'&&state.date===todayISO()?'اتصال به دیتابیس برقرار است؛ امروز هنوز اطلاعات مالی ثبت نشده. برای دیدن سوابق، روز قبل یا بازه هفتگی/ماهانه را انتخاب کن.':'برای این بازه هنوز اطلاعات مالی ثبت نشده است.'}</div>`:'';
    $('#financeDetails').innerHTML=`${info}<div class="detail-row"><span>بازه گزارش</span><b>${pDate(d.from,false)} تا ${pDate(d.to,false)}</b></div><div class="detail-row"><span>تعداد خدمات انجام‌شده</span><b>${fa(s.service_count)} مورد</b></div><div class="detail-row"><span>مجموع دریافتی</span><b>${money(s.received_total)}</b></div><div class="detail-row"><span>سهم شرکت</span><b>${money(s.company_share)}</b></div><div class="detail-row"><span>تسویه انجام‌شده</span><b>${money(s.settled_total)}</b></div><div class="detail-row highlight"><span>مانده قابل تسویه</span><b>${money(s.payable)}</b></div>`;
    renderChart(d.chart||[]);$('#chartSubtitle').textContent=`${periodFa(state.period)} • ${fa(s.service_count)} سرویس • ${money(s.received_total)}`;$$('#financeTabs button').forEach(b=>b.classList.toggle('active',b.dataset.period===state.period));
  }catch(e){cards.innerHTML=`<div class="empty error wide">${escapeHtml(errorText(e))}</div>`;$('#financeDetails').innerHTML=''}
}
function renderChart(points){
  const box=$('#barChart');if(!points.length){box.innerHTML='<div class="empty">برای این بازه داده‌ای وجود ندارد.</div>';return}
  const max=Math.max(...points.map(x=>Number(x.received||0)),1);
  box.innerHTML=points.map(x=>{const h=Math.max(8,Math.round(Number(x.received||0)/max*100));return `<div class="bar-col"><span class="bar-value">${fa(x.received)}</span><div class="bar-track"><i style="height:${h}%"></i></div><small>${pDate(x.day,false)}</small></div>`}).join('')
}
function toggleChart(){$('#chartAccordion').classList.toggle('open');interactive('open')}
function toggleSettings(){$('.settings-block').classList.toggle('open');interactive('open')}
async function changePassword(ev){
  ev.preventDefault();interactive('tap');const out=$('#passwordMessage');out.textContent='در حال ذخیره...';out.className='form-message show';
  try{
    await api('/api/mini/password',{method:'POST',body:JSON.stringify({current_password:$('#currentPassword').value,new_password:$('#newPassword').value,confirm_password:$('#confirmPassword').value})});
    $('#passwordForm').reset();out.textContent='رمز عبور با موفقیت تغییر کرد';out.className='form-message show success';await beep('success');toast('رمز جدید ذخیره شد','success');
  }catch(e){out.textContent=errorText(e);out.className='form-message show error';await beep('error')}
}

function bind(){
  $('#soundBtn').onclick=setSound;$('#logoutBtn').onclick=async()=>{interactive('tap');try{await api('/api/mini/logout',{method:'POST'});}finally{showLogin()}};
  $$('.nav-btn').forEach(b=>b.onclick=()=>navigate(b.dataset.view));
  $('#prevDay').onclick=()=>{state.date=shiftDate(state.date,-1);interactive('nav');loadDay();if(state.view==='finance')loadFinance()};
  $('#nextDay').onclick=()=>{state.date=shiftDate(state.date,1);interactive('nav');loadDay();if(state.view==='finance')loadFinance()};
  $('#customerSearch').addEventListener('input',()=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(searchCustomers,260)});
  $('#customerResults').addEventListener('click',e=>{const c=e.target.closest('[data-customer]');if(c)openCustomer(c.dataset.customer)});
  $$('#financeTabs button').forEach(b=>b.onclick=()=>{state.period=b.dataset.period;interactive('nav');loadFinance()});
  $('#chartToggle').onclick=toggleChart;$('#settingsToggle').onclick=toggleSettings;$('#passwordForm').onsubmit=changePassword;
  $('#loginForm').onsubmit=async ev=>{
    ev.preventDefault();if(state.loginBusy)return;await unlockFromGesture();const err=$('#loginError'),password=$('#password').value;err.textContent='';
    if(!password){err.textContent='رمز عبور را وارد کن.';await beep('error');return}
    setLoginBusy(true);
    try{await api('/api/mini/login',{method:'POST',body:JSON.stringify({username:'admin',password})});$('#password').value='';await beep('success');showApp()}
    catch(e){err.textContent=errorText(e);await beep('error')}
    finally{setLoginBusy(false)}
  };
  document.addEventListener('pointerdown',unlockFromGesture,{passive:true});document.addEventListener('touchend',unlockFromGesture,{passive:true});
  window.addEventListener('pageshow',()=>{state.audioUnlocked=false;if(state.sound)void ensureAudio()});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&state.sound){state.audioUnlocked=false;void ensureAudio()}});
}
async function start(){
  state.date=todayISO();bind();updateSoundUI();try{window.Bale?.WebApp?.ready?.();window.Bale?.WebApp?.expand?.()}catch{}
  let session={authenticated:false};try{session=await api('/api/mini/session')}catch{}setTimeout(()=>{hideSplash();session.authenticated?showApp():showLogin()},760)
}
start();
})();