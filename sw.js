const CACHE='aquagold-v8-rc2-shell';
const SHELL=[
  '/', '/manifest.json', '/offline-store.js', '/ui-v3-base.js', '/ui-v4-enhancements.js',
  '/ui-commerce.js', '/ui-visual-polish.js', '/aqua-premium.js', '/aqua-ai.js',
  '/bale-ui.js', '/ui-v4-finalize.js', '/aria-v8.js', '/ui-detail-v8.js',
  '/aqua-premium.css', '/aqua-ai.css', '/bale.css', '/assets/brand-sector.svg',
  '/icon-180.png', '/icon-192.png', '/icon-512.png', '/vendor/vazirmatn.css',
  '/vendor/leaflet-1.9.4.css', '/vendor/leaflet-1.9.4.js', '/vendor/chart-4.4.7.min.js',
  '/vendor/alpinejs-3.14.9.min.js', '/vendor/tailwindcss-3.4.17.js'
];

self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil((async()=>{const keys=await caches.keys();await Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)));await self.clients.claim()})()));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const url=new URL(event.request.url);
  if(url.origin!==location.origin||url.pathname.startsWith('/api/'))return;
  if(event.request.mode==='navigate'){
    event.respondWith(fetch(event.request).then(response=>{if(response.ok)caches.open(CACHE).then(cache=>cache.put('/',response.clone()));return response}).catch(()=>caches.match('/')));
    return;
  }
  event.respondWith(caches.match(event.request,{ignoreSearch:true}).then(cached=>cached||fetch(event.request).then(response=>{if(response.ok)caches.open(CACHE).then(cache=>cache.put(event.request,response.clone()));return response})));
});
self.addEventListener('push',event=>{let data={};try{data=event.data?.json()||{}}catch{data={body:event.data?.text()||''}};const title=data.title||'AquaGold';const options={body:data.body||'',icon:'/icon-180.png',badge:'/icon-180.png',tag:data.tag||'aquagold',renotify:true,data:{url:data.url||'/'}};event.waitUntil(self.registration.showNotification(title,options))});
self.addEventListener('notificationclick',event=>{event.notification.close();const url=event.notification?.data?.url||'/';event.waitUntil((async()=>{const list=await clients.matchAll({type:'window',includeUncontrolled:true});for(const client of list){if('focus'in client){try{await client.navigate(url)}catch{}return client.focus()}}if(clients.openWindow)return clients.openWindow(url)})())});
