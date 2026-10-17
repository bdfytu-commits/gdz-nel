/* =========================================================
   service worker ГДЗ НЭЛ
   стратегия:
     - статика (css/js/svg/png/шрифты) — cache-first
     - JSON данных (app/data/*.json) — network-first, офлайн из кэша
     - переходы по странице — сеть, офлайн — index.html из кэша
   ========================================================= */

const VERSION = 'gdz-nel-v3';
const STATIC_CACHE = VERSION + '-static';
const DATA_CACHE = VERSION + '-data';

const PRECACHE = [
  './',
  './index.html',
  './assets/style.css',
  './assets/script.js',
  './manifest.json',
  './data/catalog.json',
  './data/stats.json',
  '../index.html',
  '../auth.html',
  '../profile.html',
  '../photo.html',
  '../terms.html',
  '../assets/style.css',
  '../assets/script.js',
  '../assets/supabase.js',
  '../favicon.ico',
  '../favicon.svg',
  '../assets/img/logo.png',
  '../assets/img/logo-120.png',
  '../assets/img/icons/apple-touch-icon.png',
  '../assets/img/icons/icon-192.png',
  '../assets/img/icons/icon-512.png',
  '../assets/img/icons/icon-maskable-512.png',
  // иконки (используются как CSS-маски, нужны офлайн)
  '../assets/img/icons/alert.svg',
  '../assets/img/icons/android.svg',
  '../assets/img/icons/arrow-left.svg',
  '../assets/img/icons/arrow-right.svg',
  '../assets/img/icons/ban.svg',
  '../assets/img/icons/biology.svg',
  '../assets/img/icons/book.svg',
  '../assets/img/icons/camera.svg',
  '../assets/img/icons/chart.svg',
  '../assets/img/icons/check.svg',
  '../assets/img/icons/chevron-down.svg',
  '../assets/img/icons/chevron-right.svg',
  '../assets/img/icons/clock.svg',
  '../assets/img/icons/close.svg',
  '../assets/img/icons/code.svg',
  '../assets/img/icons/copy.svg',
  '../assets/img/icons/download.svg',
  '../assets/img/icons/english.svg',
  '../assets/img/icons/external.svg',
  '../assets/img/icons/eye.svg',
  '../assets/img/icons/flag.svg',
  '../assets/img/icons/history.svg',
  '../assets/img/icons/home.svg',
  '../assets/img/icons/image.svg',
  '../assets/img/icons/info.svg',
  '../assets/img/icons/logout.svg',
  '../assets/img/icons/mail.svg',
  '../assets/img/icons/math.svg',
  '../assets/img/icons/message.svg',
  '../assets/img/icons/moon.svg',
  '../assets/img/icons/russian.svg',
  '../assets/img/icons/search.svg',
  '../assets/img/icons/send.svg',
  '../assets/img/icons/share.svg',
  '../assets/img/icons/social.svg',
  '../assets/img/icons/sparkles.svg',
  '../assets/img/icons/star-filled.svg',
  '../assets/img/icons/star.svg',
  '../assets/img/icons/sun.svg',
  '../assets/img/icons/trash.svg',
  '../assets/img/icons/user.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key !== STATIC_CACHE && key !== DATA_CACHE)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// сеть, при обрыве — кэш
async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) cache.put(request, fresh.clone());
    return fresh;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw err;
  }
}

// кэш, при промахе — сеть (и кладём в кэш)
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request, { ignoreSearch: true });
  if (cached) return cached;

  const fresh = await fetch(request);
  // opaque — шрифты с CDN без CORS
  if (fresh && (fresh.ok || fresh.type === 'opaque')) {
    cache.put(request, fresh.clone());
  }
  return fresh;
}

// переходы: сеть, офлайн — главная страница приложения из кэша
async function navigationHandler(request) {
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, fresh.clone());
    }
    return fresh;
  } catch (err) {
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return cached;
    const fallback = await caches.match('./index.html') || await caches.match('./');
    if (fallback) return fallback;
    throw err;
  }
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // данные: всегда свежие, офлайн — из кэша
  if (url.pathname.includes('/app/data/')) {
    event.respondWith(networkFirst(request, DATA_CACHE));
    return;
  }

  // навигация
  if (request.mode === 'navigate') {
    event.respondWith(navigationHandler(request));
    return;
  }

  // статика
  event.respondWith(cacheFirst(request, STATIC_CACHE));
});
