/* =========================================================
   service worker ГДЗ НЭЛ — v6 (Ф15, Ф29, контурные карты)

   стратегии:
     - навигация (HTML) — Network First, офлайн из кэша
     - JSON данных (app/data/*.json) — Stale-While-Revalidate
     - картинки — Cache First (включая решения с внешнего источника
       и локальные сканы контурных карт из app/data/.../img/)
     - шрифты — Cache First
     - чужие домены, кроме картинок (Supabase REST и прочие API) —
       только сеть, без кэша: иначе «живые» данные (отзывы, лайки)
       навсегда залипают в старом состоянии
     - остальная статика — Cache First

   обновление: новая версия ждёт, страница показывает кнопку
   «Обновить» и шлёт SKIP_WAITING (Ф15.8).
   ========================================================= */

const VERSION = 'gdz-nel-v10';
const STATIC_CACHE = VERSION + '-static';
const DATA_CACHE = VERSION + '-data';
const IMAGE_CACHE = VERSION + '-images';
const FONT_CACHE = VERSION + '-fonts';

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
  '../honor.html',
  '../photo.html',
  '../premium.html',
  '../cheatsheets.html',
  '../search.html',
  '../terms.html',
  '../assets/style.css',
  '../assets/script.js',
  '../assets/supabase.js',
  '../assets/analytics.js',
  '../assets/vendor/fuse.min.js',
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
  '../assets/img/icons/algebra.svg',
  '../assets/img/icons/world.svg',
  '../assets/img/icons/chemistry.svg',
  '../assets/img/icons/physics.svg',
  '../assets/img/icons/geometry.svg',
  '../assets/img/icons/android.svg',
  '../assets/img/icons/arrow-left.svg',
  '../assets/img/icons/arrow-right.svg',
  '../assets/img/icons/arrow-up.svg',
  '../assets/img/icons/award.svg',
  '../assets/img/icons/ban.svg',
  '../assets/img/icons/bell.svg',
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
  '../assets/img/icons/edit.svg',
  '../assets/img/icons/english.svg',
  '../assets/img/icons/external.svg',
  '../assets/img/icons/eye.svg',
  '../assets/img/icons/flag.svg',
  '../assets/img/icons/filter.svg',
  '../assets/img/icons/globe.svg',
  '../assets/img/icons/history.svg',
  '../assets/img/icons/informatics.svg',
  '../assets/img/icons/home.svg',
  '../assets/img/icons/image.svg',
  '../assets/img/icons/info.svg',
  '../assets/img/icons/key.svg',
  '../assets/img/icons/literature.svg',
  '../assets/img/icons/logout.svg',
  '../assets/img/icons/mail.svg',
  '../assets/img/icons/math.svg',
  '../assets/img/icons/message.svg',
  '../assets/img/icons/moon.svg',
  '../assets/img/icons/refresh.svg',
  '../assets/img/icons/russian.svg',
  '../assets/img/icons/search.svg',
  '../assets/img/icons/send.svg',
  '../assets/img/icons/share.svg',
  '../assets/img/icons/shield.svg',
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
  );
  // ждём команды со страницы (SKIP_WAITING), чтобы не перезагружать её посреди чтения
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => key.indexOf(VERSION) !== 0)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
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

// кэш сразу, сеть — в фоне (данные обновятся к следующему заходу)
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const network = fetch(request).then((fresh) => {
    if (fresh && fresh.ok) cache.put(request, fresh.clone());
    return fresh;
  }).catch(() => cached);
  return cached || network;
}

// кэш, при промахе — сеть (и кладём в кэш)
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request, { ignoreSearch: true });
  if (cached) return cached;

  const fresh = await fetch(request);
  // opaque — картинки и шрифты с чужих CDN без CORS
  if (fresh && (fresh.ok || fresh.type === 'opaque')) {
    cache.put(request, fresh.clone());
  }
  return fresh;
}

// переходы: сеть, офлайн — страница из кэша
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

  // чужие домены: кэшируем только картинки (решения с внешнего источника),
  // всё остальное (Supabase REST и прочие API) — всегда через сеть
  if (url.origin !== self.location.origin) {
    if (request.destination === 'image') {
      event.respondWith(cacheFirst(request, IMAGE_CACHE));
    }
    return;
  }

  // данные приложения (json): сначала кэш, свежее — в фоне
  if (url.pathname.includes('/app/data/') && !/\.(png|jpe?g|webp|gif|svg|ico)$/i.test(url.pathname)) {
    event.respondWith(staleWhileRevalidate(request, DATA_CACHE));
    return;
  }

  // картинки (включая решения с внешнего источника): cache first
  if (request.destination === 'image' || /\.(png|jpe?g|webp|gif|svg|ico)$/i.test(url.pathname)) {
    event.respondWith(cacheFirst(request, IMAGE_CACHE));
    return;
  }

  // шрифты: cache first
  if (request.destination === 'font' ||
      url.hostname === 'fonts.gstatic.com' || url.hostname === 'fonts.googleapis.com') {
    event.respondWith(cacheFirst(request, FONT_CACHE));
    return;
  }

  // навигация по страницам
  if (request.mode === 'navigate') {
    event.respondWith(navigationHandler(request));
    return;
  }

  // прочая статика
  event.respondWith(cacheFirst(request, STATIC_CACHE));
});
