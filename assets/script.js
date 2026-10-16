'use strict';

/* =========================================================
   ГДЗ НЭЛ — скрипты лендинга.
   1) тёмная тема (localStorage + prefers-color-scheme)
   2) тень шапки при скролле
   3) появление блоков при скролле (один раз)
   4) счётчики заданий из stats.json
   ========================================================= */

(function () {
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- 1. тёмная тема ---------- */

  var THEME_KEY = 'gdz-nel-theme';
  var root = document.documentElement;

  function storedTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (err) { return null; }
  }

  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      var dark = theme === 'dark';
      btn.setAttribute('aria-label', dark ? 'Включить светлую тему' : 'Включить тёмную тему');
      var icon = btn.querySelector('.icon');
      icon.classList.toggle('i-sun', dark);
      icon.classList.toggle('i-moon', !dark);
    }
  }

  // первый заход: сохранённый выбор или системная тема
  applyTheme(storedTheme() || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));

  var toggleBtn = document.getElementById('theme-toggle');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(THEME_KEY, next); } catch (err) { /* приватный режим */ }
      applyTheme(next);
    });
  }

  /* ---------- 2. тень шапки при скролле ---------- */

  var header = document.getElementById('site-header');
  if (header) {
    var onScroll = function () {
      header.classList.toggle('is-stuck', window.scrollY > 6);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ---------- 3. появление при скролле ---------- */

  var items = Array.prototype.slice.call(document.querySelectorAll('.reveal'));

  if (!reduced && 'IntersectionObserver' in window) {
    items.forEach(function (el) {
      var index = Array.prototype.indexOf.call(el.parentElement.children, el);
      el.style.transitionDelay = Math.min(index, 6) * 70 + 'ms';
      el.classList.add('is-hidden');
    });

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;

        // после проигрывания убираем задержку, чтобы она не тормозила hover
        el.addEventListener('transitionend', function done() {
          el.style.transitionDelay = '0ms';
          el.removeEventListener('transitionend', done);
        });

        el.classList.remove('is-hidden');
        observer.unobserve(el);
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -30px 0px' });

    items.forEach(function (el) { observer.observe(el); });
  }

  /* ---------- 4. счётчики из stats.json ---------- */

  fetch('app/data/stats.json')
    .then(function (res) { return res.ok ? res.json() : null; })
    .then(function (stats) {
      if (!stats) return;

      var tasksEl = document.getElementById('stat-tasks');
      var booksEl = document.getElementById('stat-books');
      var footerEl = document.getElementById('footer-stats');

      if (tasksEl) tasksEl.textContent = stats.total;
      if (booksEl) booksEl.textContent = stats.textbooks;

      if (footerEl) {
        footerEl.textContent =
          stats.total + ' ' + plural(stats.total, 'задание', 'задания', 'заданий') +
          ' · ' + stats.textbooks + ' ' + plural(stats.textbooks, 'учебник', 'учебника', 'учебников') +
          ' · 6 предметов';
      }

      document.querySelectorAll('[data-count]').forEach(function (el) {
        var card = el.closest('[data-subject]');
        var subject = card && stats.subjects[card.getAttribute('data-subject')];
        if (subject) {
          el.textContent = subject.tasks + ' ' + plural(subject.tasks, 'задание', 'задания', 'заданий');
        }
      });
    })
    .catch(function () { /* без статистики страница просто остаётся с базовыми числами */ });

  function plural(n, one, few, many) {
    var m10 = n % 10;
    var m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }
})();
