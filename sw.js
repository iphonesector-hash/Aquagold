const CACHE = 'aquagold-network-only-recovery-20260901-stable1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  event.respondWith(fetch(request));
});
self.addEventListener('push', event => {
  let data = {title:'AquaGold', body:'اعلان جدید', url:'/', tag:'aquagold'};
  try { if (event.data) data = {...data, ...event.data.json()}; } catch { try { data.body = event.data?.text() || data.body; } catch {} }
  event.waitUntil(self.registration.showNotification(data.title || 'AquaGold', {
    body: data.body || '', icon:'/icon-192.png', badge:'/icon-192.png', tag:data.tag || 'aquagold',
    data:{url:data.url || '/'}, renotify:true, vibrate:[180,80,180]
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || '/', self.location.origin).href;
  event.waitUntil((async()=>{
    const windows = await clients.matchAll({type:'window', includeUncontrolled:true});
    for (const client of windows) {
      if ('focus' in client) { await client.focus(); if ('navigate' in client) await client.navigate(target); return; }
    }
    if (clients.openWindow) await clients.openWindow(target);
  })());
});
