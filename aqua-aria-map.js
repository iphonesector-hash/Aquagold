/* Aria address commands are dispatched into the same Smart Tour destination/navigation flow used by the map UI. */
(()=>{
  const previous=window.app;if(typeof previous!=='function')return;
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const textOf=v=>String(v||'').replace(/\s+/g,' ').trim();
  const folded=v=>textOf(v).replace(/[يى]/g,'ی').replace(/ك/g,'ک').replace(/[۰-۹]/g,d=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d)).toLowerCase();
  const addressCue=/(?:خیابان|خیابون|کوچه|بلوار|میدان|بزرگراه|اتوبان|محله|پلاک|بن[‌ ]?بست|مرزداران|صادقیه|آریاشهر|پونک|ستارخان|یوسف[‌ ]?آباد|سعادت[‌ ]?آباد|تهرانسر|فردیس|کرج|تهران)/;
  const mapVerb=/(?:روی نقشه|رو نقشه|نشون بده|نشان بده|پیدا کن|بازش کن|باز کن)/;
  const mapOnly=/^(?:(?:لطفا|لطفاً|آریا)\s*)?(?:(?:همون|همونو|همین|اون|اونو|این|اینو)\s*)?(?:رو|را)?\s*(?:روی\s*)?نقشه(?:\s*(?:بهم|برام|برای من))?\s*(?:نشون بده|نشان بده|باز کن)?[.!؟?]*$/;
  const cleanAddress=v=>textOf(v)
    .replace(/^(?:گفتم|آدرس(?:م|ش)?(?:\s+(?:اینه|این هست))?|مقصد(?:م)?(?:\s+(?:اینه|این هست))?|لطفا|لطفاً|آریا)\s*[:،,-]?\s*/,'')
    .replace(/\s*(?:رو|را)?\s*(?:روی\s*)?نقشه(?:\s*(?:بهم|برام|برای من))?\s*(?:نشون بده|نشان بده|باز کن)?\s*$/,'')
    .replace(/\s*(?:نشون بده|نشان بده|پیدا کن)\s*$/,'')
    .trim();
  const looksLikeAddress=v=>{const q=cleanAddress(v);return q.split(' ').length>=2&&addressCue.test(folded(q))};

  /* Keep the exact AquaGold startup artwork intact on tall iPhones. Older layers
     keep rewriting the same image with different cache-busters and object-fit:cover,
     which crops the 9:16 artwork on modern Safari viewports. */
  const loaderUrl='/assets/aquagold-loading-v20260906b.jpg?aqua-loader-fixed-20260914';
  const fixBootArtwork=()=>{
    const image=document.querySelector('#aqua-boot-20260906 img');
    if(image){
      if(image.getAttribute('src')!==loaderUrl)image.setAttribute('src',loaderUrl);
      image.style.objectFit='contain';
      image.style.objectPosition='center center';
      image.style.background='#010817';
    }
    document.querySelectorAll('link[rel="preload"][as="image"],link[rel="apple-touch-startup-image"]').forEach(link=>{
      if(/aquagold-loading-v(?:64|20260906|20260906b)\.jpg/.test(link.getAttribute('href')||''))link.setAttribute('href',loaderUrl);
    });
  };
  fixBootArtwork();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fixBootArtwork,{once:true});
  [0,40,120,300].forEach(ms=>setTimeout(fixBootArtwork,ms));

  window.app=function(){
    const state=previous(),baseAction=state.runAquaAction,baseSubmit=state.submitAquaText,baseOpenNavigation=state.openNavigation;
    Object.assign(state,{ariaLocation:null,ariaPendingAddress:'',ariaSearchMarker:null,ariaNearbyMarkers:[],ariaMapRequest:0});

    state.waitForAriaMapRuntime=async function(){
      for(let i=0;i<18;i++){
        if(window.AquaMapBridge?.selectDestination||document.getElementById('aqst-map-place-q'))return true;
        await sleep(90);
      }
      return false;
    };

    state.resolveAriaAddress=async function(value){
      const query=cleanAddress(value);if(!looksLikeAddress(query))return null;
      let lat=Number(this.gps?.lat),lng=Number(this.gps?.lng);
      try{const c=this.mainMap?.getCenter?.();if(c){lat=Number(c.lat);lng=Number(c.lng)}}catch{}
      if(!Number.isFinite(lat)||!Number.isFinite(lng)){lat=35.6892;lng=51.3890}
      try{
        const data=await this.api(`/map/smart-tour/place-search?q=${encodeURIComponent(query)}&lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`),items=Array.isArray(data?.items)?data.items:[];
        if(!items.length)return null;
        const wanted=folded(query),tokens=wanted.split(' ').filter(x=>x.length>1);
        const ranked=items.map((item,index)=>{
          const got=folded(`${item.title||''} ${item.address||item.region||''}`);let score=0;
          for(const token of tokens)if(got.includes(token))score+=token.length>3?2:1;
          return{item,index,score};
        }).sort((a,b)=>b.score-a.score||a.index-b.index);
        const item=ranked[0].item,latitude=Number(item.latitude),longitude=Number(item.longitude);
        if(!Number.isFinite(latitude)||!Number.isFinite(longitude))return null;
        return{...item,kind:'address',name:item.title||query,title:item.title||query,address:item.address||item.region||query,formatted_address:item.address||item.region||query,latitude,longitude,lat:latitude,lng:longitude,source:item.source||'neshan-place-search'};
      }catch(e){console.warn('Aria direct address lookup failed',e);return null}
    };

    state.recentAriaAddressText=function(){
      if(this.ariaPendingAddress)return this.ariaPendingAddress;
      const messages=[...(this.aquaMessages||[])].reverse();
      for(const message of messages){
        if(message?.role!=='user')continue;
        const candidate=cleanAddress(message.content);
        if(looksLikeAddress(candidate))return candidate;
      }
      return '';
    };

    state.rememberAriaAddress=async function(value,source='text'){
      const raw=String(value||'').trim(),query=cleanAddress(raw);if(!query)return false;
      this.stopAquaSpeech?.();this.aquaMessages.push({role:'user',content:raw});this.aquaInput='';this.aquaBusy=true;this.aquaScroll?.();
      try{
        const location=await this.resolveAriaAddress(query);
        if(!location){
          const content='آدرس رو گرفتم، ولی روی نشان نتیجه مطمئنی پیدا نکردم. اسم محله یا خیابون اصلی رو هم بگو.';
          this.aquaMessages.push({role:'assistant',content,error:true});this.aquaScroll?.();setTimeout(()=>this.speakAqua?.(content),20);return true;
        }
        this.ariaPendingAddress=query;this.ariaLocation=location;
        const content=`گرفتم؛ ${location.formatted_address||query}. اگر بگی «روی نقشه نشون بده» همین مقصد رو باز می‌کنم.`;
        this.aquaMessages.push({role:'assistant',content});this.aquaScroll?.();setTimeout(()=>this.speakAqua?.(content),20);return true;
      }finally{this.aquaBusy=false;this.aquaScroll?.()}
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
      input.value=query;input.dispatchEvent(new Event('input',{bubbles:true}));go.click();
      let buttons=[];
      for(let i=0;i<24;i++){await sleep(100);buttons=[...document.querySelectorAll('#aqst-free-results .aqst-free-result')];if(buttons.length)break}
      if(!buttons.length)return false;
      const wanted=folded(`${location.title||location.name||''} ${location.formatted_address||location.address||''}`);
      const best=buttons.map(button=>{const got=folded(button.textContent);let score=0;for(const token of wanted.split(' ').filter(x=>x.length>2))if(got.includes(token))score++;return{button,score}}).sort((a,b)=>b.score-a.score)[0]?.button||buttons[0];
      best.click();
      for(let i=0;i<12;i++){await sleep(70);if(document.querySelector('#aqst-free-card .aqst-free-start'))return true}
      return false;
    };

    state.showAriaAddress=async function(location){
      const lat=Number(location?.latitude??location?.lat),lng=Number(location?.longitude??location?.lng);
      if(!Number.isFinite(lat)||!Number.isFinite(lng))return false;
      this.ariaLocation={...location,latitude:lat,longitude:lng,lat,lng};this.ariaPendingAddress=cleanAddress(location.formatted_address||location.address||location.title||location.name||this.ariaPendingAddress);
      this.page='map';const requestId=++this.ariaMapRequest;
      await sleep(90);if(requestId!==this.ariaMapRequest)return false;
      try{this.renderMainMap?.()}catch{}
      await sleep(120);if(requestId!==this.ariaMapRequest)return false;
      const synced=await this.syncAriaDestination(this.ariaLocation);
      if(requestId!==this.ariaMapRequest)return false;
      if(synced){try{this.mainMap?.invalidateSize?.()}catch{}return true}
      try{
        if(this.ariaSearchMarker)this.ariaSearchMarker.remove();
        const icon=L.divIcon({className:'aq-aria-marker',html:'<span aria-hidden="true">◆</span>',iconSize:[38,42],iconAnchor:[19,38]});
        this.ariaSearchMarker=L.marker([lat,lng],{icon}).addTo(this.mainMap);
        this.ariaSearchMarker.bindPopup(`<div dir="rtl"><b>${this.escapeHtml(location.title||location.name||'نتیجه آدرس')}</b><br>${this.escapeHtml(location.formatted_address||location.address||'')}</div>`).openPopup();
        this.mainMap.setView([lat,lng],17);this.mainMap.invalidateSize();return true;
      }catch(e){console.warn('Aria map fallback failed',e);return false}
    };

    state.navigateInternal=async function(location){
      const lat=Number(location?.latitude??location?.lat),lng=Number(location?.longitude??location?.lng);
      if(!Number.isFinite(lat)||!Number.isFinite(lng))return false;
      const target={...location,latitude:lat,longitude:lng,lat,lng};this.ariaLocation=target;this.page='map';
      await sleep(80);try{this.renderMainMap?.()}catch{}
      const bridge=window.AquaMapBridge;
      if(bridge?.startNavigation){try{await bridge.startNavigation(target);return true}catch(e){console.warn('AquaMapBridge navigation failed',e)}}
      let start=document.querySelector('#aqst-free-card .aqst-free-start');
      if(!start){await this.syncAriaDestination(target);start=document.querySelector('#aqst-free-card .aqst-free-start')}
      if(start){start.click();return true}
      return false;
    };

    state.openNavigation=async function(location){if(await this.navigateInternal(location))return true;return baseOpenNavigation?.call(this,location)};

    state.submitAquaText=async function(value,source='text'){
      const text=String(value||'').trim(),candidate=cleanAddress(text);
      if(!text)return false;

      if(looksLikeAddress(candidate)&&!mapVerb.test(folded(text))){
        return this.rememberAriaAddress(text,source);
      }

      if(mapOnly.test(folded(text))){
        this.aquaMessages.push({role:'user',content:text});this.aquaInput='';
        let location=this.ariaLocation;
        if(!location){const recent=this.recentAriaAddressText();if(recent)location=await this.resolveAriaAddress(recent)}
        if(!location){this.aquaMessages.push({role:'assistant',content:'آدرس قبلی رو پیدا نکردم. آدرس رو بگو؛ مثلاً «مرزداران، خیابان گلستان ۱۵».'});this.aquaScroll?.();return true}
        this.ariaLocation=location;const shown=await this.showAriaAddress(location);
        this.aquaMessages.push({role:'assistant',content:shown?'پیداش کردم؛ روی نقشه بازش کردم.':'مقصد رو پیدا کردم ولی نقشه آماده نشد؛ یک‌بار بخش نقشه رو باز کن.'});this.aquaScroll?.();return true;
      }

      if(looksLikeAddress(candidate)&&mapVerb.test(folded(text))){
        this.aquaMessages.push({role:'user',content:text});this.aquaInput='';
        const location=await this.resolveAriaAddress(candidate);
        if(!location){this.aquaMessages.push({role:'assistant',content:'این آدرس رو دقیق پیدا نکردم. اسم محله یا خیابون اصلی رو هم بگو.'});this.aquaScroll?.();return true}
        this.ariaLocation=location;this.ariaPendingAddress=candidate;await this.showAriaAddress(location);this.aquaMessages.push({role:'assistant',content:'پیداش کردم؛ روی نقشه نشونت دادم.'});this.aquaScroll?.();return true;
      }

      if(/(?:مشتری.{0,14}(?:اطرافش|اونجا|همین آدرس|این آدرس|این نقطه)|اطرافش|مشتری(?:‌| )های اطراف)/.test(text)){
        if(!this.ariaLocation){const recent=this.recentAriaAddressText();if(recent)this.ariaLocation=await this.resolveAriaAddress(recent)}
        if(this.ariaLocation){this.aquaMessages.push({role:'user',content:text});this.aquaInput='';const ok=await this.ariaNearby();if(ok)this.aquaMessages.push({role:'assistant',content:this.nearby.length?`${this.nearby.length.toLocaleString('fa-IR')} مشتری تا شعاع دو کیلومتری پیدا شد و روی نقشه نمایش داده شد.`:'در شعاع دو کیلومتری مشتری دارای موقعیت پیدا نشد.'});this.aquaScroll();return ok}
      }

      const navFollowup=/^(?:مسیریابی(?: کن)?|شروع(?: کن)? مسیر|مسیر(?: رو|ش رو|ش)?(?: شروع کن| شروع| بزن)?|حرکت کن|راه بیفت)$/;
      const navContext=/(?:ببر(?:م|مون)?|مسیر|مسیریابی).*(?:اونجا|همونجا|همین مقصد|این مقصد)/;
      if(navFollowup.test(text)||navContext.test(text)){
        if(!this.ariaLocation){const recent=this.recentAriaAddressText();if(recent)this.ariaLocation=await this.resolveAriaAddress(recent)}
        if(this.ariaLocation){this.aquaMessages.push({role:'user',content:text});this.aquaInput='';const started=await this.navigateInternal(this.ariaLocation);if(!started)this.aquaMessages.push({role:'assistant',content:'مقصد رو دارم، ولی مسیریابی داخلی نقشه آماده نشد. یک‌بار صفحه نقشه رو باز کن و دوباره بگو مسیر رو شروع کن.',error:true});this.aquaScroll();return started}
      }

      const before=this.aquaMessages?.length||0;
      const sent=await baseSubmit.call(this,value,source);if(!sent)return sent;
      const added=(this.aquaMessages||[]).slice(before),message=[...added].reverse().find(m=>m?.role==='assistant'&&m?.action);
      if(message?.action&&!message.__aquaMapDispatched){message.__aquaMapDispatched=true;try{await Promise.resolve(this.runAquaAction(message.action))}catch(e){console.warn('Aria action dispatch failed',e)}}
      return sent;
    };

    state.runAquaAction=function(action){
      if(action?.type==='show_address_on_map')return this.showAriaAddress(action.location);
      if(action?.customer?.kind==='address')return this.showAriaAddress(action.customer);
      return baseAction?.call(this,action);
    };

    state.ariaNavigate=async function(){return this.ariaLocation?this.navigateInternal(this.ariaLocation):false};

    state.ariaNearby=async function(){
      if(!this.ariaLocation){alert('اول یک مقصد را روی نقشه انتخاب کن');return false}
      try{
        const p=this.ariaLocation;this.nearby=await this.api(`/customers/nearby?lat=${encodeURIComponent(p.latitude)}&lng=${encodeURIComponent(p.longitude)}&radius=2000`);
        this.ariaNearbyMarkers.forEach(m=>m.remove());this.ariaNearbyMarkers=[];
        for(const c of this.nearby){if(!c.latitude||!c.longitude)continue;this.ariaNearbyMarkers.push(L.marker([c.latitude,c.longitude],{icon:this.mapIcon()}).bindPopup(`<div dir="rtl"><b>${this.escapeHtml(c.map_label||c.name||'مشتری')}</b></div>`).addTo(this.mainMap))}
        return true;
      }catch(e){alert(e.message||'نمایش مشتری‌های اطراف انجام نشد');return false}
    };

    return state;
  };
})();
