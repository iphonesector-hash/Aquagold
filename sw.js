const VERSION='20260830-hotfix2';
const CACHE='aquagold-v8-hotfix2-shell';
const SHELL=[
  '/', '/manifest.json', `/offline-store.js?v=${VERSION}`, `/ui-v3-base.js?v=${VERSION}`, `/ui-v4-enhancements.js?v=${VERSION}`,
  `/ui-commerce.js?v=${VERSION}`, `/ui-visual-polish.js?v=${VERSION}`, `/aqua-premium.js?v=${VERSION}`, `/aqua-ai.js?v=${VERSION}`,
  `/bale-ui.js?v=${VERSION}`, `/ui-v4-finalize.js?v=${VERSION}`, `/aria-v8.js?v=${VERSION}`, `/ui-detail-v8.js?v=${VERSION}`,
  `/aqua-premium.css?v=${VERSION}`, `/aqua-ai.css?v=${VERSION}`, `/bale.css?v=${VERSION}`, '/assets/brand-sector.svg',
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
  const critical=['script','style','worker'].includes(event.request.destination);
  if(critical){
    event.respondWith(fetch(event.request).then(response=>{if(response.ok)caches.open(CACHE).then(cache=>cache.put(event.request,response.clone()));return response}).catch(()=>caches.match(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request).then(response=>{if(response.ok)caches.open(CACHE).then(cache=>cache.put(event.request,response.clone()));return response})));
});
self.addEventListener('push',event=>{let data={};try{data=event.data?.json()||{}}catch{data={body:event.data?.text()||''}};const title=data.title||'AquaGold';const options={body:data.body||'',icon:'/icon-180.png',badge:'/icon-180.png',tag:data.tag||'aquagold',renotify:true,data:{url:data.url||'/'}};event.waitUntil(self.registration.showNotification(title,options))});
self.addEventListener('notificationclick',event=>{event.notification.close();const url=event.notification?.data?.url||'/';event.waitUntil((async()=>{const list=await clients.matchAll({type:'window',includeUncontrolled:true});for(const client of list){if('focus'in client){try{await client.navigate(url)}catch{}return client.focus()}}if(clients.openWindow)return clients.openWindow(url)})())});
