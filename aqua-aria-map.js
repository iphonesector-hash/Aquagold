/* Aria address commands are dispatched into the same Smart Tour destination/navigation flow used by the map UI. */
(()=>{
  const previous=window.app;if(typeof previous!=='function')return;
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const textOf=v=>String(v||'').replace(/\s+/g,' ').trim();
  const folded=v=>textOf(v).replace(/[يى]/g,'ی').replace(/ك/g,'ک').toLowerCase();
  window.app=function(){
    const state=previous(),baseAction=state.runAquaAction,baseSubmit=state.submitAquaText;
    Object.assign(state,{ariaLocation:null,ariaSearchMarker:null,ariaNearbyMarkers:[],ariaMapRequest:0});

    state.waitForAriaMapRuntime=async function(){
      for(let i=0;i<18;i++){
        if(window.AquaMapBridge?.selectDestination||document.getElementById('aqst-map-place-q'))return true;
        await sleep(90);
      }
      return false;
    };

    state.syncAriaDestination=async function(location){
      if(!location)return false;
      const bridge=window.AquaMapBridge;
      if(bridge?.selectDestination){
        try{await bridge.selectDestination(location);return true}catch(e){console.warn('AquaMapBridge select failed',e)}
      }
      await this.waitForAriaMapRuntime();
      const input=document.getElementById('aqst-map-place-q'),go=document.getElementById('aqst-map-place-go');
      if(!input||!go)return false;
      const query=textOf(location.formatted_address||location.address||location.title||location.name);
      if(!query)return false;
      input.value=query;
      input.dispatchEvent(new Event('input',{bubbles:true}));
      go.click();
      let buttons=[];
      for(let i=0;i<24;i++){
        await sleep(100);
        buttons=[...document.querySelectorAll('#aqst-free-results .aqst-free-result')];
        if(buttons.length)break;
      }
      if(!buttons.length)return false;
      const wanted=folded(`${location.title||location.name||''} ${location.formatted_address||location.address||''}`);
      const best=buttons.map(button=>{
        const got=folded(button.textContent);
        let score=0;
        for(const token of wanted.split(' ').filter(x=>x.length>2))if(got.includes(token))score++;
        return{button,score};
      }).sort((a,b)=>b.score-a.score)[0]?.button||buttons[0];
      best.click();
      for(let i=0;i<12;i++){
        await sleep(70);
        if(document.querySelector('#aqst-free-card .aqst-free-start'))return true;
      }
      return false;
    };

    state.showAriaAddress=async function(location){
      const lat=Number(location?.latitude??location?.lat),lng=Number(location?.longitude??location?.lng);
      if(!Number.isFinite(lat)||!Number.isFinite(lng))return false;
      this.ariaLocation={...location,latitude:lat,longitude:lng,lat,lng};
      this.page='map';const requestId=++this.ariaMapRequest;
      await sleep(90);if(requestId!==this.ariaMapRequest)return false;
      try{this.renderMainMap?.()}catch{}
      await sleep(120);if(requestId!==this.ariaMapRequest)return false;
      const synced=await this.syncAriaDestination(this.ariaLocation);
      if(requestId!==this.ariaMapRequest)return false;
      if(synced){
        try{this.mainMap?.invalidateSize?.()}catch{}
        return true;
      }
      try{
        if(this.ariaSearchMarker)this.ariaSearchMarker.remove();
        const icon=L.divIcon({className:'aq-aria-marker',html:'<span aria-hidden="true">◆</span>',iconSize:[38,42],iconAnchor:[19,38]});
        this.ariaSearchMarker=L.marker([lat,lng],{icon}).addTo(this.mainMap);
        this.ariaSearchMarker.bindPopup(`<div dir="rtl"><b>${this.escapeHtml(location.title||location.name||'نتیجه آدرس')}</b><br>${this.escapeHtml(location.formatted_address||location.address||'')}</div>`).openPopup();
        this.mainMap.setView([lat,lng],17);this.mainMap.invalidateSize();
        return true;
      }catch(e){console.warn('Aria map fallback failed',e);return false}
    };

    state.submitAquaText=async function(value,source='text'){
      const text=String(value||'').trim();
      if(this.ariaLocation&&/(?:مشتری.{0,14}(?:اطرافش|اونجا|همین آدرس|این آدرس|این نقطه)|اطرافش|مشتری(?:‌| )های اطراف)/.test(text)){
        this.aquaMessages.push({role:'user',content:text});this.aquaInput='';await this.ariaNearby();
        this.aquaMessages.push({role:'assistant',content:this.nearby.length?`${this.nearby.length.toLocaleString('fa-IR')} مشتری تا شعاع دو کیلومتری پیدا شد و روی نقشه نمایش داده شد.`:'در شعاع دو کیلومتری مشتری دارای موقعیت پیدا نشد.'});this.aquaScroll();return true;
      }
      if(this.ariaLocation&&/(?:مسیریابی|شروع(?: کن)? مسیر|مسیر(?:ش|ش رو| رو)?(?: شروع| بزن| باز| برو)?|ببر(?:م|مون)?(?: اونجا| به)|حرکت کن|راه بیفت)/.test(text)){
        this.aquaMessages.push({role:'user',content:text});this.aquaInput='';
        const started=await this.ariaNavigate();
        if(!started)this.aquaMessages.push({role:'assistant',content:'مقصد رو دارم، ولی مسیریابی داخلی نقشه آماده نشد. یک‌بار صفحه نقشه رو باز کن و دوباره بگو مسیر رو شروع کن.',error:true});
        this.aquaScroll();return started;
      }
      const before=this.aquaMessages?.length||0;
      const sent=await baseSubmit.call(this,value,source);
      if(!sent)return sent;
      const added=(this.aquaMessages||[]).slice(before);
      const message=[...added].reverse().find(m=>m?.role==='assistant'&&m?.action);
      if(message?.action&&!message.__aquaMapDispatched){
        message.__aquaMapDispatched=true;
        try{await Promise.resolve(this.runAquaAction(message.action))}catch(e){console.warn('Aria action dispatch failed',e)}
      }
      return sent;
    };

    state.runAquaAction=function(action){
      if(action?.type==='show_address_on_map')return this.showAriaAddress(action.location);
      if(action?.customer?.kind==='address')return this.showAriaAddress(action.customer);
      return baseAction?.call(this,action);
    };

    state.ariaNavigate=async function(){
      if(!this.ariaLocation)return false;
      const bridge=window.AquaMapBridge;
      if(bridge?.startNavigation){
        try{await bridge.startNavigation(this.ariaLocation);return true}catch(e){console.warn('AquaMapBridge navigation failed',e)}
      }
      let start=document.querySelector('#aqst-free-card .aqst-free-start');
      if(!start){await this.syncAriaDestination(this.ariaLocation);start=document.querySelector('#aqst-free-card .aqst-free-start')}
      if(start){start.click();return true}
      if(typeof this.openNavigation==='function'){try{this.openNavigation(this.ariaLocation);return true}catch{}}
      return false;
    };

    state.ariaNearby=async function(){
      if(!this.ariaLocation)return alert('اول یک مقصد را روی نقشه انتخاب کن');
      try{
        const p=this.ariaLocation;this.nearby=await this.api(`/customers/nearby?lat=${encodeURIComponent(p.latitude)}&lng=${encodeURIComponent(p.longitude)}&radius=2000`);
        this.ariaNearbyMarkers.forEach(m=>m.remove());this.ariaNearbyMarkers=[];
        for(const c of this.nearby){if(!c.latitude||!c.longitude)continue;this.ariaNearbyMarkers.push(L.marker([c.latitude,c.longitude],{icon:this.mapIcon()}).bindPopup(`<div dir="rtl"><b>${this.escapeHtml(c.map_label||c.name||'مشتری')}</b></div>`).addTo(this.mainMap))}
      }catch(e){alert(e.message||'نمایش مشتری‌های اطراف انجام نشد')}
    };

    return state;
  };
})();
