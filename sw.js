const CACHE='aquagold-network-only-recovery-20260827-v8';
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil((async()=>{const keys=await caches.keys();await Promise.all(keys.map(k=>caches.delete(k)));await self.clients.claim()})()));
self.addEventListener('fetch',event=>{if(event.request.method==='GET')event.respondWith(fetch(event.request))});
self.addEventListener('push',event=>{let data={};try{data=event.data?.json()||{}}catch{data={body:event.data?.text()||''}};const title=data.title||'AquaGold';const options={body:data.body||'',icon:'/icon-180.png',badge:'/icon-180.png',tag:data.tag||'aquagold',renotify:true,data:{url:data.url||'/'}};event.waitUntil(self.registration.showNotification(title,options))});
self.addEventListener('notificationclick',event=>{event.notification.close();const url=event.notification?.data?.url||'/';event.waitUntil((async()=>{const list=await clients.matchAll({type:'window',includeUncontrolled:true});for(const c of list){if('focus'in c){try{await c.navigate(url)}catch{}return c.focus()}}if(clients.openWindow)return clients.openWindow(url)})())});
