/* =========================================================
   service worker ГДЗ НЭЛ — v12 (офлайн-учебники + IndexedDB)

   стратегии:
     - навигация — Network First; офлайн: кэш → offline.html
     - JSON данных — Network First; офлайн: IndexedDB (скачанный
       учебник) → кэш
     - картинки — Cache First → IndexedDB (Blob) → сеть
     - шрифты — Cache First
     - остальная статика — Cache First

   Явно скачанные учебники лежат в IndexedDB (gdz-nel-offline),
   поэтому работают даже после очистки HTTP-кэша.
   ========================================================= */

const VERSION = 'gdz-nel-v13';
const STATIC_CACHE = VERSION + '-static';
const DATA_CACHE = VERSION + '-data';
const IMAGE_CACHE = VERSION + '-image';
const FONT_CACHE = VERSION + '-font';
const OFFLINE_URL = './offline.html';

const PRECACHE = [
  './',
  './index.html',
  './offline.html',
  './assets/style.css',
  './assets/script.js',
  './assets/offline-db.js',
  './assets/v4.js',
  './manifest.json',
  './data/catalog.json',
  './data/stats.json',
  '../offline.html',
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
  '../assets/offline-profile.js',
  '../assets/profile-v4.js',
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
  // Страховка для картинок без CORS: страница не может прочитать Blob,
  // но service worker может положить opaque-ответ в Cache API.
  if (event.data && event.data.type === 'CACHE_IMAGES' && Array.isArray(event.data.urls)) {
    event.waitUntil(cacheOpaqueImages(event.data.urls.slice(0, 40)));
  }
  if (event.data && event.data.type === 'PROCESS_AUTO_OFFLINE') {
    event.waitUntil(processAutoQueue());
  }
});

/* ---------- PRO: фоновое скачивание последних учебников ---------- */

self.addEventListener('sync', (event) => {
  if (event.tag === 'gdz-auto-offline') event.waitUntil(processAutoQueue());
});

function txDone(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

async function saveAutoBook(db, entry, doc) {
  const tasks = Array.isArray(doc.tasks) ? doc.tasks : [];
  if (!tasks.length) return false;
  const meta = {
    file: entry.file,
    id: entry.id || '',
    title: entry.title || doc.textbook || '',
    author: entry.author || doc.author || '',
    year: entry.year || doc.year || '',
    grade: entry.grade || '',
    gradeTitle: entry.gradeTitle || '',
    subject: entry.subject || doc.subject || '',
    subjectTitle: entry.subjectTitle || '',
    taskCount: tasks.length,
    imageCount: 0,
    failedImages: 0,
    bytes: 0,
    auto: true,
    downloadedAt: Date.now()
  };

  const tx = db.transaction(['tasks', 'books'], 'readwrite');
  const taskStore = tx.objectStore('tasks');
  tasks.forEach((task, index) => {
    taskStore.put({
      key: entry.file + '::' + String(task.number),
      file: entry.file,
      number: String(task.number),
      index,
      data: task
    });
  });
  tx.objectStore('books').put(meta);
  await txDone(tx);

  // Картинки сохраняем best-effort: не валим фоновую загрузку из-за CORS/404.
  const urls = [];
  const seen = new Set();
  for (const task of tasks) {
    for (const raw of (Array.isArray(task.images) ? task.images : [])) {
      let url = raw;
      try { url = new URL(raw, entry.pageUrl || self.registration.scope).href; } catch { continue; }
      if (seen.has(url) || url.startsWith('data:')) continue;
      seen.add(url);
      urls.push(url);
      if (urls.length >= 120) break;
    }
    if (urls.length >= 120) break;
  }

  let saved = 0;
  let failed = 0;
  let bytes = 0;
  for (const url of urls) {
    try {
      const response = await fetch(url, { mode: 'no-cors' });
      if (!response) throw new Error('нет ответа');
      const blob = await response.blob();
      if (!blob || !blob.size) throw new Error('пусто');
      // Каждую картинку пишем отдельной транзакцией: ждать fetch внутри
      // одной транзакции нельзя — IndexedDB закроет её между задачами.
      const imgTx = db.transaction('images', 'readwrite');
      imgTx.objectStore('images').put({
        url, file: entry.file, blob, bytes: blob.size, type: blob.type || '', savedAt: Date.now()
      });
      await txDone(imgTx);
      saved++;
      bytes += blob.size;
    } catch (err) {
      failed++;
    }
  }

  meta.imageCount = saved;
  meta.failedImages = failed;
  meta.bytes = bytes;
  const metaTx = db.transaction('books', 'readwrite');
  metaTx.objectStore('books').put(meta);
  await txDone(metaTx);
  return true;
}

async function processAutoQueue() {
  const db = await openOfflineDB();
  if (!db) return;
  let rows = [];
  try {
    const tx = db.transaction('queue', 'readonly');
    rows = await idbRequest(tx.objectStore('queue').getAll());
  } catch (err) {
    return;
  }
  rows.sort((a, b) => (a.queuedAt || 0) - (b.queuedAt || 0));

  for (const entry of rows.slice(0, 5)) {
    try {
      const path = entry.url || ('data/' + entry.file);
      const res = await fetch(new URL(path, self.registration.scope), { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const doc = await res.json();
      await saveAutoBook(db, entry, doc);
      const rm = db.transaction('queue', 'readwrite');
      rm.objectStore('queue').delete(entry.file);
      await txDone(rm);
    } catch (err) {
      // оставляем в очереди: Background Sync попробует позже
    }
  }

  const clients = await self.clients.matchAll({ includeUncontrolled: true });
  clients.forEach((client) => client.postMessage({ type: 'AUTO_OFFLINE_DONE' }));
}

async function cacheOpaqueImages(urls) {
  const cache = await caches.open(IMAGE_CACHE);
  for (const url of urls) {
    try {
      const response = await fetch(url, { mode: 'no-cors' });
      if (response) await cache.put(url, response);
    } catch (err) { /* источник недоступен — пропускаем */ }
  }
}

/* ---------- IndexedDB (та же база, что и у страницы) ---------- */

function openOfflineDB() {
  return new Promise((resolve) => {
    if (!self.indexedDB) { resolve(null); return; }
    const request = indexedDB.open('gdz-nel-offline', 2);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('books')) db.createObjectStore('books', { keyPath: 'file' });
      if (!db.objectStoreNames.contains('tasks')) {
        const store = db.createObjectStore('tasks', { keyPath: 'key' });
        store.createIndex('file', 'file', { unique: false });
      }
      if (!db.objectStoreNames.contains('images')) {
        const store = db.createObjectStore('images', { keyPath: 'url' });
        store.createIndex('file', 'file', { unique: false });
      }
      if (!db.objectStoreNames.contains('queue')) {
        db.createObjectStore('queue', { keyPath: 'file' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
  });
}

function idbRequest(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function getBookFromIDB(file) {
  const db = await openOfflineDB();
  if (!db) return null;
  try {
    const tx = db.transaction('tasks', 'readonly');
    const rows = await idbRequest(tx.objectStore('tasks').index('file').getAll(IDBKeyRange.only(file)));
    if (!rows || !rows.length) return null;
    rows.sort((a, b) => a.index - b.index);
    return { tasks: rows.map((row) => row.data) };
  } catch (err) {
    return null;
  }
}

async function hasOfflineBooks() {
  const db = await openOfflineDB();
  if (!db) return false;
  try {
    const tx = db.transaction('books', 'readonly');
    const count = await idbRequest(tx.objectStore('books').count());
    return count > 0;
  } catch (err) {
    return false;
  }
}

// Cloudflare Pages редиректит offline.html → offline. Ответ с редиректом
// нельзя отдавать на навигацию (браузер даёт net::ERR_FAILED), поэтому
// пересобираем обычный 200 из тела закэшированной страницы.
async function withoutRedirect(response) {
  if (!response || !response.redirected) return response;
  const body = await response.blob();
  return new Response(body, {
    status: 200,
    headers: { 'content-type': 'text/html; charset=utf-8' }
  });
}

async function getOfflinePage() {
  const cached = await caches.match(OFFLINE_URL, { ignoreSearch: true });
  if (!cached) return null;
  return new Response(await cached.text(), {
    status: 200,
    headers: { 'content-type': 'text/html; charset=utf-8' }
  });
}

async function getImageFromIDB(url) {
  const db = await openOfflineDB();
  if (!db) return null;
  try {
    const tx = db.transaction('images', 'readonly');
    const row = await idbRequest(tx.objectStore('images').get(url));
    return row ? row.blob : null;
  } catch (err) {
    return null;
  }
}

/* ---------- стратегии ---------- */

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) cache.put(request, fresh.clone());
    return fresh;
  } catch (err) {
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request, { ignoreSearch: true });
  if (cached) return cached;
  const fresh = await fetch(request);
  if (fresh && (fresh.ok || fresh.type === 'opaque')) cache.put(request, fresh.clone());
  return fresh;
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const network = fetch(request).then((fresh) => {
    if (fresh && fresh.ok) cache.put(request, fresh.clone());
    return fresh;
  }).catch(() => cached);
  return cached || network;
}

/* ---------- данные приложения ---------- */

async function dataHandler(request) {
  const cache = await caches.open(DATA_CACHE);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) cache.put(request, fresh.clone());
    return fresh;
  } catch (err) {
    const url = new URL(request.url);
    const marker = '/app/data/';
    const index = url.pathname.indexOf(marker);
    if (index !== -1) {
      const file = url.pathname.slice(index + marker.length);
      if (!/^(catalog|stats|search-index)\.json$/.test(file) && !file.startsWith('search/')) {
        const book = await getBookFromIDB(file);
        if (book) {
          return new Response(JSON.stringify(book), {
            status: 200,
            headers: { 'content-type': 'application/json; charset=utf-8', 'x-gdz-source': 'indexeddb' }
          });
        }
      }
    }
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    throw err;
  }
}

async function imageHandler(request) {
  const cache = await caches.open(IMAGE_CACHE);
  const cached = await cache.match(request, { ignoreSearch: true });
  if (cached) return cached;

  const blob = await getImageFromIDB(request.url);
  if (blob) {
    return new Response(blob, {
      status: 200,
      headers: {
        'content-type': blob.type || 'image/png',
        'cache-control': 'public, max-age=86400',
        'x-gdz-source': 'indexeddb'
      }
    });
  }

  const fresh = await fetch(request);
  if (fresh && (fresh.ok || fresh.type === 'opaque')) cache.put(request, fresh.clone());
  return fresh;
}

/* ---------- навигация ---------- */

async function navigationHandler(request) {
  const requestUrl = new URL(request.url);
  if (
    self.navigator && self.navigator.onLine === false &&
    requestUrl.pathname.indexOf('/app/') === 0 &&
    !requestUrl.pathname.endsWith('/offline.html')
  ) {
    const books = await hasOfflineBooks();
    if (!books) {
      const offlinePage = await getOfflinePage();
      if (offlinePage) return offlinePage;
    }
  }
  try {
    // no-store: не даём HTTP-кэшу замаскировать отсутствие сети
    const fresh = await fetch(request, { cache: 'no-store' });
    if (fresh && fresh.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, fresh.clone());
    }
    return fresh;
  } catch (err) {
    const url = new URL(request.url);
    // нет сети и ни одного скачанного учебника — показываем offline.html,
    // а не пустую оболочку приложения
    if (url.pathname.indexOf('/app/') === 0 && !url.pathname.endsWith('/offline.html')) {
      const books = await hasOfflineBooks();
      if (!books) {
        const offlinePage = await getOfflinePage();
        if (offlinePage) return offlinePage;
      }
    }
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return withoutRedirect(cached);
    const shell = await caches.match('./index.html') || await caches.match('./');
    if (shell) return withoutRedirect(shell);
    const offline = await getOfflinePage();
    if (offline) return offline;
    return new Response(
      '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Нет сети — ГДЗ НЭЛ</title>' +
      '<body style="font-family:system-ui;padding:40px"><h1>Нет подключения</h1>' +
      '<p>Откройте приложение онлайн хотя бы раз и скачайте учебники для офлайна.</p></body></html>',
      { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } }
    );
  }
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // чужие домены: кэшируем и отдаём из IndexedDB только картинки,
  // остальное (Supabase REST и API) — всегда через сеть
  if (url.origin !== self.location.origin) {
    if (request.destination === 'image') {
      event.respondWith(imageHandler(request).catch(() => fetch(request)));
    }
    return;
  }

  // данные приложения (json): сеть, офлайн — IndexedDB/кэш
  if (url.pathname.includes('/app/data/') && !/\.(png|jpe?g|webp|gif|svg|ico)$/i.test(url.pathname)) {
    event.respondWith(dataHandler(request));
    return;
  }

  // картинки: кэш → IndexedDB → сеть
  if (request.destination === 'image' || /\.(png|jpe?g|webp|gif|svg|ico)$/i.test(url.pathname)) {
    event.respondWith(imageHandler(request));
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
