import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const read=name=>readFileSync(new URL('../'+name,import.meta.url),'utf8');
const source=read('aqua-aria-map.js');
const A={title:'گلستان ۱۵',address:'تهران مرزداران گلستان ۱۵',latitude:35.73,longitude:51.36};
function runtime(items=[A]){
 const calls={chat:[],search:[],selected:[],started:[],oldClicks:0};
 const document={readyState:'complete',querySelector:s=>s==='#aqst-free-card .aqst-free-start'?{click(){calls.oldClicks++}}:null,querySelectorAll:()=>[],getElementById:()=>null};
 const window={app:()=>({aquaMessages:[],gps:{},aquaScroll(){},escapeHtml:v=>v,renderMainMap(){},mainMap:{invalidateSize(){}},submitAquaText:async(...args)=>{calls.chat.push(args);return true},api:async path=>{calls.search.push(path);return{items}}})};
 window.AquaMapBridge={async selectDestination(p){calls.selected.push(p);return true},async startNavigation(p){calls.started.push(p);return true}};
 const context=vm.createContext({window,document,console,setTimeout:f=>{f();return 1},clearTimeout(){},Intl,Date});
 vm.runInContext(source,context);return{state:window.app(),calls,window,context};
}
test('weather, news, customer and finance questions preserve the original chat including voice id',async()=>{
 for(const text of ['هوای تهران چطوره؟','اخبار کرج رو نشون بده','مشتری مرزداران رو پیدا کن','قیمت طلا تهران','فروش امروز تهران چقدر بود؟']){
  const {state,calls}=runtime();await state.submitAquaText(text,'voice',17);
  assert.equal(calls.chat.length,1,text);assert.equal(calls.chat[0][2],17);assert.equal(calls.search.length,0,text);
 }
});
test('a bare address is remembered and its follow-up opens the same coordinates',async()=>{
 const {state,calls}=runtime();await state.submitAquaText('مرزداران گلستان پانزده');
 assert.equal(state.ariaLocation.latitude,A.latitude);assert.equal(calls.chat.length,0);
 await state.submitAquaText('روی نقشه نشون بده');assert.equal(calls.selected.length,1);assert.equal(calls.selected[0].longitude,A.longitude);
});
test('unrelated results and different street numbers are rejected and old context is cleared',async()=>{
 for(const item of [{...A,title:'محل نامرتبط',address:'شیراز'},{...A,title:'گلستان ۱۵۰',address:'تهران مرزداران گلستان ۱۵۰'}]){
  const {state,calls}=runtime([item]);state.ariaLocation=A;
  await state.submitAquaText('مرزداران گلستان ۱۵ روی نقشه نشون بده');
  assert.equal(state.ariaLocation,null);assert.equal(calls.selected.length,0);assert.equal(state.aquaMessages.at(-1).error,true);
 }
});
test('ambiguous results require explicit selection and dispatch the selected coordinates',async()=>{
 const B={...A,latitude:35.74};const {state,calls}=runtime([A,B]);
 await state.submitAquaText('مرزداران گلستان ۱۵ روی نقشه نشون بده');
 const results=state.aquaMessages.at(-1).results;assert.equal(results.length,2);assert.equal(calls.selected.length,0);
 await state.runAquaAction({type:'show_customer_on_map',customer:results[1]});
 assert.equal(calls.selected[0].latitude,B.latitude);
});
test('an existing route button cannot start the previous destination',async()=>{
 const {state,calls}=runtime();await state.navigateInternal(A);
 assert.equal(calls.oldClicks,0);assert.equal(calls.started.length,1);assert.equal(calls.started[0].latitude,A.latitude);
});
test('missing bridge and failed navigation do not claim success or click an old button',async()=>{
 const {state,calls,window}=runtime();window.AquaMapBridge.startNavigation=async()=>false;
 assert.equal(await state.navigateInternal(A),false);delete window.AquaMapBridge;
 assert.equal(await state.navigateInternal(A),false);assert.equal(calls.oldClicks,0);
});
test('blank, non-finite and out-of-range coordinates never reach navigation',async()=>{
 const {state,calls}=runtime();
 for(const latitude of [null,'',NaN,Infinity,91])assert.equal(await state.navigateInternal({...A,latitude}),false);
 assert.equal(calls.started.length,0);
});
test('new local address lookup is locked against overlapping voice/text submissions',async()=>{
 const {state,calls}=runtime();let resolve;
 state.api=()=>new Promise(r=>resolve=r);
 const first=state.submitAquaText('مرزداران گلستان ۱۵');
 assert.equal(await state.submitAquaText('تهران خیابان آزادی'),false);
 resolve({items:[A]});await first;assert.equal(state.ariaCommandBusy,false);assert.equal(calls.chat.length,0);
});
test('map bridge replaces A with B before navigation and rejects concurrent starts',async()=>{
 const fragment=read('aqua-navigation-pro-fragment.js');
 const bridgeSource=fragment.slice(fragment.indexOf('function aqBridgePoint('),fragment.indexOf('\nfunction navIcon('));
 const ST={nav:{freeDestination:{lat:1,lng:2}}},selected=[],started=[];let release;
 const ctx=vm.createContext({window:{},ST,mainMap:()=>({}),createNav(){},setupFreeMapTools(){},async selectFreeDestination(p){ST.nav.freeDestination=p;selected.push(p)},async startNavigation(p){started.push(p);await new Promise(r=>release=r);ST.nav.active=true;ST.nav.target=p}});
 vm.runInContext(bridgeSource,ctx);const bridge=ctx.window.AquaMapBridge;
 const pending=bridge.startNavigation(A);await Promise.resolve();await Promise.resolve();await Promise.resolve();
 assert.equal(await bridge.startNavigation({...A,latitude:35.8}),false);
 assert.equal(selected[0].lat,A.latitude);assert.equal(started[0].lng,A.longitude);
 release();assert.equal(await pending,true);
});
test('expense runtime and final card layer preserve the canonical Aria destination flow',async()=>{
 const {context,calls,window}=runtime();vm.runInContext(read('aqua-runtime-completion.js'),context);
 const state=window.app();
 const py=read('aqua_aria_map.py');const patch=py.slice(py.indexOf('function patch(s){'),py.indexOf('function css(){'));
 let cards=0;Object.assign(context,{expensePicker(){},mapLayout(){},fixEdit(){},card(){cards++}});
 vm.runInContext(patch,context);context.patch(state);
 assert.equal(await state.showAriaAddress(A),true);assert.equal(calls.selected.length,1);assert.equal(cards,1);
});
