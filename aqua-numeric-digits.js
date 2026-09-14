/* Preserve the Finance/Map baseline while accepting Persian/Arabic digits globally. */
(()=>{
  const previous=window.app;if(typeof previous!=='function')return;
  const digits={'۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9','٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9'};
  window.app=function(){
    const state=previous();
    state.num=function(v){return Number(String(v??0).replace(/[۰-۹٠-٩]/g,n=>digits[n]).replace(/[٬،,\s]/g,''))||0};
    return state;
  };
})();
