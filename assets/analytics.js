/* =========================================================
   ГДЗ НЭЛ — аналитика (Ф26).

   Лёгкие события в таблицу events Supabase: просмотры страниц,
   просмотры заданий, поиск, скачивания APK, Web Vitals.
   Только публикуемый ключ — доступ ограничен RLS (insert anon,
   читать может только админ). Ошибки глотаем: аналитика никогда
   не должна ломать страницу. Файл подключается как обычный скрипт:
   <script src="assets/analytics.js" defer></script>
   ========================================================= */

(function () {
  'use strict';

  var SUPABASE_URL = 'https://qncqeoklwblztbnoktwk.supabase.co';
  var SUPABASE_KEY = 'sb_publishable_uyBIZ2gNPuDqxre3ea989w_WbctezF4';

  var sentVitals = false;

  // Уникальный посетитель: стабильный id в localStorage. Нужен, чтобы
  // отличать живые просмотры от повторных заходов и ботов без хранилища.
  var VISITOR_KEY = 'gdz-nel-visitor';

  function visitorId() {
    try {
      var id = localStorage.getItem(VISITOR_KEY);
      if (!id) {
        id = 'v-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
        localStorage.setItem(VISITOR_KEY, id);
      }
      return id;
    } catch (err) {
      return 'anon';
    }
  }

  var visitor = visitorId();

  function dayKey() {
    var d = new Date();
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }

  // Один page_view на страницу в сутки с одного браузера.
  function seenToday(name, path) {
    try {
      var key = 'gdz-nel-ev:' + dayKey() + ':' + name + ':' + path;
      if (localStorage.getItem(key)) return true;
      localStorage.setItem(key, '1');
      return false;
    } catch (err) {
      return false;
    }
  }

  function send(name, meta) {
    if (!name) return;
    // офлайн: не шумим ошибками в консоли и не копим очередь
    if (typeof navigator !== 'undefined' && navigator.onLine === false) return;
    var path = (location.pathname + location.hash).slice(0, 300);
    if (name === 'page_view' && seenToday(name, path)) return;
    var payload = meta ? Object.assign({ visitor: visitor }, meta) : { visitor: visitor };
    try {
      fetch(SUPABASE_URL + '/rest/v1/events', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          apikey: SUPABASE_KEY,
          Authorization: 'Bearer ' + SUPABASE_KEY,
          Prefer: 'return=minimal'
        },
        body: JSON.stringify({
          name: String(name).slice(0, 64),
          path: path,
          meta: payload
        }),
        keepalive: true
      }).catch(function () { /* офлайн — не страшно */ });
    } catch (err) { /* ignore */ }
  }

  window.gdzTrack = send;

  // просмотр страницы
  send('page_view');

  // скачивание APK — клик по любой ссылке с app.apk (Ф26.5)
  document.addEventListener('click', function (event) {
    var link = event.target && event.target.closest ? event.target.closest('a[href*="app.apk"]') : null;
    if (link) send('apk_download', { href: link.getAttribute('href') });
  }, true);

  // если браузер не умеет поддерживать PWA — отметим (пригодится в статистике)
  if (!('serviceWorker' in navigator)) send('no_service_worker');

  // ---------- Web Vitals: LCP, CLS, INP (Ф26.6) ----------

  var vitals = {};

  try {
    new PerformanceObserver(function (list) {
      var entries = list.getEntries();
      if (entries.length) vitals.lcp = Math.round(entries[entries.length - 1].startTime);
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (err) { /* не поддерживается */ }

  try {
    var cls = 0;
    new PerformanceObserver(function (list) {
      list.getEntries().forEach(function (entry) {
        if (!entry.hadRecentInput) cls += entry.value;
      });
      vitals.cls = Math.round(cls * 1000) / 1000;
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (err) { /* не поддерживается */ }

  try {
    var inp = 0;
    new PerformanceObserver(function (list) {
      list.getEntries().forEach(function (entry) {
        if (entry.duration > inp) inp = entry.duration;
      });
      vitals.inp = Math.round(inp);
    }).observe({ type: 'event', buffered: true, durationThreshold: 104 });
  } catch (err) { /* не поддерживается */ }

  function flushVitals() {
    if (sentVitals || !Object.keys(vitals).length) return;
    sentVitals = true;
    send('web_vitals', vitals);
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flushVitals();
  });
  window.addEventListener('pagehide', flushVitals);
})();
