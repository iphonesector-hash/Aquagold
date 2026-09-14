/* Aria address results reuse the existing Leaflet map, nearby endpoint and navigation. */
(()=>{
  const previous=window.app;if(typeof previous!=='function')return;
  window.app=function(){const state=previous(),baseAction=state.runAquaAction,baseSubmit=state.submitAquaText;
    Object.assign(state,{ariaLocation:null,ariaSearchMarker:null,ariaNearbyMarkers:[],ariaMapRequest:0});
    state.showAriaAddress=function(location){
      if(!location||!Number.isFinite(Number(location.latitude))||!Number.isFinite(Number(location.longitude)))return;
      this.ariaLocation={...location};this.page='map';const requestId=++this.ariaMapRequest;
      setTimeout(()=>{if(requestId!==this.ariaMapRequest)return;this.renderMainMap();
        if(this.ariaSearchMarker)this.ariaSearchMarker.remove();
        const icon=L.divIcon({className:'aq-aria-marker',html:'<span aria-hidden="true">◆</span>',iconSize:[38,42],iconAnchor:[19,38]});
        this.ariaSearchMarker=L.marker([location.latitude,location.longitude],{icon}).addTo(this.mainMap);
        this.ariaSearchMarker.bindPopup(`<div dir="rtl"><b>${this.escapeHtml(location.title||location.name||'نتیجه آدرس')}</b><br>${this.escapeHtml(location.formatted_address||location.address||'')}</div>`).openPopup();
        this.mainMap.setView([location.latitude,location.longitude],17);this.mainMap.invalidateSize();
        this.aquaMessages?.push({role:'assistant',content:'پیداش کردم. روی نقشه نشونت دادم.'});this.aquaScroll?.();
      },140);
    };
    state.submitAquaText=async function(value,source='text'){
      const text=String(value||'').trim();
      if(this.ariaLocation&&/(?:مشتری.{0,12}(?:اطرافش|اونجا|همین آدرس|این نقطه)|اطرافش)/.test(text)){
        this.aquaMessages.push({role:'user',content:text});this.aquaInput='';await this.ariaNearby();
        this.aquaMessages.push({role:'assistant',content:this.nearby.length?`${this.nearby.length.toLocaleString('fa-IR')} مشتری تا شعاع دو کیلومتری پیدا شد و روی نقشه نمایش داده شد.`:'در شعاع دو کیلومتری مشتری دارای موقعیت پیدا نشد.'});this.aquaScroll();return true;
      }
      return baseSubmit.call(this,value,source);
    };
    state.runAquaAction=function(action){
      if(action?.type==='show_address_on_map')return this.showAriaAddress(action.location);
      if(action?.customer?.kind==='address')return this.showAriaAddress(action.customer);
      return baseAction?.call(this,action);
    };
    state.ariaNavigate=function(){if(this.ariaLocation)this.openNavigation(this.ariaLocation)};
    state.ariaNearby=async function(){if(!this.ariaLocation)return alert('اول یک مقصد را روی نقشه انتخاب کن');
      try{const p=this.ariaLocation;this.nearby=await this.api(`/customers/nearby?lat=${encodeURIComponent(p.latitude)}&lng=${encodeURIComponent(p.longitude)}&radius=2000`);
        this.ariaNearbyMarkers.forEach(m=>m.remove());this.ariaNearbyMarkers=[];
        for(const c of this.nearby){if(!c.latitude||!c.longitude)continue;this.ariaNearbyMarkers.push(L.marker([c.latitude,c.longitude],{icon:this.mapIcon()}).bindPopup(`<div dir="rtl"><b>${this.escapeHtml(c.map_label||c.name||'مشتری')}</b></div>`).addTo(this.mainMap))}
      }catch(e){alert(e.message||'نمایش مشتری‌های اطراف انجام نشد')}};
    const init=state.init;state.init=async function(){await init.call(this);setTimeout(()=>{
      const map=document.getElementById('mainMap')?.parentElement;if(!map||document.getElementById('ariaMapCard'))return;
      const card=document.createElement('div');card.id='ariaMapCard';card.className='card p-4 mt-3';card.setAttribute('x-show','ariaLocation');
      card.innerHTML='<div class="min-w-0"><b x-text="ariaLocation?.title||ariaLocation?.name"></b><div class="text-sm muted" x-text="ariaLocation?.formatted_address||ariaLocation?.address"></div></div><div class="flex flex-wrap gap-2 mt-3"><button type="button" class="btn primary" @click="ariaNavigate()">مسیریابی</button><button type="button" class="btn soft" @click="ariaNearby()">مشتری‌های اطراف</button><button type="button" class="btn glass" @click="ariaLocation=null;if(ariaSearchMarker){ariaSearchMarker.remove();ariaSearchMarker=null}">بستن</button></div>';
      map.insertAdjacentElement('afterend',card);if(window.Alpine)Alpine.initTree(card)},0)};
    return state;
  };
})();
