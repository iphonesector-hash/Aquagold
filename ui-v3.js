function app(){return{
  token:localStorage.getItem('token'),
  user:JSON.parse(localStorage.getItem('user')||'null'),
  page:'dashboard',busy:false,error:'',
  stats:{today:{},total_customers:0},jobs:[],customers:[],expenses:[],settlements:[],
  analytics:{totals:{},months:[],service_types:[]},insights:{top_customers:[],busy_days:[],expense_categories:[],areas:[],service_analysis:[]},
  reminders:[],auditRows:[],nearby:[],routePlan:[],
  loginForm:{username:'',password:''},customerSearch:'',serviceSearch:'',selectedCustomer:null,
  customerEdit:{},
  serviceForm:{customer_id:'',service_type:'',description:'',invoice_amount:'',received_amount:'',payment_method:'',status:'completed',visited_at:'',next_service_at:'',visitor_code:''},
  expenseForm:{category:'goods',title:'',amount:'',expense_date:'',notes:''},
  settlementForm:{amount:'',settled_at:'',notes:''},financeSettings:{company_share_percent:50},
  gps:{},smartText:'',smartParsed:null,smartGps:{},smartSuggestions:[],smartCustomerId:'',
  mainMap:null,mainMarkers:[],userMarker:null,editMap:null,editMarker:null,
  monthlyChart:null,yearlyChart:null,serviceChart:null,
  navs:[
    {id:'dashboard',label:'داشبورد',icon:'◫'},{id:'daily',label:'روزانه',icon:'📅'},{id:'customers',label:'مشتریان',icon:'👥'},
    {id:'services',label:'سرویس‌ها',icon:'🧾'},{id:'map',label:'نقشه',icon:'📍'},{id:'expense',label:'هزینه‌ها',icon:'💸'},
    {id:'finance',label:'مالی',icon:'📊'},{id:'insights',label:'تحلیل',icon:'🧠'},{id:'smart',label:'هوشمند',icon:'✨'},
    {id:'reminders',label:'یادآوری',icon:'⏰'},{id:'settings',label:'تنظیمات',icon:'⚙️'}
  ],
  get userName(){return [this.user?.first_name,this.user?.last_name].filter(Boolean).join(' ')||this.user?.username||''},
  get filteredCustomers(){let q=this.customerSearch.trim().toLowerCase();if(!q)return this.customers;return this.customers.filter(c=>[c.name,(c.phones||[]).join(' '),c.address,c.map_label,c.plaque,c.unit_no,c.device_model].join(' ').toLowerCase().includes(q))},
  get filteredJobs(){let q=this.serviceSearch.trim().toLowerCase();if(!q)return this.jobs;return this.jobs.filter(j=>[j.name,j.phone,j.address,j.description,j.service_type].join(' ').toLowerCase().includes(q))},
  get selectedCustomerJobs(){return this.selectedCustomer?this.jobs.filter(j=>String(j.customer_id)===String(this.selectedCustomer.id)):[]},
  get estimatedCompanyShare(){let r=this.num(this.serviceForm.received_amount||this.serviceForm.invoice_amount);return Math.round(r*(Number(this.financeSettings.company_share_percent)||50)/100)},
  get estimatedBalance(){return Math.max(this.num(this.serviceForm.invoice_amount)-this.num(this.serviceForm.received_amount),0)},
  get financeCards(){let t=this.analytics.totals||{};return[
    {label:'فروش/فاکتور',value:t.invoice},{label:'دریافتی',value:t.received},{label:'سهم شرکت',value:t.company_share},
    {label:'هزینه‌ها',value:t.expenses},{label:'سود خالص',value:t.net_profit,cls:'text-emerald-700'},{label:'بدهی شرکت',value:t.company_due,cls:'text-amber-700'}
  ]},
  get dailyGroups(){
    let by={};
    for(let j of this.jobs){let key=this.tehranDay(j.date);if(!by[key])by[key]={iso:key,jobs:[],services:0,received:0,company_share:0,customer_balance:0,expenses:0,net_profit:0,sort:new Date(j.date).getTime()};let d=by[key];d.jobs.push(j);d.services++;d.received+=Number(j.received_amount||0);d.company_share+=Number(j.company_share_amount||0);d.customer_balance+=Number(j.customer_balance||0);d.sort=Math.max(d.sort,new Date(j.date).getTime())}
    for(let e of this.expenses){let key=this.tehranDay(e.expense_date);if(!by[key])by[key]={iso:key,jobs:[],services:0,received:0,company_share:0,customer_balance:0,expenses:0,net_profit:0,sort:new Date(e.expense_date).getTime()};by[key].expenses+=Number(e.amount||0);by[key].sort=Math.max(by[key].sort,new Date(e.expense_date).getTime())}
    for(let d of Object.values(by))d.net_profit=d.received-d.company_share-d.expenses;
    return Object.values(by).sort((a,b)=>b.sort-a.sort)
  },
  get jalaliMonthlyMetrics(){
    let map={};
    const ensure=(p,stamp)=>{let key=`${p.year}/${String(p.month).padStart(2,'0')}`;if(!map[key])map[key]={key,label:key,sort:stamp,received:0,company_share:0,expenses:0,net_profit:0,services:0};return map[key]};
    for(let j of this.jobs){let p=this.jalaliParts(j.date);let d=ensure(p,new Date(j.date).getTime());d.received+=Number(j.received_amount||0);d.company_share+=Number(j.company_share_amount||0);d.services++}
    for(let e of this.expenses){let p=this.jalaliParts(e.expense_date);let d=ensure(p,new Date(e.expense_date).getTime());d.expenses+=Number(e.amount||0)}
    for(let d of Object.values(map))d.net_profit=d.received-d.company_share-d.expenses;
    return Object.values(map).sort((a,b)=>a.sort-b.sort)
  },
  get jalaliYearlyMetrics(){
    let map={};
    const ensure=(year,stamp)=>{if(!map[year])map[year]={year:String(year),sort:stamp,received:0,company_share:0,expenses:0,net_profit:0,services:0};return map[year]};
    for(let j of this.jobs){let p=this.jalaliParts(j.date);let d=ensure(p.year,new Date(j.date).getTime());d.received+=Number(j.received_amount||0);d.company_share+=Number(j.company_share_amount||0);d.services++}
    for(let e of this.expenses){let p=this.jalaliParts(e.expense_date);let d=ensure(p.year,new Date(e.expense_date).getTime());d.expenses+=Number(e.amount||0)}
    for(let d of Object.values(map))d.net_profit=d.received-d.company_share-d.expenses;
    return Object.values(map).sort((a,b)=>a.sort-b.sort)
  },
  get smartRows(){let p=this.smartParsed||{};return[['موتور تحلیل',this.parserLabel(p.parser)],['نام خانوادگی',p.last_name],['شماره‌ها',(p.phones||[]).join(' • ')],['آدرس',p.address],['سرویس',p.service_type],['شرح',p.description],['ویزیتور',p.visitor_code],['زمان',p.time_text],['مبلغ',p.amount?this.money(p.amount)+' تومان':'—']]},

  num(v){return Number(String(v||0).replace(/[٬،,\s]/g,''))||0},
  money(v){return new Intl.NumberFormat('fa-IR').format(Number(v||0))},
  jalaliParts(v){let parts=new Intl.DateTimeFormat('en-US-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(new Date(v));let o={};parts.forEach(p=>{if(['year','month','day'].includes(p.type))o[p.type]=Number(p.value)});return o},
  tehranDay(v){let f=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'});return f.format(new Date(v))},
  persianDate(v){if(!v)return'';let d=/^\d{4}-\d{2}-\d{2}$/.test(v)?new Date(v+'T12:00:00+03:30'):new Date(v);return new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit',weekday:'long'}).format(d)},
  persianDateTime(v){if(!v)return'';try{return new Intl.DateTimeFormat('fa-IR-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(v))}catch{return v}},
  weekdayName(n){return({1:'دوشنبه',2:'سه‌شنبه',3:'چهارشنبه',4:'پنجشنبه',5:'جمعه',6:'شنبه',7:'یکشنبه'})[Number(n)]||String(n)},
  parserLabel(p){return ({ai:'هوش مصنوعی',local:'تحلیل محلی', 'local-fallback':'تحلیل محلی (AI موقتاً در دسترس نبود)'})[p]||p||'تحلیل محلی'},
  expenseCategory(c){return({goods:'خرید جنس/قطعه',fuel:'بنزین/سوخت',parking:'پارکینگ',tools:'ابزار/تعمیر',food:'غذا',other:'متفرقه'})[c]||c},

  async api(path,opts={}){let h={'Content-Type':'application/json',...(opts.headers||{})};if(this.token)h.Authorization='Bearer '+this.token;let r=await fetch('/api'+path,{...opts,headers:h});let d={};try{d=await r.json()}catch{}if(r.status===401&&path!='/login'){this.logout();throw Error('نشست منقضی شد')}if(!r.ok){let e=new Error(d.error||'خطا در ارتباط با سرور');e.data=d;throw e}return d},
  async init(){if(this.token){await this.refreshAll();this.locate(false)}},
  async login(){this.busy=true;this.error='';try{let d=await this.api('/login',{method:'POST',body:JSON.stringify(this.loginForm)});this.token=d.token;this.user=d.user;localStorage.setItem('token',d.token);localStorage.setItem('user',JSON.stringify(d.user));await this.refreshAll()}catch(e){this.error='نام کاربری یا رمز عبور نادرست است'}finally{this.busy=false}},
  logout(){localStorage.clear();location.reload()},
  async refreshAll(){
    let [s,j,c,e,set,a,r,fs,i,au]=await Promise.all([
      this.api('/stats'),this.api('/jobs'),this.api('/customers'),this.api('/expenses'),this.api('/settlements'),this.api('/reports/analytics'),this.api('/reminders?days=45'),this.api('/settings/finance'),this.api('/reports/insights'),this.api('/audit?limit=30')
    ]);
    this.stats=s;this.jobs=j||[];this.customers=c||[];this.expenses=e||[];this.settlements=set||[];this.analytics=a||{totals:{},months:[],service_types:[]};this.reminders=r||[];this.financeSettings=fs||{company_share_percent:50};this.insights=i||{};this.auditRows=au||[]
  },
  async go(p){this.page=p;if(['dashboard','daily','customers','services','expense','finance','insights','reminders','settings'].includes(p))await this.refreshAll();if(p==='map')setTimeout(()=>this.renderMainMap(),100);if(p==='finance')setTimeout(()=>this.renderCharts(),120)},

  newCustomer(){this.customerEdit={id:null,first_name:'',last_name:'',phone:'',phone2:'',address:'',map_label:'',plaque:'',unit_no:'',device_model:'',notes:'',latitude:null,longitude:null,location_accuracy_m:null,location_source:null};this.page='customer-edit';setTimeout(()=>this.initEditMap(),100)},
  editCustomer(c){this.customerEdit={...c,phone:(c.phones||[])[0]||'',phone2:(c.phones||[])[1]||''};this.page='customer-edit';setTimeout(()=>this.initEditMap(),100)},
  async saveCustomer(){if(!this.customerEdit.last_name)return alert('نام خانوادگی لازم است');this.busy=true;try{let f=this.customerEdit;let payload={...f,phones:[f.phone,f.phone2].filter(Boolean)};let cid=f.id;if(cid){await this.api('/customers/'+cid,{method:'PATCH',body:JSON.stringify(payload)});if(f.latitude&&f.longitude)await this.api(`/customers/${cid}/location`,{method:'PATCH',body:JSON.stringify({latitude:f.latitude,longitude:f.longitude,accuracy:f.location_accuracy_m,source:f.location_source||'manual'})})}else{let d=await this.api('/customers',{method:'POST',body:JSON.stringify(payload)});cid=d.id}await this.refreshAll();this.page='customers';alert('مشتری ذخیره شد')}catch(e){alert(e.message)}finally{this.busy=false}},
  openCustomer(c){this.selectedCustomer=c;this.page='customer-detail'},
  serviceFor(c){this.serviceForm={customer_id:c.id,service_type:'',description:'',invoice_amount:'',received_amount:'',payment_method:'',status:'completed',visited_at:'',next_service_at:'',visitor_code:''};this.page='new-service'},
  async createService(){if(!this.serviceForm.customer_id)return alert('مشتری را انتخاب کن');try{let f={...this.serviceForm,invoice_amount:this.num(this.serviceForm.invoice_amount),received_amount:this.num(this.serviceForm.received_amount||this.serviceForm.invoice_amount)};await this.api('/jobs',{method:'POST',body:JSON.stringify(f)});this.serviceForm={customer_id:'',service_type:'',description:'',invoice_amount:'',received_amount:'',payment_method:'',status:'completed',visited_at:'',next_service_at:'',visitor_code:''};await this.refreshAll();this.page='services';alert('سرویس ثبت شد')}catch(e){alert(e.message)}},

  locate(show=true){return new Promise((resolve,reject)=>{if(!navigator.geolocation){if(show)alert('GPS در دسترس نیست');return reject()}navigator.geolocation.getCurrentPosition(p=>{this.gps={lat:p.coords.latitude,lng:p.coords.longitude,accuracy:p.coords.accuracy};resolve(this.gps)},e=>{if(show)alert('اجازه دسترسی GPS داده نشد');reject(e)},{enableHighAccuracy:true,timeout:15000,maximumAge:5000})})},
  async captureEditGps(){try{let g=await this.locate();Object.assign(this.customerEdit,{latitude:g.lat,longitude:g.lng,location_accuracy_m:g.accuracy,location_source:'gps'});this.placeEditMarker()}catch{}},
  applyManualCoords(){if(!this.customerEdit.latitude||!this.customerEdit.longitude)return alert('مختصات را وارد کن');this.customerEdit.location_source='manual';this.placeEditMarker()},
  initEditMap(){let el=document.getElementById('editMap');if(!el)return;if(this.editMap){this.editMap.remove();this.editMap=null}this.editMap=new maplibregl.Map({container:'editMap',style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap'}},layers:[{id:'osm',type:'raster',source:'osm'}]},center:[this.customerEdit.longitude||51.389,this.customerEdit.latitude||35.6892],zoom:this.customerEdit.latitude?16:11});this.editMap.addControl(new maplibregl.NavigationControl(),'top-left');this.editMap.on('click',e=>{this.customerEdit.latitude=e.lngLat.lat;this.customerEdit.longitude=e.lngLat.lng;this.customerEdit.location_source='map';this.placeEditMarker()});this.placeEditMarker()},
  placeEditMarker(){if(!this.editMap||!this.customerEdit.latitude||!this.customerEdit.longitude)return;if(this.editMarker)this.editMarker.remove();this.editMarker=new maplibregl.Marker({draggable:true}).setLngLat([this.customerEdit.longitude,this.customerEdit.latitude]).addTo(this.editMap);this.editMarker.on('dragend',()=>{let p=this.editMarker.getLngLat();this.customerEdit.latitude=p.lat;this.customerEdit.longitude=p.lng;this.customerEdit.location_source='drag'});this.editMap.flyTo({center:[this.customerEdit.longitude,this.customerEdit.latitude],zoom:16})},
  renderMainMap(){let el=document.getElementById('mainMap');if(!el)return;if(!this.mainMap){this.mainMap=new maplibregl.Map({container:'mainMap',style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap'}},layers:[{id:'osm',type:'raster',source:'osm'}]},center:[51.389,35.6892],zoom:10});this.mainMap.addControl(new maplibregl.NavigationControl(),'top-left')}this.mainMarkers.forEach(m=>m.remove());this.mainMarkers=[];let pts=[];for(let c of this.customers.filter(x=>x.latitude&&x.longitude)){let label=c.map_label||c.name;let html=`<div dir="rtl"><b>${this.escapeHtml(label)}</b><br>${this.escapeHtml((c.phones||[]).join(' • '))}<br>${this.escapeHtml(c.address||'')}</div>`;let m=new maplibregl.Marker().setLngLat([c.longitude,c.latitude]).setPopup(new maplibregl.Popup({offset:20}).setHTML(html)).addTo(this.mainMap);this.mainMarkers.push(m);pts.push([c.longitude,c.latitude])}if(pts.length){let b=pts.reduce((bb,p)=>bb.extend(p),new maplibregl.LngLatBounds(pts[0],pts[0]));this.mainMap.fitBounds(b,{padding:50,maxZoom:15})}setTimeout(()=>this.mainMap.resize(),80)},
  escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))},
  async liveLocate(){try{let g=await this.locate();this.renderMainMap();if(this.userMarker)this.userMarker.remove();this.userMarker=new maplibregl.Marker({color:'#2563eb'}).setLngLat([g.lng,g.lat]).setPopup(new maplibregl.Popup().setHTML('<div dir="rtl"><b>موقعیت فعلی من</b></div>')).addTo(this.mainMap);this.mainMap.flyTo({center:[g.lng,g.lat],zoom:16})}catch{}},
  async loadNearby(){try{let g=await this.locate();this.nearby=await this.api(`/customers/nearby?lat=${g.lat}&lng=${g.lng}&radius=300`);await this.liveLocate()}catch(e){alert(e.message)}},
  async loadRoutePlan(){try{let g=await this.locate();this.routePlan=await this.api(`/route/nearest?lat=${g.lat}&lng=${g.lng}&limit=12`);await this.liveLocate()}catch(e){alert(e.message)}},
  showOnMap(c){this.page='map';setTimeout(()=>{this.renderMainMap();this.mainMap.flyTo({center:[c.longitude,c.latitude],zoom:17})},120)},
  copyRoute(){let t=['🗺 مسیر پیشنهادی بر اساس نزدیکی'];this.routePlan.forEach((r,i)=>t.push(`${i+1}) ${r.map_label||r.name} — ${r.distance_m} متر — ${r.phone||''}`));this.copyText(t.join('\n'))},

  async createExpense(){try{let f={...this.expenseForm,amount:this.num(this.expenseForm.amount)};await this.api('/expenses',{method:'POST',body:JSON.stringify(f)});this.expenseForm={category:'goods',title:'',amount:'',expense_date:'',notes:''};await this.refreshAll();alert('هزینه ثبت شد')}catch(e){alert(e.message)}},
  async removeExpense(e){if(!confirm('این هزینه حذف شود؟'))return;await this.api('/expenses/'+e.id,{method:'DELETE'});await this.refreshAll()},
  async createSettlement(){try{await this.api('/settlements',{method:'POST',body:JSON.stringify({...this.settlementForm,amount:this.num(this.settlementForm.amount)})});this.settlementForm={amount:'',settled_at:'',notes:''};await this.refreshAll();this.renderCharts();alert('تسویه ثبت شد')}catch(e){alert(e.message)}},
  async saveFinanceSettings(){try{this.financeSettings=await this.api('/settings/finance',{method:'PATCH',body:JSON.stringify(this.financeSettings)});alert('تنظیمات ذخیره شد')}catch(e){alert(e.message)}},

  renderCharts(){
    let months=this.jalaliMonthlyMetrics,labels=months.map(m=>m.label),c1=document.getElementById('monthlyChart');
    if(c1){if(this.monthlyChart)this.monthlyChart.destroy();this.monthlyChart=new Chart(c1,{type:'line',data:{labels,datasets:[{label:'دریافتی',data:months.map(m=>m.received)},{label:'سود خالص',data:months.map(m=>m.net_profit)},{label:'هزینه',data:months.map(m=>m.expenses)}]},options:{responsive:true,plugins:{legend:{position:'bottom'}}}})}
    let years=this.jalaliYearlyMetrics,cY=document.getElementById('yearlyChart');
    if(cY){if(this.yearlyChart)this.yearlyChart.destroy();this.yearlyChart=new Chart(cY,{type:'bar',data:{labels:years.map(y=>y.year),datasets:[{label:'دریافتی',data:years.map(y=>y.received)},{label:'سود خالص',data:years.map(y=>y.net_profit)}]},options:{responsive:true,plugins:{legend:{position:'bottom'}}}})}
    let types=this.analytics.service_types||[],c2=document.getElementById('serviceChart');
    if(c2){if(this.serviceChart)this.serviceChart.destroy();this.serviceChart=new Chart(c2,{type:'bar',data:{labels:types.map(x=>x.service_type||'نامشخص'),datasets:[{label:'دریافتی',data:types.map(x=>x.received)}]},options:{responsive:true,plugins:{legend:{display:false}}}})}
  },
  copyText(t){navigator.clipboard?.writeText(t).then(()=>alert('گزارش کپی شد')).catch(()=>prompt('متن گزارش:',t))},
  dayReportText(d){let lines=[`📅 ${this.persianDate(d.iso)}`];d.jobs.forEach((j,i)=>lines.push(`${i+1}) ${j.name} — ${j.description||j.service_type||'سرویس'} — ${this.money(j.received_amount)} تومان`));lines.push(`\nجمع دریافتی: ${this.money(d.received)} تومان`,`سهم شرکت: ${this.money(d.company_share)} تومان`,`هزینه‌ها: ${this.money(d.expenses)} تومان`,`مانده مشتری‌ها: ${this.money(d.customer_balance)} تومان`,`سود خالص من: ${this.money(d.net_profit)} تومان`);return lines.join('\n')},
  copyDay(d){this.copyText(this.dayReportText(d))},copyAllDaily(){this.copyText(this.dailyGroups.map(d=>this.dayReportText(d)).join('\n\n──────────\n\n'))},
  async downloadExcel(){try{let r=await fetch('/api/export.xlsx',{headers:{Authorization:'Bearer '+this.token}});if(!r.ok)throw Error('خروجی Excel ساخته نشد');let b=await r.blob(),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download='AquaGold.xlsx';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),2000)}catch(e){alert(e.message)}},
  printPdf(){window.print()},

  async captureSmartGps(){try{let g=await this.locate();this.smartGps={lat:g.lat,lng:g.lng,accuracy:g.accuracy};if(this.smartParsed)await this.loadSmartSuggestions()}catch{}},
  async analyzeSmart(){if(!this.smartText.trim())return alert('متن را وارد کن');try{this.smartParsed=await this.api('/smart/parse',{method:'POST',body:JSON.stringify({text:this.smartText})});this.smartCustomerId='';await this.loadSmartSuggestions()}catch(e){alert(e.message)}},
  async loadSmartSuggestions(){let p=this.smartParsed||{},qs=new URLSearchParams();if(p.last_name)qs.set('surname',p.last_name);if((p.phones||[])[0])qs.set('phone',p.phones[0]);if(this.smartGps.lat){qs.set('lat',this.smartGps.lat);qs.set('lng',this.smartGps.lng)}this.smartSuggestions=await this.api('/customers/suggest?'+qs.toString())},
  async registerSmart(){try{let p=this.smartParsed||{},d=await this.api('/smart/register',{method:'POST',body:JSON.stringify({text:this.smartText,parsed:p,customer_id:this.smartCustomerId||null,latitude:this.smartGps.lat,longitude:this.smartGps.lng,accuracy:this.smartGps.accuracy})});this.smartText='';this.smartParsed=null;this.smartSuggestions=[];this.smartCustomerId='';await this.refreshAll();alert('ثبت هوشمند انجام شد');let c=this.customers.find(x=>String(x.id)===String(d.customer_id));if(c)this.openCustomer(c)}catch(e){alert(e.message)}}
}}