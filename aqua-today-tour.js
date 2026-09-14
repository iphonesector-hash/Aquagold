/* Today Tour: active Bale new/review jobs on the existing AquaGold Leaflet map. */
(()=>{
  const previous=window.app;if(typeof previous!=='function')return;
  window.app=function(){
    const state=previous();
    Object.assign(state,{todayTourPlan:null,todayTourBusy:false,todayTourMarkers:[],todayTourLayer:null});

    state.clearTodayTourMap=function(){
      for(const marker of this.todayTourMarkers||[]){try{marker.remove()}catch{}}
      this.todayTourMarkers=[];
      if(this.todayTourLayer){try{this.todayTourLayer.remove()}catch{}this.todayTourLayer=null}
    };

    state.renderTodayTourMap=function(){
      const plan=this.todayTourPlan;if(!plan)return;
      this.page='map';
      setTimeout(()=>{
        try{this.renderMainMap?.()}catch{}
        if(!this.mainMap||typeof L==='undefined')return;
        this.clearTodayTourMap();
        const bounds=[];
        for(const job of plan.jobs||[]){
          const loc=job?.location||{};
          const lat=Number(loc.latitude),lng=Number(loc.longitude);
          if(!Number.isFinite(lat)||!Number.isFinite(lng))continue;
          const badge=loc.quality==='exact'?'دقیق':loc.quality==='approximate'?'تقریبی':'نامشخص';
          const icon=L.divIcon({className:'aq-tour-marker',html:`<span>${Number(job.order||0).toLocaleString('fa-IR')}</span>`,iconSize:[38,38],iconAnchor:[19,19]});
          const marker=L.marker([lat,lng],{icon}).addTo(this.mainMap);
          const name=this.escapeHtml?.(job.customer_name||job.phone||'کار بله')||'کار بله';
          const address=this.escapeHtml?.(job.address||loc.formatted_address||'')||'';
          marker.bindPopup(`<div dir="rtl"><b>${name}</b><br>${address}<br><small>${badge} • ${job.schedule?.label||''}</small></div>`);
          this.todayTourMarkers.push(marker);bounds.push([lat,lng]);
        }
        const geometry=plan.route?.geometry;
        if(geometry?.coordinates?.length){
          try{this.todayTourLayer=L.geoJSON(geometry,{style:{weight:5,opacity:.82}}).addTo(this.mainMap)}catch{}
        }
        if(bounds.length){try{this.mainMap.fitBounds(bounds,{padding:[32,32],maxZoom:15})}catch{}}
        this.renderTodayTourCard?.();
      },160);
    };

    state.loadTodayTour=async function(){
      if(this.todayTourBusy)return;
      if(!navigator.geolocation)return alert('موقعیت مکانی روی این دستگاه در دسترس نیست');
      this.todayTourBusy=true;
      try{
        const position=await new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:10000,maximumAge:15000}));
        const lat=position.coords.latitude,lng=position.coords.longitude;
        this.todayTourPlan=await this.api(`/map/today-tour/plan?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`);
        if(!(this.todayTourPlan?.jobs||[]).length){alert('برای امروز کار فعال new/review پیدا نشد');return}
        this.renderTodayTourMap();
      }catch(error){alert(error?.message||'ساخت تور امروز انجام نشد')}
      finally{this.todayTourBusy=false}
    };

    state.navigateTodayTourStop=function(job){
      const loc=job?.location||{};
      if(!Number.isFinite(Number(loc.latitude))||!Number.isFinite(Number(loc.longitude)))return alert('این کار هنوز موقعیت قابل مسیریابی ندارد');
      if(typeof this.openNavigation==='function')return this.openNavigation({latitude:Number(loc.latitude),longitude:Number(loc.longitude),name:job.customer_name||job.phone||'مقصد'});
      window.open(`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(loc.latitude+','+loc.longitude)}`,'_blank','noopener');
    };

    state.renderTodayTourCard=function(){
      let card=document.getElementById('aquaTodayTourCard');
      if(!card){
        const map=document.getElementById('mainMap')?.parentElement;if(!map)return;
        card=document.createElement('section');card.id='aquaTodayTourCard';card.className='card p-4 mt-3';
        map.insertAdjacentElement('afterend',card);
      }
      card.replaceChildren();
      const title=document.createElement('div');title.className='flex items-center justify-between gap-3';
      const heading=document.createElement('b');heading.textContent='تور امروز';title.appendChild(heading);
      const refresh=document.createElement('button');refresh.type='button';refresh.className='btn soft !py-2';refresh.textContent='به‌روزرسانی';refresh.addEventListener('click',()=>this.loadTodayTour());title.appendChild(refresh);card.appendChild(title);
      const summary=this.todayTourPlan?.summary||{};
      const meta=document.createElement('div');meta.className='text-sm muted mt-2';meta.textContent=`${Number(summary.jobs||0).toLocaleString('fa-IR')} کار • دقیق ${Number(summary.exact||0).toLocaleString('fa-IR')} • تقریبی ${Number(summary.approximate||0).toLocaleString('fa-IR')} • بدون موقعیت ${Number(summary.unresolved||0).toLocaleString('fa-IR')}`;card.appendChild(meta);
      for(const job of this.todayTourPlan?.jobs||[]){
        const row=document.createElement('div');row.className='glass rounded-2xl p-3 mt-3';
        const label=document.createElement('b');label.textContent=`${Number(job.order||0).toLocaleString('fa-IR')}. ${job.customer_name||job.phone||'کار بله'}`;row.appendChild(label);
        const detail=document.createElement('div');detail.className='text-sm muted mt-1';detail.textContent=`${job.schedule?.label||'امروز'} • ${job.status==='review'?'نیازمند بررسی':'جدید'}${job.address?' • '+job.address:''}`;row.appendChild(detail);
        const nav=document.createElement('button');nav.type='button';nav.className='btn primary !py-2 mt-2';nav.textContent='مسیریابی';nav.disabled=!job.location?.latitude;nav.addEventListener('click',()=>this.navigateTodayTourStop(job));row.appendChild(nav);
        card.appendChild(row);
      }
    };

    const oldInit=state.init;
    state.init=async function(){
      await oldInit?.call(this);
      setTimeout(()=>{
        const map=document.getElementById('mainMap')?.parentElement;if(!map||document.getElementById('aquaTodayTourLaunch'))return;
        const launch=document.createElement('button');launch.id='aquaTodayTourLaunch';launch.type='button';launch.className='btn primary w-full mt-3';launch.textContent='ساخت تور امروز از کارهای بله';launch.addEventListener('click',()=>this.loadTodayTour());map.insertAdjacentElement('afterend',launch);
      },0);
    };
    return state;
  };
})();
