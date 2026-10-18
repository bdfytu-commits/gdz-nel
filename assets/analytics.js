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

  function send(name, meta) {
    if (!name) return;
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
          path: (location.pathname + location.hash).slice(0, 300),
          meta: meta || {}
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
