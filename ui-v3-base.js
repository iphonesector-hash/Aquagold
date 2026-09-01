function app(){return{
  token:false,authReady:false,
  user:null,
  page:'dashboard',busy:false,error:'',online:navigator.onLine,offlineQueueCount:0,syncingOffline:false,
  stats:{today:{},total_customers:0},jobs:[],customers:[],expenses:[],settlements:[],
  analytics:{totals:{},months:[],service_types:[]},insights:{top_customers:[],busy_days:[],expense_categories:[],areas:[],service_analysis:[]},
  reminders:[],auditRows:[],nearby:[],routePlan:[],routeMeta:{},geocodeResults:[],geocoding:false,
  loginForm:{username:'',password:''},customerSearch:'',serviceSearch:'',selectedCustomer:null,selectedCustomerJobsRemote:[],
  customerPagination:{page:1,per_page:100,total:0,pages:1},jobPagination:{page:1,per_page:100,total:0,pages:1},
  customerEdit:{},
  serviceForm:{customer_id:'',service_type:'',description:'',invoice_amount:'',received_amount:'',payment_method:'',status:'completed',visited_at:'',next_service_at:'',visitor_code:''},
  expenseForm:{category:'goods',title:'',amount:'',expense_date:'',notes:''},
  settlementForm:{amount:'',settled_at:'',notes:''},financeSettings:{company_share_percent:50},
  gps:{},smartText:'',smartParsed:null,smartGps:{},smartSuggestions:[],smartCustomerId:'',
  mainMap:null,mainMarkers:[],userMarker:null,editMap:null,editMarker:null,routeLayer:null,heatmapLayer:null,
  monthlyChart:null,yearlyChart:null,serviceChart:null,financeDonutChart:null,financePolarChart:null,
  pushBusy:false,pushActive:false,pushPermission:(window.Notification?.permission||'default'),
  navs:[
    {id:'dashboard',label:'داشبورد',icon:'◫'},{id:'daily',label:'روزانه',icon:'📅'},{id:'customers',label:'مشتریان',icon:'👥'},
    {id:'services',label:'سرویس‌ها',icon:'🧾'},{id:'map',label:'نقشه',icon:'📍'},{id:'expense',label:'هزینه‌ها',icon:'💸'},
    {id:'finance',label:'مالی',icon:'📊'},{id:'insights',label:'تحلیل',icon:'🧠'},{id:'smart',label:'هوشمند',icon:'✨'},
    {id:'reminders',label:'یادآوری',icon:'⏰'},{id:'settings',label:'تنظیمات',icon:'⚙️'}
  ],
  get userName(){return [this.user?.first_name,this.user?.last_name].filter(Boolean).join(' ')||this.user?.username||''},
  get canAdmin(){return ['admin','superadmin'].includes(this.user?.role)},
  get filteredCustomers(){let q=this.customerSearch.trim().toLowerCase();if(!q)return this.customers;return this.customers.filter(c=>[c.name,(c.phones||[]).join(' '),c.address,c.map_label,c.plaque,c.unit_no,c.device_model].join(' ').toLowerCase().includes(q))},
  get filteredJobs(){let q=this.serviceSearch.trim().toLowerCase();if(!q)return this.jobs;return this.jobs.filter(j=>[j.name,j.phone,j.address,j.description,j.service_type].join(' ').toLowerCase().includes(q))},
  get selectedCustomerJobs(){return this.selectedCustomerJobsRemote},
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
  persianNumericDate(v){let d=v instanceof Date?v:new Date(v),parts=new Intl.DateTimeFormat('en-US-u-ca-persian',{timeZone:'Asia/Tehran',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d),out={};parts.forEach(p=>{if(['year','month','day'].includes(p.type))out[p.type]=p.value});let fa=x=>String(x||'').replace(/\d/g,n=>'۰۱۲۳۴۵۶۷۸۹'[Number(n)]);return `\u2066${fa(out.year)}/${fa(out.month)}/${fa(out.day)}\u2069`},
  persianDate(v){if(!v)return'';let d=/^\d{4}-\d{2}-\d{2}$/.test(v)?new Date(v+'T12:00:00+03:30'):new Date(v),weekday=new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',weekday:'long'}).format(d);return `${weekday}، ${this.persianNumericDate(d)}`},
  persianDateTime(v){if(!v)return'';try{let d=new Date(v),time=new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);return `${this.persianNumericDate(d)} • ${time}`}catch{return v}},
  weekdayName(n){return({1:'دوشنبه',2:'سه‌شنبه',3:'چهارشنبه',4:'پنجشنبه',5:'جمعه',6:'شنبه',7:'یکشنبه'})[Number(n)]||String(n)},
  parserLabel(p){return ({ai:'هوش مصنوعی',local:'تحلیل محلی','local-offline':'تحلیل محلی آفلاین','local-fallback':'تحلیل محلی (AI موقتاً در دسترس نبود)'})[p]||p||'تحلیل محلی'},
  expenseCategory(c){return({goods:'خرید جنس/قطعه',fuel:'بنزین/سوخت',parking:'پارکینگ',tools:'ابزار/تعمیر',food:'غذا',other:'متفرقه'})[c]||c},

  cookie(name){let hit=document.cookie.split('; ').find(x=>x.startsWith(name+'='));return hit?decodeURIComponent(hit.slice(name.length+1)):''},
  pendingLogout(){try{return localStorage.getItem('aq_logout_pending')==='1'}catch{return false}},
  async finishPendingLogout(){
    if(!this.pendingLogout()||!navigator.onLine)return false;
    try{
      let headers={'Content-Type':'application/json'},csrf=this.cookie('aquagold_csrf');
      if(csrf)headers['X-CSRF-Token']=csrf;
      let r=await fetch('/api/logout',{method:'POST',headers,credentials:'same-origin'});
      if(!r.ok&&r.status!==401)return false;
      try{localStorage.removeItem('aq_logout_pending')}catch{}
      return true
    }catch{return false}
  },
  async bindOfflineUser(user){let next=String(user?.id||''),previous='';try{previous=localStorage.getItem('aq_offline_user')||''}catch{}if(previous!==next&&window.AquaOffline)await AquaOffline.clear();try{if(next)localStorage.setItem('aq_offline_user',next);else localStorage.removeItem('aq_offline_user')}catch{}},
  async queueOffline(path,method,body,headers={}){
    if(!window.AquaOffline)throw Error('ذخیره آفلاین در دسترس نیست');
    let id=headers['Idempotency-Key']||crypto.randomUUID(),stableCreates=['/customers','/jobs','/expenses','/settlements','/products','/invoices'];
    if(method==='POST'&&stableCreates.includes(path)&&body){try{let data=JSON.parse(body);if(!data.client_id)data.client_id=id;body=JSON.stringify(data)}catch{}}
    let item=await AquaOffline.enqueue({id,path,method,body,headers});
    this.offlineQueueCount=await AquaOffline.count();
    return{queued:true,offline_id:item.id,id:item.id,message:'در صف همگام‌سازی ذخیره شد'}
  },
  async api(path,opts={}){
    let method=(opts.method||'GET').toUpperCase(),safe=['GET','HEAD','OPTIONS'].includes(method),queueable=!['/login','/logout','/smart/parse','/route/optimize'].includes(path),headers={'Content-Type':'application/json',...(opts.headers||{})};
    if(!safe){let csrf=this.cookie('aquagold_csrf');if(csrf)headers['X-CSRF-Token']=csrf;if(!headers['Idempotency-Key'])headers['Idempotency-Key']=crypto.randomUUID()}
    let fetchOpts={method,body:opts.body,headers,credentials:'same-origin'};
    if(!safe&&queueable&&!opts.offlineReplay&&!navigator.onLine)return this.queueOffline(path,method,opts.body,headers);
    try{
      let r=await fetch('/api'+path,fetchOpts),d={};try{d=await r.json()}catch{}
      if(r.status===401&&!['/login','/session','/logout'].includes(path)){this.token=false;this.user=null;let e=Error('نشست منقضی شد');e.status=401;throw e}
      if(!r.ok){if(safe&&window.AquaOffline&&[502,503,504].includes(r.status)){let cached=await AquaOffline.cacheGet('/api'+path);if(cached!==undefined)return cached}if(!safe&&queueable&&!opts.offlineReplay&&[502,503,504].includes(r.status))return this.queueOffline(path,method,opts.body,headers);let e=new Error(d.error||'خطا در ارتباط با سرور');e.status=r.status;e.data=d;throw e}
      if(safe&&window.AquaOffline)await AquaOffline.cachePut('/api'+path,d);
      return d
    }catch(e){
      if(e.status)throw e;
      if(safe&&window.AquaOffline){let cached=await AquaOffline.cacheGet('/api'+path);if(cached!==undefined)return cached}
      if(!safe&&queueable&&!opts.offlineReplay)return this.queueOffline(path,method,opts.body,headers);
      throw e
    }
  },
  async syncOfflineQueue(){if(this.syncingOffline||!navigator.onLine||!this.token||!window.AquaOffline)return;this.syncingOffline=true;try{let r=await AquaOffline.sync((path,opts)=>this.api(path,opts));this.offlineQueueCount=r.remaining;if(r.sent){await this.refreshAll();if(this.refreshCommerce)await this.refreshCommerce();alert(`${r.sent} ثبت آفلاین همگام شد`)}if(r.failed)alert('یک ثبت آفلاین نیاز به بررسی دارد')}finally{this.syncingOffline=false}},
  async init(){
    this.authReady=true;
    try{
      try{this.offlineQueueCount=window.AquaOffline?await Promise.race([AquaOffline.count(),new Promise(resolve=>setTimeout(()=>resolve(0),1200))]):0}catch{this.offlineQueueCount=0}
      window.addEventListener('online',async()=>{this.online=true;if(await this.finishPendingLogout()){location.reload();return}this.syncOfflineQueue()});
      window.addEventListener('offline',()=>{this.online=false});
      if(this.pendingLogout()){
        if(navigator.onLine)await this.finishPendingLogout();
        if(this.pendingLogout()){this.token=false;this.user=null;return}
      }
      try{let d=await this.api('/session');if(!d?.user||(d.expires_at&&Date.parse(d.expires_at)<=Date.now()))throw Error('نشست آفلاین منقضی شده');await this.bindOfflineUser(d.user);if(window.AquaOffline)await AquaOffline.cachePut('/api/session',d);this.token=true;this.user=d.user;await this.refreshAll();this.locate(false).catch(()=>{});await this.syncOfflineQueue()}catch{this.token=false;this.user=null}
    }catch(error){this.token=false;this.user=null;console.warn('AquaGold initialization fallback',error)}finally{this.authReady=true}
  },
  async login(){this.busy=true;this.error='';try{let d=await this.api('/login',{method:'POST',body:JSON.stringify(this.loginForm)});try{localStorage.removeItem('aq_logout_pending')}catch{}await this.bindOfflineUser(d.user);if(window.AquaOffline)await AquaOffline.cachePut('/api/session',{authenticated:true,user:d.user,expires_at:d.expires_at});this.token=true;this.user=d.user;await this.refreshAll()}catch(e){this.error=e.status===429?'تلاش‌های ورود بیش از حد است؛ کمی بعد دوباره امتحان کن':!navigator.onLine||!e.status?'برای ورود اولیه اتصال اینترنت لازم است':'نام کاربری یا رمز عبور نادرست است'}finally{this.busy=false;this.authReady=true}},
  async logout(reload=true){let revoked=!this.token;try{if(this.token){await this.api('/logout',{method:'POST'});revoked=true}}catch{}if(window.AquaOffline)await AquaOffline.clear();try{if(revoked)localStorage.removeItem('aq_logout_pending');else localStorage.setItem('aq_logout_pending','1');localStorage.removeItem('aq_offline_user');localStorage.removeItem('aq_drafts_v4')}catch{}this.token=false;this.user=null;this.offlineQueueCount=0;sessionStorage.removeItem('aq_unlocked');if(reload)location.reload()},
  async refreshAll(){
    let jq=encodeURIComponent(this.serviceSearch.trim()),cq=encodeURIComponent(this.customerSearch.trim());
    const safe=(promise,fallback)=>promise.catch(error=>{console.warn('AquaGold refresh fallback',error);return fallback});
    let [s,j,c,e,set,a,r,fs,i,au]=await Promise.all([
      safe(this.api('/stats'),{today:{},total_customers:0}),safe(this.api(`/jobs?page=${this.jobPagination.page}&per_page=${this.jobPagination.per_page}&q=${jq}`),{items:[],pagination:this.jobPagination}),safe(this.api(`/customers?page=${this.customerPagination.page}&per_page=${this.customerPagination.per_page}&q=${cq}`),{items:[],pagination:this.customerPagination}),safe(this.api('/expenses'),[]),safe(this.api('/settlements'),[]),safe(this.api('/reports/analytics'),{totals:{},months:[],service_types:[]}),safe(this.api('/reminders?days=45'),[]),safe(this.api('/settings/finance'),{company_share_percent:50}),safe(this.api('/reports/insights'),{}),this.canAdmin?safe(this.api('/audit?limit=30'),[]):Promise.resolve([])
    ]);
    this.stats=s;this.jobs=j?.items||[];this.jobPagination=j?.pagination||this.jobPagination;this.customers=c?.items||[];this.customerPagination=c?.pagination||this.customerPagination;this.expenses=e||[];this.settlements=set||[];this.analytics=a||{totals:{},months:[],service_types:[]};this.reminders=r||[];this.financeSettings=fs||{company_share_percent:50};this.insights=i||{};this.auditRows=au||[]
  },
  async loadCustomers(page=1){this.customerPagination.page=page;let q=encodeURIComponent(this.customerSearch.trim()),d=await this.api(`/customers?page=${page}&per_page=${this.customerPagination.per_page}&q=${q}`);this.customers=d.items||[];this.customerPagination=d.pagination||this.customerPagination},
  async loadJobs(page=1){this.jobPagination.page=page;let q=encodeURIComponent(this.serviceSearch.trim()),d=await this.api(`/jobs?page=${page}&per_page=${this.jobPagination.per_page}&q=${q}`);this.jobs=d.items||[];this.jobPagination=d.pagination||this.jobPagination},
  async go(p){this.page=p;if(['dashboard','daily','customers','services','expense','finance','insights','reminders','settings'].includes(p))await this.refreshAll();if(p==='map')setTimeout(()=>this.renderMainMap(),100);if(p==='finance')setTimeout(()=>this.renderCharts(),120)},

  newCustomer(){this.geocodeResults=[];this.customerEdit={id:null,first_name:'',last_name:'',phone:'',phone2:'',address:'',map_label:'',plaque:'',unit_no:'',device_model:'',notes:'',latitude:null,longitude:null,location_accuracy_m:null,location_source:null};this.page='customer-edit';setTimeout(()=>this.initEditMap(),100)},
  editCustomer(c){this.geocodeResults=[];this.customerEdit={...c,phone:(c.phones||[])[0]||'',phone2:(c.phones||[])[1]||''};this.page='customer-edit';setTimeout(()=>this.initEditMap(),100)},
  async saveCustomer(){if(!this.customerEdit.last_name)return alert('نام خانوادگی لازم است');this.busy=true;try{let f=this.customerEdit,payload={...f,phones:[f.phone,f.phone2].filter(Boolean)},cid=f.id,d;if(cid){d=await this.api('/customers/'+cid,{method:'PATCH',body:JSON.stringify(payload)});if(f.latitude&&f.longitude)await this.api(`/customers/${cid}/location`,{method:'PATCH',body:JSON.stringify({latitude:f.latitude,longitude:f.longitude,accuracy:f.location_accuracy_m,source:f.location_source||'manual'})})}else{d=await this.api('/customers',{method:'POST',body:JSON.stringify(payload)});cid=d.id}if(d?.queued){let local={...payload,id:cid,name:[payload.first_name,payload.last_name].filter(Boolean).join(' '),offline_pending:true};if(f.id)this.customers=this.customers.map(c=>String(c.id)===String(f.id)?{...c,...local}:c);else this.customers.unshift(local);this.page='customers';alert('مشتری روی گوشی ذخیره شد و پس از اتصال همگام می‌شود');return}await this.refreshAll();this.page='customers';alert('مشتری ذخیره شد')}catch(e){alert(e.message)}finally{this.busy=false}},
  async openCustomer(c){this.selectedCustomer=c;this.page='customer-detail';try{let d=await this.api(`/customers/${c.id}/jobs?per_page=100`);this.selectedCustomerJobsRemote=d.items||[]}catch(e){this.selectedCustomerJobsRemote=[];alert(e.message)}},
  serviceFor(c){this.serviceForm={customer_id:c.id,service_type:'',description:'',invoice_amount:'',received_amount:'',payment_method:'',status:'completed',visited_at:'',next_service_at:'',visitor_code:''};this.page='new-service'},
  async createService(){if(!this.serviceForm.customer_id)return alert('مشتری را انتخاب کن');try{let f={...this.serviceForm,invoice_amount:this.num(this.serviceForm.invoice_amount),received_amount:this.num(this.serviceForm.received_amount||this.serviceForm.invoice_amount)},d=await this.api('/jobs',{method:'POST',body:JSON.stringify(f)});this.serviceForm={customer_id:'',service_type:'',description:'',invoice_amount:'',received_amount:'',payment_method:'',status:'completed',visited_at:'',next_service_at:'',visitor_code:''};if(d?.queued){let c=this.customers.find(x=>String(x.id)===String(f.customer_id));this.jobs.unshift({...f,id:d.id,name:c?.name||'ثبت آفلاین',date:f.visited_at||new Date().toISOString(),customer_balance:Math.max(f.invoice_amount-f.received_amount,0),offline_pending:true});this.page='services';alert('سرویس در صف همگام‌سازی ذخیره شد');return}await this.refreshAll();this.page='services';alert('سرویس ثبت شد')}catch(e){alert(e.message)}},

  locate(show=true){return new Promise((resolve,reject)=>{if(!navigator.geolocation){if(show)alert('GPS در دسترس نیست');return reject()}navigator.geolocation.getCurrentPosition(p=>{this.gps={lat:p.coords.latitude,lng:p.coords.longitude,accuracy:p.coords.accuracy};resolve(this.gps)},e=>{if(show)alert('اجازه دسترسی GPS داده نشد');reject(e)},{enableHighAccuracy:true,timeout:15000,maximumAge:5000})})},
  async captureEditGps(){try{let g=await this.locate();Object.assign(this.customerEdit,{latitude:g.lat,longitude:g.lng,location_accuracy_m:g.accuracy,location_source:'gps'});this.placeEditMarker()}catch{}},
  applyManualCoords(){if(!this.customerEdit.latitude||!this.customerEdit.longitude)return alert('مختصات را وارد کن');this.customerEdit.location_source='manual';this.placeEditMarker()},
  async geocodeAddress(){if(!this.customerEdit.address?.trim())return alert('اول آدرس را وارد کن');this.geocoding=true;try{let d=await this.api('/geocode?q='+encodeURIComponent(this.customerEdit.address));this.geocodeResults=d.items||[];if(!this.geocodeResults.length)alert('برای این آدرس نتیجه‌ای پیدا نشد')}catch(e){alert(e.message)}finally{this.geocoding=false}},
  applyGeocode(result){this.customerEdit.latitude=result.latitude;this.customerEdit.longitude=result.longitude;this.customerEdit.location_source='geocoded';this.placeEditMarker();this.geocodeResults=[]},
  initEditMap(){
    let el=document.getElementById('editMap');if(!el)return;
    if(this.editMap){this.editMap.remove();this.editMap=null}
    let lat=Number(this.customerEdit.latitude)||35.6892,lng=Number(this.customerEdit.longitude)||51.389;
    this.editMap=L.map(el,{zoomControl:true}).setView([lat,lng],this.customerEdit.latitude?16:11);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(this.editMap);
    this.editMap.on('click',e=>{this.customerEdit.latitude=e.latlng.lat;this.customerEdit.longitude=e.latlng.lng;this.customerEdit.location_source='map';this.placeEditMarker()});
    this.placeEditMarker()
  },
  placeEditMarker(){
    if(!this.editMap||!this.customerEdit.latitude||!this.customerEdit.longitude)return;
    if(this.editMarker)this.editMarker.remove();
    this.editMarker=L.marker([this.customerEdit.latitude,this.customerEdit.longitude],{draggable:true,icon:this.mapIcon()}).addTo(this.editMap);
    this.editMarker.on('dragend',()=>{let p=this.editMarker.getLatLng();this.customerEdit.latitude=p.lat;this.customerEdit.longitude=p.lng;this.customerEdit.location_source='drag'});
    this.editMap.setView([this.customerEdit.latitude,this.customerEdit.longitude],16)
  },
  renderMainMap(){
    let el=document.getElementById('mainMap');if(!el)return;
    if(!this.mainMap){this.mainMap=L.map(el,{zoomControl:true}).setView([35.6892,51.389],10);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(this.mainMap)}
    this.mainMarkers.forEach(m=>m.remove());this.mainMarkers=[];let pts=[];
    for(let c of this.customers.filter(x=>x.latitude&&x.longitude)){let label=c.map_label||c.name,html=`<div dir="rtl"><b>${this.escapeHtml(label)}</b><br>${this.escapeHtml((c.phones||[]).join(' • '))}<br>${this.escapeHtml(c.address||'')}</div>`,m=L.marker([c.latitude,c.longitude],{icon:this.mapIcon()}).bindPopup(html).addTo(this.mainMap);this.mainMarkers.push(m);pts.push([c.latitude,c.longitude])}
    if(pts.length)this.mainMap.fitBounds(L.latLngBounds(pts),{padding:[50,50],maxZoom:15});
    setTimeout(()=>this.mainMap.invalidateSize(),80)
  },
  mapIcon(){return L.divIcon({className:'aq-map-marker',html:'<span aria-hidden="true"></span>',iconSize:[28,36],iconAnchor:[14,34],popupAnchor:[0,-30]})},
  escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))},
  async liveLocate(){try{let g=await this.locate();this.renderMainMap();if(this.userMarker)this.userMarker.remove();this.userMarker=L.circleMarker([g.lat,g.lng],{radius:9,color:'#fff',weight:3,fillColor:'#2563eb',fillOpacity:1}).bindPopup('<div dir="rtl"><b>موقعیت فعلی من</b></div>').addTo(this.mainMap);this.mainMap.setView([g.lat,g.lng],16)}catch{}},
  async loadNearby(){try{let g=await this.locate();this.nearby=await this.api(`/customers/nearby?lat=${g.lat}&lng=${g.lng}&radius=300`);await this.liveLocate()}catch(e){alert(e.message)}},
  haversine(a,b,c,d){let R=6371000,p=Math.PI/180,x=(c-a)*p,y=(d-b)*p,h=Math.sin(x/2)**2+Math.cos(a*p)*Math.cos(c*p)*Math.sin(y/2)**2;return 2*R*Math.asin(Math.sqrt(h))},
  offlineRoute(g){let left=this.customers.filter(c=>c.latitude&&c.longitude).slice(0,100),out=[],cur={latitude:g.lat,longitude:g.lng},distance=0;while(left.length&&out.length<12){let best=left.reduce((a,c)=>{let m=this.haversine(cur.latitude,cur.longitude,Number(c.latitude),Number(c.longitude));return!a||m<a.m?{c,m}:a},null);left=left.filter(c=>String(c.id)!==String(best.c.id));distance+=best.m;out.push({...best.c,distance_from_previous_m:Math.round(best.m)});cur=best.c}return{provider:'offline-haversine',distance_m:Math.round(distance),duration_s:0,geometry:{type:'LineString',coordinates:[[g.lng,g.lat],...out.map(c=>[Number(c.longitude),Number(c.latitude)])]},stops:out}},
  async loadRoutePlan(){try{let g=await this.locate(),d;if(!navigator.onLine){d=this.offlineRoute(g)}else{let near=await this.api(`/route/nearest?lat=${g.lat}&lng=${g.lng}&limit=12`);if(!near.length){this.routePlan=[];return alert('مشتری دارای GPS پیدا نشد')}d=await this.api('/route/optimize',{method:'POST',body:JSON.stringify({latitude:g.lat,longitude:g.lng,customer_ids:near.map(x=>x.id)})})}if(!d.stops?.length){this.routePlan=[];return alert('مشتری دارای GPS پیدا نشد')}this.routePlan=d.stops;this.routeMeta=d;await this.liveLocate();this.drawOptimizedRoute(d.geometry,g)}catch(e){alert(e.message)}},
  drawOptimizedRoute(geometry,start){if(!this.mainMap)return;let data=geometry||{type:'LineString',coordinates:[[start.lng,start.lat],...this.routePlan.map(x=>[x.longitude,x.latitude])]};if(this.routeLayer)this.routeLayer.remove();this.routeLayer=L.geoJSON({type:'Feature',properties:{},geometry:data},{style:{color:'#2563eb',weight:5,opacity:.82}}).addTo(this.mainMap)},
  openNavigation(r){window.open(`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(r.latitude+','+r.longitude)}&travelmode=driving`,'_blank','noopener')},
  showOnMap(c){this.page='map';setTimeout(()=>{this.renderMainMap();this.mainMap.setView([c.latitude,c.longitude],17)},120)},
  copyRoute(){let t=['🗺 مسیر بهینه پیشنهادی'];if(this.routeMeta.distance_m)t.push(`مسافت تقریبی: ${Math.round(this.routeMeta.distance_m/1000*10)/10} کیلومتر`);if(this.routeMeta.duration_s)t.push(`زمان تقریبی: ${Math.round(this.routeMeta.duration_s/60)} دقیقه`);this.routePlan.forEach((r,i)=>t.push(`${i+1}) ${r.map_label||r.name} — ${r.phone||''} — ${r.address||''}`));this.copyText(t.join('\n'))},

  async createExpense(){try{let f={...this.expenseForm,amount:this.num(this.expenseForm.amount)},d=await this.api('/expenses',{method:'POST',body:JSON.stringify(f)});this.expenseForm={category:'goods',title:'',amount:'',expense_date:'',notes:''};if(d?.queued){this.expenses.unshift({...f,id:d.id,expense_date:f.expense_date||new Date().toISOString(),offline_pending:true});alert('هزینه در صف همگام‌سازی ذخیره شد');return}await this.refreshAll();alert('هزینه ثبت شد')}catch(e){alert(e.message)}},
  async removeExpense(e){if(!confirm('این هزینه حذف شود؟'))return;await this.api('/expenses/'+e.id,{method:'DELETE'});await this.refreshAll()},
  async createSettlement(){try{let f={...this.settlementForm,amount:this.num(this.settlementForm.amount)},d=await this.api('/settlements',{method:'POST',body:JSON.stringify(f)});this.settlementForm={amount:'',settled_at:'',notes:''};if(d?.queued){this.settlements.unshift({...f,id:d.id,settled_at:f.settled_at||new Date().toISOString(),offline_pending:true});alert('تسویه در صف همگام‌سازی ذخیره شد');return}await this.refreshAll();this.renderCharts();alert('تسویه ثبت شد')}catch(e){alert(e.message)}},
  async saveFinanceSettings(){try{this.financeSettings=await this.api('/settings/finance',{method:'PATCH',body:JSON.stringify(this.financeSettings)});alert('تنظیمات ذخیره شد')}catch(e){alert(e.message)}},

  pushKeyBytes(value){let pad='='.repeat((4-value.length%4)%4),raw=atob((value+pad).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from(raw,c=>c.charCodeAt(0))},
  async refreshPushStatus(){this.pushPermission=window.Notification?.permission||'unsupported';if(!('serviceWorker'in navigator)||!('PushManager'in window)){this.pushActive=false;return}try{let reg=await navigator.serviceWorker.ready,sub=await reg.pushManager.getSubscription();this.pushActive=!!sub}catch{this.pushActive=false}},
  async enableAquaPush(){if(this.pushBusy)return;if(!('serviceWorker'in navigator)||!('PushManager'in window)||!window.Notification)return this.toast?.('Push روی این گوشی پشتیبانی نمی‌شود','error');this.pushBusy=true;try{let permission=await Notification.requestPermission();this.pushPermission=permission;if(permission!=='granted')throw Error('اجازه اعلان داده نشد');let key=await this.api('/push/public-key'),reg=await navigator.serviceWorker.ready,sub=await reg.pushManager.getSubscription();if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:this.pushKeyBytes(key.public_key)});await this.api('/push/subscribe',{method:'POST',body:JSON.stringify(sub.toJSON())});this.pushActive=true;this.toast?.('اعلان کارهای جدید روی این گوشی فعال شد','success')}catch(e){this.toast?.(e.message||'فعال‌سازی اعلان انجام نشد','error')}finally{this.pushBusy=false}},
  async disableAquaPush(){if(this.pushBusy)return;this.pushBusy=true;try{let reg=await navigator.serviceWorker.ready,sub=await reg.pushManager.getSubscription();if(sub){await this.api('/push/subscribe',{method:'DELETE',body:JSON.stringify({endpoint:sub.endpoint})});await sub.unsubscribe()}this.pushActive=false;this.toast?.('اعلان این گوشی غیرفعال شد','info')}catch(e){this.toast?.(e.message||'غیرفعال‌سازی اعلان انجام نشد','error')}finally{this.pushBusy=false}},

  renderCharts(){
    const colors={teal:'#2dd4bf',cyan:'#22d3ee',violet:'#8b5cf6',amber:'#f59e0b',rose:'#f43f5e',blue:'#38bdf8'},legend={position:'bottom',labels:{color:'#b8d5ec',font:{family:'Vazirmatn'}}};
    let months=this.jalaliMonthlyMetrics,labels=months.map(m=>m.label),c1=document.getElementById('monthlyChart');
    if(c1){if(this.monthlyChart)this.monthlyChart.destroy();this.monthlyChart=new Chart(c1,{type:'line',data:{labels,datasets:[{label:'دریافتی',data:months.map(m=>m.received),borderColor:colors.teal,backgroundColor:'#2dd4bf22',fill:true,tension:.35},{label:'سود خالص',data:months.map(m=>m.net_profit),borderColor:colors.violet,backgroundColor:'#8b5cf622',tension:.35},{label:'هزینه',data:months.map(m=>m.expenses),borderColor:colors.amber,backgroundColor:'#f59e0b22',tension:.35}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend}}})}
    let years=this.jalaliYearlyMetrics,cY=document.getElementById('yearlyChart');
    if(cY){if(this.yearlyChart)this.yearlyChart.destroy();this.yearlyChart=new Chart(cY,{type:'bar',data:{labels:years.map(y=>y.year),datasets:[{label:'دریافتی',data:years.map(y=>y.received),backgroundColor:colors.cyan,borderRadius:8},{label:'سود خالص',data:years.map(y=>y.net_profit),backgroundColor:colors.violet,borderRadius:8}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend}}})}
    let types=this.analytics.service_types||[],c2=document.getElementById('serviceChart');
    if(c2){if(this.serviceChart)this.serviceChart.destroy();this.serviceChart=new Chart(c2,{type:'bar',data:{labels:types.map(x=>x.service_type||'نامشخص'),datasets:[{label:'دریافتی',data:types.map(x=>x.received),backgroundColor:types.map((_,i)=>[colors.teal,colors.cyan,colors.violet,colors.amber,colors.rose,colors.blue][i%6]),borderRadius:8}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}})}
    let totals=this.analytics.totals||{},donut=document.getElementById('financeDonutChart');
    if(donut){if(this.financeDonutChart)this.financeDonutChart.destroy();this.financeDonutChart=new Chart(donut,{type:'doughnut',data:{labels:['سهم شرکت','هزینه‌ها','سود خالص'],datasets:[{data:[Math.max(Number(totals.company_share||0),0),Math.max(Number(totals.expenses||0),0),Math.max(Number(totals.net_profit||0),0)],backgroundColor:[colors.cyan,colors.amber,colors.violet],borderWidth:0,hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'66%',plugins:{legend}}})}
    let polar=document.getElementById('financePolarChart');
    if(polar){if(this.financePolarChart)this.financePolarChart.destroy();this.financePolarChart=new Chart(polar,{type:'polarArea',data:{labels:types.slice(0,6).map(x=>x.service_type||'نامشخص'),datasets:[{data:types.slice(0,6).map(x=>Number(x.received||0)),backgroundColor:['#2dd4bfaa','#22d3eeaa','#8b5cf6aa','#f59e0baa','#f43f5eaa','#38bdf8aa'],borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend}}})}
  },
  copyText(t){navigator.clipboard?.writeText(t).then(()=>alert('گزارش کپی شد')).catch(()=>prompt('متن گزارش:',t))},
  dayReportText(d){let lines=[`📅 ${this.persianDate(d.iso)}`];d.jobs.forEach((j,i)=>lines.push(`${i+1}) ${j.name} — ${j.description||j.service_type||'سرویس'} — ${this.money(j.received_amount)} تومان`));lines.push(`\nجمع دریافتی: ${this.money(d.received)} تومان`,`سهم شرکت: ${this.money(d.company_share)} تومان`,`هزینه‌ها: ${this.money(d.expenses)} تومان`,`مانده مشتری‌ها: ${this.money(d.customer_balance)} تومان`,`سود خالص من: ${this.money(d.net_profit)} تومان`);return lines.join('\n')},
  copyDay(d){this.copyText(this.dayReportText(d))},copyAllDaily(){this.copyText(this.dailyGroups.map(d=>this.dayReportText(d)).join('\n\n──────────\n\n'))},
  async downloadExcel(){try{let r=await fetch('/api/export.xlsx',{credentials:'same-origin'});if(!r.ok)throw Error('خروجی Excel ساخته نشد');let b=await r.blob(),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download='AquaGold.xlsx';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),2000)}catch(e){alert(e.message)}},
  printPdf(){window.print()},

  async captureSmartGps(){try{let g=await this.locate();this.smartGps={lat:g.lat,lng:g.lng,accuracy:g.accuracy};if(this.smartParsed)await this.loadSmartSuggestions()}catch{}},
  localSmartParse(raw){
    let tr={'۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9','٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9'},text=String(raw||'').replace(/[۰-۹٠-٩]/g,x=>tr[x]),lines=text.split(/\n+/).map(x=>x.trim().replace(/\s+/g,' ')).filter(Boolean),phonePattern=/(?:\+98|0098|98|0)?9\d{9}/g,phones=[...new Set((text.match(phonePattern)||[]).map(x=>{let d=x.replace(/\D/g,'');return d.startsWith('0098')?'0'+d.slice(4):d.startsWith('98')?'0'+d.slice(2):d.length===10?'0'+d:d}))],services=['فیلتر','یخچال','تصفیه','دستگاه','سرویس','نصب','تعویض','تعمیر'],addresses=['خیابان','خ ','کوچه','کوی','شهرک','بلوار','میدان','پلاک','پ ','واحد','طبقه','آریا','صادقیه','تهران','کرج','ولنجک','کاشانی'],times=['شنبه','یکشنبه','دوشنبه','سه شنبه','سه‌شنبه','چهارشنبه','پنجشنبه','جمعه','الی','ساعت'],service=lines.find(x=>services.some(w=>x.includes(w))&&!/(?:\+98|0098|98|0)?9\d{9}/.test(x))||null,time=lines.find(x=>times.some(w=>x.includes(w)))||null,m=text.match(/(?:دریافتی|مبلغ|گرفتم|پرداخت)\s*[:：]?\s*([\d/.,٬،\s]{3,})/i),amount=m?Number(m[1].replace(/\D/g,''))||null:null,last=null;
    for(let line of lines){let s=line.replace(/(?:\+98|0098|98|0)?9\d{9}/g,'').trim();if(s&&line!==service&&line!==time&&!addresses.some(w=>line.includes(w))&&s.split(' ').length<=3&&/^[آ-ی‌\- ]+$/.test(s)){last=s;break}}
    let address=lines.filter(x=>addresses.some(w=>x.includes(w))).join(' ')||null;
    return{last_name:last,phones,address,service_type:service,description:service,time_text:time,amount,raw_text:raw,parser:'local-offline'}
  },
  async analyzeSmart(){if(!this.smartText.trim())return alert('متن را وارد کن');try{this.smartParsed=navigator.onLine?await this.api('/smart/parse',{method:'POST',body:JSON.stringify({text:this.smartText})}):this.localSmartParse(this.smartText);this.smartCustomerId='';if(navigator.onLine)await this.loadSmartSuggestions();else this.smartSuggestions=[]}catch{this.smartParsed=this.localSmartParse(this.smartText);this.smartCustomerId='';this.smartSuggestions=[]}},
  async loadSmartSuggestions(){let p=this.smartParsed||{},qs=new URLSearchParams();if(p.last_name)qs.set('surname',p.last_name);if((p.phones||[])[0])qs.set('phone',p.phones[0]);if(this.smartGps.lat){qs.set('lat',this.smartGps.lat);qs.set('lng',this.smartGps.lng)}this.smartSuggestions=await this.api('/customers/suggest?'+qs.toString())},
  async registerSmart(){try{let p=this.smartParsed||{},d=await this.api('/smart/register',{method:'POST',body:JSON.stringify({text:this.smartText,parsed:p,customer_id:this.smartCustomerId||null,latitude:this.smartGps.lat,longitude:this.smartGps.lng,accuracy:this.smartGps.accuracy})});this.smartText='';this.smartParsed=null;this.smartSuggestions=[];this.smartCustomerId='';if(d?.queued){alert('ثبت هوشمند در صف همگام‌سازی ذخیره شد');this.page='dashboard';return}await this.refreshAll();alert('ثبت هوشمند انجام شد');let c=this.customers.find(x=>String(x.id)===String(d.customer_id));if(c)this.openCustomer(c)}catch(e){alert(e.message)}}
}}
