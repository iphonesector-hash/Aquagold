const CACHE = 'aquagold-v6.1-20260827-1';
const STATIC_ASSETS = [
  '/', '/manifest.json', '/icon-180.png', '/icon-192.png', '/icon-512.png', '/offline-store.js', '/ui-v3-base.js',
  '/ui-v4-enhancements.js', '/ui-v4-finalize.js', '/ui-commerce.js', '/ui-visual-polish.js', '/aqua-premium.js', '/aqua-premium.css', '/aqua-ai.js', '/aqua-ai.css', '/commerce-guidance.js',
  '/vendor/vazirmatn.css', '/vendor/tailwindcss-3.4.17.js', '/vendor/alpinejs-3.14.9.min.js',
  '/vendor/leaflet-1.9.4.js', '/vendor/leaflet-1.9.4.css', '/vendor/chart-4.4.7.min.js',
  '/vendor/html2canvas-1.4.1.min.js', '/assets/brand-sector.svg', '/assets/aquagold-stamp.svg',
  '/assets/aqua-icons.svg', '/assets/aqua-wave.webp', '/assets/product-ro-filter.svg', '/assets/product-fridge-filter.svg'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => Promise.allSettled(
    STATIC_ASSETS.map(asset => cache.add(asset))
  )));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || request.url.includes('/api/')) return;

  if (request.mode === 'navigate' || request.destination === 'document') {
    event.respondWith(fetch(request).then(response => {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put('/', copy));
      return response;
    }).catch(async () => (await caches.match(request)) || (await caches.match('/')) || new Response(
      '<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#020817"><body style="font-family:system-ui;background:radial-gradient(circle at 50% 15%,#0b4f87,#020817 58%);color:white;display:grid;place-items:center;min-height:100vh;text-align:center;padding:24px"><main><div style="font-size:52px">💧</div><h1>AquaGold</h1><p>اینترنت قطع است. پیش‌نویس‌های شما روی دستگاه حفظ شده‌اند.</p><button onclick="location.reload()" style="padding:12px 22px;border:1px solid #35d9ff;border-radius:14px;background:#075ba0;color:white">تلاش دوباره</button></main></body></html>',
      {headers:{'Content-Type':'text/html; charset=utf-8'}}
    )));
    return;
  }

  event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
    if (response && response.status === 200) {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(request, copy));
    }
    return response;
  })));
});