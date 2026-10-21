'use strict';

/* =========================================================
   ГДЗ НЭЛ — приложение.
   Хэш-роутинг:
     #/                          список классов
     #/favorites                 избранное
     #/recent                    недавние
     #/<grade>                   предметы класса
     #/<grade>/<subject>         учебники предмета
     #/<grade>/<subject>/<book>  сетка заданий
     #/<grade>/<subject>/<book>/<n>  задание
   Старые ссылки без класса (#/math/...) ведут на 6 класс.
   Данные — app/data/*.json через fetch (кэш в памяти).
   Отзывы — Supabase (window.gdzSupabase из assets/supabase.js).
   ========================================================= */

(function () {
  var DATA_DIR = 'data/';

  var LS_THEME = 'gdz-nel-theme';
  var LS_BOOKMARKS = 'gdz-nel-bookmarks';
  var LS_HISTORY = 'gdz-nel-history';
  var LS_HINT = 'gdz-nel-hint-done';

  var DEFAULT_GRADE = '6';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var screenEl = document.getElementById('screen');
  var headerEl = document.getElementById('app-header');
  var toastEl = document.getElementById('toast');
  var hintEl = document.getElementById('hint');
  var searchInput = document.getElementById('search-input');
  var searchClear = document.getElementById('search-clear');

  var catalog = null;
  var bookCache = {};     // file -> данные учебника
  var searchIndex = null; // облегчённый индекс условий для поиска
  var renderToken = 0;    // защита от гонок при быстрой навигации
  var currentTask = null; // prev/next для клавиатуры и свайпов

  /* =========================================================
     утилиты
     ========================================================= */

  function esc(value) {
    return String(value)
      .replace(/\u2212/g, '-') // математический минус → обычный дефис-минус
      .replace(/[\u2219\u22C5]/g, '·') // операторы умножения → средняя точка
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // дроби: «1/2», «3 / 4» → вертикальная дробь (CSS .frac).
  // Работает по уже экранированному тексту, поэтому безопасен для innerHTML.
  var FRAC_RE = /(^|[^\p{L}\p{N}_/])(\d{1,3})\s*\/\s*(\d{1,3})(?=$|[^\p{L}\p{N}_/])/gu;

  function fracify(escapedText) {
    return String(escapedText).replace(FRAC_RE, function (all, pre, num, den) {
      return pre + '<span class="frac" role="math"><span class="frac-n">' + num +
        '</span><span class="frac-d">' + den + '</span></span>';
    });
  }

  // текст задания с дробями: экранирование + красивые дроби
  function mathHtml(text) {
    return fracify(esc(text));
  }

  /* =========================================================
     SVG-визуализации задачи (Ф29): круговая диаграмма и
     координатная прямая строятся из текста условия.
     ========================================================= */

  var VIS_COLORS = ['#1AA3A3', '#0070C0', '#F5C518', '#E53935', '#16A085', '#8E44AD', '#E67E22', '#5D6D7E'];

  function fmtNum(value) {
    return String(Number(value.toFixed ? value.toFixed(3) : value)).replace('.', ',');
  }

  function escNum(value) {
    return esc(fmtNum(value));
  }

  // круговая диаграмма: parts = [{ label, value }]
  function pieSvg(parts) {
    var total = parts.reduce(function (sum, p) { return sum + p.value; }, 0) || 1;
    var cx = 120, cy = 120, r = 96;
    var angle = -Math.PI / 2;
    var slices = [];

    parts.forEach(function (part, i) {
      var share = part.value / total;
      var end = angle + share * Math.PI * 2;
      var x1 = cx + r * Math.cos(angle), y1 = cy + r * Math.sin(angle);
      var x2 = cx + r * Math.cos(end), y2 = cy + r * Math.sin(end);
      var large = share > 0.5 ? 1 : 0;
      slices.push('<path d="M ' + cx + ' ' + cy + ' L ' + x1.toFixed(2) + ' ' + y1.toFixed(2) +
        ' A ' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x2.toFixed(2) + ' ' + y2.toFixed(2) + ' Z" fill="' +
        VIS_COLORS[i % VIS_COLORS.length] + '" stroke="var(--c-surface)" stroke-width="2"></path>');
      angle = end;
    });

    var legend = parts.map(function (part, i) {
      return '<span class="vis-item"><span class="vis-swatch" style="background:' +
        VIS_COLORS[i % VIS_COLORS.length] + '"></span>' + esc(part.label) + ' — ' +
        escNum(part.value) + '%</span>';
    }).join('');

    return '<figure class="task-visual">' +
      '<svg viewBox="0 0 240 240" width="240" height="240" role="img" aria-label="Круговая диаграмма">' +
      slices.join('') + '</svg>' +
      '<figcaption class="vis-legend">' + legend + '</figcaption></figure>';
  }

  // «красивый» шаг разметки координатной прямой
  function niceStep(raw) {
    if (!raw || raw <= 0) return 1;
    var pow = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var norm = raw / pow;
    var factor = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
    return factor * pow;
  }

  // координатная прямая: points = [{ label, value }]
  function numberLineSvg(points) {
    var values = points.map(function (p) { return p.value; });
    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    if (min === max) { min -= 1; max += 1; }
    var pad = (max - min) * 0.15 || 1;
    min -= pad;
    max += pad;

    var step = niceStep((max - min) / 8);
    var first = Math.ceil(min / step) * step;
    var width = 640, y = 78, left = 24, right = width - 24;
    var toX = function (v) { return left + (v - min) / (max - min) * (right - left); };

    var marks = '';
    for (var v = first; v <= max + 1e-9; v += step) {
      var x = toX(v);
      marks += '<line x1="' + x.toFixed(1) + '" y1="' + (y - 7) + '" x2="' + x.toFixed(1) + '" y2="' + (y + 7) +
        '" stroke="var(--c-text-muted)" stroke-width="1.4"></line>' +
        '<text x="' + x.toFixed(1) + '" y="' + (y + 26) + '" text-anchor="middle" font-size="14" fill="var(--c-text-muted)">' +
        escNum(v) + '</text>';
    }

    var dots = points.map(function (p) {
      var x = toX(p.value);
      return '<circle cx="' + x.toFixed(1) + '" cy="' + y + '" r="6" fill="#E53935"></circle>' +
        '<text x="' + x.toFixed(1) + '" y="' + (y - 16) + '" text-anchor="middle" font-size="15" font-weight="600" fill="var(--c-text)">' +
        esc(p.label) + '(' + escNum(p.value) + ')</text>';
    }).join('');

    return '<figure class="task-visual">' +
      '<svg viewBox="0 0 ' + width + ' 120" role="img" aria-label="Координатная прямая" style="max-width:100%">' +
      '<defs><marker id="vis-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">' +
      '<path d="M0,0 L8,3 L0,6 Z" fill="var(--c-text-muted)"></path></marker></defs>' +
      '<line x1="' + left + '" y1="' + y + '" x2="' + right + '" y2="' + y +
      '" stroke="var(--c-text-muted)" stroke-width="1.8" marker-end="url(#vis-arrow)"></line>' +
      marks + dots + '</svg></figure>';
  }

  function detectPie(text) {
    if (!/кругов[аоуы][йеюая]?\s+диаграмм/i.test(text)) return null;
    var re = /([A-Za-zА-Яа-яЁё][\wА-Яа-яЁё .-]{1,40}?)\s*[-–—:]\s*(\d{1,3}(?:[.,]\d+)?)\s*%/g;
    var parts = [];
    var match;
    while ((match = re.exec(text)) !== null) {
      var label = match[1].trim().replace(/[.\s]+$/, '');
      if (label.length >= 2) parts.push({ label: label, value: Number(match[2].replace(',', '.')) });
    }
    if (parts.length < 2) return null;
    var sum = parts.reduce(function (s, p) { return s + p.value; }, 0);
    if (sum < 80 || sum > 120) return null;
    return parts;
  }

  function detectNumberLine(text) {
    if (!/координатн[а-яё]*\s+(прямой|оси|прямую|ось)/i.test(text)) return null;
    var re = /([A-ZА-Я])\s*\(\s*([-–—−]?\d{1,4}(?:[.,]\d+)?)\s*\)/g;
    var points = [];
    var match;
    while ((match = re.exec(text)) !== null) {
      points.push({
        label: match[1],
        value: Number(match[2].replace(',', '.').replace(/[–—−]/, '-'))
      });
    }
    if (points.length < 2 || points.length > 16) return null;
    return points;
  }

  function taskVisualHtml(task) {
    var text = String(task.condition || '') + '\n' + String(task.solution || '');

    var pie = detectPie(text);
    if (pie) return pieSvg(pie);

    var line = detectNumberLine(text);
    if (line) return numberLineSvg(line);

    return '';
  }

  function byId(id) { return document.getElementById(id); }

  function plural(n, one, few, many) {
    var m10 = n % 10;
    var m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }

  function tasksWord(n) { return n + ' ' + plural(n, 'задание', 'задания', 'заданий'); }
  function booksWord(n) { return n + ' ' + plural(n, 'учебник', 'учебника', 'учебников'); }

  // текст с переносами -> абзацы (с дробями)
  function textToHtml(text) {
    return String(text || '')
      .split(/\n+/)
      .map(function (line) { return line.trim(); })
      .filter(Boolean)
      .map(function (line) { return '<p>' + mathHtml(line) + '</p>'; })
      .join('');
  }

  // подсветка первого совпадения запроса в тексте
  function highlight(text, query) {
    var q = String(query || '').trim();
    if (!q) return esc(text);
    var idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return esc(text);
    return esc(text.slice(0, idx)) +
      '<mark>' + esc(text.slice(idx, idx + q.length)) + '</mark>' +
      esc(text.slice(idx + q.length));
  }

  // короткий фрагмент условия вокруг совпадения
  function snippet(text, query, len) {
    text = String(text || '');
    len = len || 150;
    var q = String(query || '').trim().toLowerCase();
    var idx = q ? text.toLowerCase().indexOf(q) : 0;
    if (idx === -1) idx = 0;
    var start = Math.max(0, idx - 40);
    var cut = text.slice(start, start + len);
    return (start > 0 ? '…' : '') +
      (q ? highlight(cut, query) : esc(cut)) +
      (start + len < text.length ? '…' : '');
  }

  function debounce(fn, ms) {
    var timer = 0;
    return function () {
      var args = arguments;
      var self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  }

  // мягкое появление списков и карточек: задержка задаётся через --stagger,
  // сама анимация отключается правилом prefers-reduced-motion в CSS.
  function staggerList(container, selector) {
    if (!container) return;
    var items = container.querySelectorAll(selector);
    for (var i = 0; i < items.length && i < 24; i++) {
      items[i].style.setProperty('--stagger', String(i));
      items[i].classList.add('is-stagger');
    }
  }

  // скелетон на время загрузки данных: каталог, сетка, задача
  function routeSkeleton(parts) {
    var html = '<div class="sk-page" aria-hidden="true">' +
      '<div class="sk sk-heading"></div><div class="sk sk-subline"></div>';
    if (parts.length >= 4) {
      html += '<div class="sk sk-block"></div><div class="sk sk-block sk-block--short"></div>' +
        '<div class="sk sk-block"></div>';
    } else {
      var taskGrid = parts.length === 3;
      html += '<div class="sk-grid' + (taskGrid ? ' sk-grid--tasks' : '') + '">';
      var count = taskGrid ? 24 : 6;
      for (var i = 0; i < count; i++) {
        html += '<span class="sk ' + (taskGrid ? 'sk-cell' : 'sk-card') + '"></span>';
      }
      html += '</div>';
    }
    return html + '</div>';
  }

  function formatDate(ts) {
    try {
      return new Date(ts).toLocaleString('ru-RU', {
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
      });
    } catch (err) { return ''; }
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
      document.body.removeChild(area);
      ok ? resolve() : reject(new Error('copy failed'));
    });
  }

  var toastTimer = 0;
  function showToast(message) {
    toastEl.textContent = message;
    toastEl.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('is-visible'); }, 2400);
  }

  // кнопка «скопировать»: кратко превращается в «Скопировано»
  function flashCopied(btn) {
    if (!btn || btn.classList.contains('is-copied')) return;
    var label = btn.querySelector('span:last-child');
    var icon = btn.querySelector('.icon');
    btn.classList.add('is-copied');
    if (label) label.textContent = 'Скопировано';
    if (icon) { icon.classList.remove('i-copy'); icon.classList.add('i-check'); }
    setTimeout(function () {
      btn.classList.remove('is-copied');
      if (label) label.textContent = 'Скопировать ссылку';
      if (icon) { icon.classList.add('i-copy'); icon.classList.remove('i-check'); }
    }, 1600);
  }

  /* =========================================================
     localStorage
     ========================================================= */

  function storeGet(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (err) { return fallback; }
  }

  function storeSet(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (err) { /* приватный режим */ }
  }

  // записи без класса — из старых версий приложения (тогда был только 6 класс)
  function entryKey(entry) {
    return (entry.grade || DEFAULT_GRADE) + '/' + entry.subject + '/' + entry.book + '/' + entry.number;
  }

  function getBookmarks() { return storeGet(LS_BOOKMARKS, []); }

  function isBookmarked(entry) {
    return getBookmarks().some(function (b) { return entryKey(b) === entryKey(entry); });
  }

  function toggleBookmark(entry) {
    var list = getBookmarks();
    var key = entryKey(entry);
    var exists = list.some(function (b) { return entryKey(b) === key; });
    if (exists) {
      list = list.filter(function (b) { return entryKey(b) !== key; });
    } else {
      entry.addedAt = Date.now();
      list.unshift(entry);
    }
    storeSet(LS_BOOKMARKS, list);
    return !exists;
  }

  function removeBookmark(key) {
    storeSet(LS_BOOKMARKS, getBookmarks().filter(function (b) { return entryKey(b) !== key; }));
  }

  function addHistory(entry) {
    var list = storeGet(LS_HISTORY, []).filter(function (x) { return entryKey(x) !== entryKey(entry); });
    entry.viewedAt = Date.now();
    list.unshift(entry);
    storeSet(LS_HISTORY, list.slice(0, 20));
  }

  /* =========================================================
     данные
     ========================================================= */

  function getJSON(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    });
  }

  function loadCatalog() {
    if (catalog) return Promise.resolve(catalog);
    return getJSON(DATA_DIR + 'catalog.json').then(function (data) {
      catalog = data;
      return data;
    });
  }

  function loadStats() {
    return getJSON(DATA_DIR + 'stats.json').catch(function () { return null; });
  }

  function loadBook(file) {
    if (bookCache[file]) return Promise.resolve(bookCache[file]);
    return getJSON(DATA_DIR + file).then(function (data) {
      bookCache[file] = data;
      return data;
    });
  }

  function findGrade(cat, id) {
    var list = (cat && cat.grades) || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) return list[i];
    }
    return null;
  }

  function findSubject(grade, id) {
    var list = (grade && grade.subjects) || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) return list[i];
    }
    return null;
  }

  function findBook(subject, id) {
    return (subject.textbooks || []).filter(function (b) { return b.id === id; })[0] || null;
  }

  // облегчённый индекс: 24 МБ вместо загрузки всех 185 учебников
  // (около 190 МБ). Поля короткие: b — книга, n — номер, g/s — класс и
  // предмет, st/bt — названия, c — условие.
  function loadSearchIndex() {
    if (searchIndex) return Promise.resolve(searchIndex);
    return getJSON(DATA_DIR + 'search-index.json').then(function (data) {
      searchIndex = (data && data.tasks) || [];
      return searchIndex;
    });
  }

  function numberParts(num) {
    return String(num).split(/[.\-]/).map(function (part) { return parseInt(part, 10) || 0; });
  }

  function compareTaskNumbers(a, b) {
    var pa = numberParts(a.number);
    var pb = numberParts(b.number);
    var len = Math.max(pa.length, pb.length);
    for (var i = 0; i < len; i++) {
      var diff = (pa[i] || 0) - (pb[i] || 0);
      if (diff) return diff;
    }
    var sa = String(a.number);
    var sb = String(b.number);
    return sa < sb ? -1 : (sa > sb ? 1 : 0);
  }

  function sortedTasks(book) {
    return (book.tasks || []).slice().sort(compareTaskNumbers);
  }

  /* =========================================================
     тема
     ========================================================= */

  var root = document.documentElement;
  var themeFadeTimer = 0;

  function applyTheme(theme) {
    root.classList.add('theme-fade');
    root.setAttribute('data-theme', theme);
    clearTimeout(themeFadeTimer);
    themeFadeTimer = setTimeout(function () { root.classList.remove('theme-fade'); }, 400);
    var btn = byId('theme-toggle');
    if (!btn) return;
    var dark = theme === 'dark';
    btn.setAttribute('aria-label', dark ? 'Включить светлую тему' : 'Включить тёмную тему');
    var icon = btn.querySelector('.icon');
    icon.classList.toggle('i-sun', dark);
    icon.classList.toggle('i-moon', !dark);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', dark ? '#1A1A1A' : '#1AA3A3');
  }

  var storedTheme = null;
  try { storedTheme = localStorage.getItem(LS_THEME); } catch (err) { /* ignore */ }
  applyTheme(storedTheme || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));

  byId('theme-toggle').addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(LS_THEME, next); } catch (err) { /* ignore */ }
    applyTheme(next);
  });

  /* =========================================================
     роутинг
     ========================================================= */

  function currentParts() {
    return location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  }

  function route() {
    var parts = currentParts();
    var token = ++renderToken;
    currentTask = null;
    clearJsonLd();
    updateBottomNav(parts);

    // при любой смене маршрута очищаем строку поиска
    if (document.activeElement !== searchInput && searchInput.value) {
      searchInput.value = '';
      searchClear.hidden = true;
    }

    screenEl.classList.add('screen--out');

    setTimeout(function () {
      if (token !== renderToken) return;
      screenEl.innerHTML = routeSkeleton(parts);
      screenEl.classList.remove('screen--out');
      Promise.resolve(renderRoute(parts, token)).then(function () {
        if (token !== renderToken) return;
        staggerList(screenEl, '.subject-card, .bookcard, .task-cell, .list-item, .comment-item');
        screenEl.classList.remove('screen--out');
      }).catch(function (err) {
        if (token !== renderToken) return;
        screenEl.innerHTML = '<h1 class="panel-title">Не получилось</h1>' +
          '<p class="error">Не удалось загрузить данные: ' + esc(err.message) + '</p>';
        screenEl.classList.remove('screen--out');
      });
    }, reduced ? 0 : 150);
  }

  function renderRoute(parts, token) {
    if (!parts.length) return renderHome(token);

    if (parts[0] === 'favorites') return renderList('favorites');
    if (parts[0] === 'recent') return renderList('recent');
    if (parts[0] === 'search') {
      var query = parts.slice(1).join('/');
      if (query && searchInput.value !== query) {
        searchInput.value = query;
        searchClear.hidden = false;
      }
      return renderSearchResults(query);
    }

    return loadCatalog().then(function (cat) {
      if (token !== renderToken) return;

      var grade = findGrade(cat, parts[0]);
      if (!grade) {
        // старые ссылки без класса: #/math/... ведут на 6 класс
        var legacySubject = findSubject(findGrade(cat, DEFAULT_GRADE), parts[0]);
        if (legacySubject) {
          location.replace('#/' + DEFAULT_GRADE + '/' + parts.map(encodeURIComponent).join('/'));
          return;
        }
        return renderNotFound('Такого раздела нет.');
      }

      var rest = parts.slice(1);
      if (!rest.length) return renderGrade(grade, token);

      var subject = findSubject(grade, rest[0]);
      if (!subject) return renderNotFound('Такого предмета нет.');
      if (subject.active === false) return renderNotFound('Этот предмет пока не заполнен.');

      // предмет с одним учебником открываем сразу на сетке
      if (rest.length === 1) {
        var books = subject.textbooks || [];
        if (books.length === 1) {
          location.replace('#/' + grade.id + '/' + subject.id + '/' + books[0].id);
          return;
        }
        return renderSubject(grade, subject);
      }

      var bookRaw = rest[1];
      var listQuery = '';
      var qi = bookRaw.indexOf('?');
      if (qi !== -1) {
        listQuery = new URLSearchParams(bookRaw.slice(qi + 1)).get('q') || '';
        bookRaw = bookRaw.slice(0, qi);
      }
      var bookRef = findBook(subject, bookRaw);
      if (!bookRef) return renderNotFound('Такого учебника нет.');

      if (rest.length === 2) return renderTasks(grade, subject, bookRef, token, listQuery);

      return renderTask(grade, subject, bookRef, rest[2].split('?')[0], token);
    });
  }

  function renderNotFound(message) {
    document.title = 'Ничего не найдено — ГДЗ НЭЛ';
    screenEl.innerHTML = '<h1 class="panel-title">Ничего не найдено</h1>' +
      '<p class="panel-sub">' + esc(message) + '</p>' +
      '<p><a class="btn btn-outline" href="#/"><span class="icon i-arrow-left" aria-hidden="true"></span><span>К классам</span></a></p>';
    return Promise.resolve();
  }

  /* =========================================================
     экран: классы
     ========================================================= */

  function renderHome(token) {
    return Promise.all([loadCatalog(), loadStats()]).then(function (res) {
      if (token !== renderToken) return;
      var cat = res[0];
      var stats = res[1];

      document.title = 'ГДЗ НЭЛ — готовые домашние задания';

      var html = '<h1 class="panel-title">Классы</h1>' +
        '<p class="panel-sub">2026–2027 учебный год. Выбери класс, затем предмет и номер задания. Обычные ГДЗ открыты без входа.</p>' +
        '<div class="subject-grid">';

      (cat.grades || []).forEach(function (g) {
        var gstats = stats && stats.grades && stats.grades[g.id] ? stats.grades[g.id] : null;
        var subjects = (g.subjects || []).length;
        var icon = '<span class="subject-icon"><span class="icon i-book" aria-hidden="true"></span></span>';

        if (g.active === false) {
          html += '<div class="subject-card is-soon">' + icon +
            '<span class="subject-soon">собирается</span>' +
            '<span class="subject-name">' + esc(g.title) + '</span>' +
            '<span class="subject-meta">материалы готовятся</span></div>';
        } else {
          html += '<a class="subject-card" href="#/' + esc(g.id) + '">' + icon +
            '<span class="subject-name">' + esc(g.title) + '</span>' +
            '<span class="subject-meta">' + subjects + ' ' + plural(subjects, 'предмет', 'предмета', 'предметов') + '</span>' +
            '<span class="subject-foot"><span>' + (gstats ? tasksWord(gstats.total) : 'задания') + '</span>' +
            '<span class="icon i-chevron-right" aria-hidden="true"></span></span></a>';
        }
      });

      html += '</div>';
      screenEl.innerHTML = html;
    });
  }

  /* =========================================================
     экран: предметы класса
     ========================================================= */

  function renderGrade(grade, token) {
    return loadStats().then(function (stats) {
      if (token !== renderToken) return;

      var crumbs = '<nav class="crumbs" aria-label="Навигация">' +
        '<a href="#/">Главная</a><span class="crumb-sep">/</span>' +
        '<span>' + esc(grade.title) + '</span></nav>';

      document.title = grade.title + ' — ГДЗ НЭЛ';

      if (grade.active === false) {
        screenEl.innerHTML = crumbs +
          '<h1 class="panel-title">' + esc(grade.title) + '</h1>' +
          '<p class="panel-sub">Материалы для этого класса ещё собираются. Мы не выдумываем решения: задания появятся здесь, когда их соберут и проверят.</p>' +
          '<p><a class="btn btn-outline" href="#/"><span class="icon i-arrow-left" aria-hidden="true"></span><span>К классам</span></a></p>';
        return;
      }

      var gstats = stats && stats.grades && stats.grades[grade.id] ? stats.grades[grade.id] : null;

      var html = crumbs +
        '<h1 class="panel-title">' + esc(grade.title) + '</h1>' +
        '<p class="panel-sub">Выбери предмет, затем учебник и номер задания.</p>' +
        '<div class="subject-grid">';

      (grade.subjects || []).forEach(function (s) {
        var books = (s.textbooks || []).length;
        var count = gstats && gstats.subjects && gstats.subjects[s.id] ? gstats.subjects[s.id].tasks : null;
        var icon = '<span class="subject-icon"><span class="icon i-' + esc(s.icon || s.id) + '" aria-hidden="true"></span></span>';
        var meta = '<span class="subject-meta">' + booksWord(books) + '</span>';
        var foot = '<span class="subject-foot"><span>' +
          (count === null ? 'задания' : tasksWord(count)) +
          '</span><span class="icon i-chevron-right" aria-hidden="true"></span></span>';

        if (s.active === false) {
          html += '<div class="subject-card is-soon">' + icon +
            '<span class="subject-soon">скоро</span>' +
            '<span class="subject-name">' + esc(s.title) + '</span>' +
            meta + '<span class="subject-foot"><span>готовится</span></span></div>';
        } else {
          html += '<a class="subject-card" href="#/' + esc(grade.id) + '/' + esc(s.id) + '">' + icon +
            '<span class="subject-name">' + esc(s.title) + '</span>' +
            meta + foot + '</a>';
        }
      });

      html += '</div>';
      screenEl.innerHTML = html;
    });
  }

  /* =========================================================
     экран: учебники
     ========================================================= */

  function renderSubject(grade, subject) {
    return loadStats().then(function (stats) {
      document.title = subject.title + ' — ' + grade.title + ' — ГДЗ НЭЛ';
      var gstats = stats && stats.grades && stats.grades[grade.id] ? stats.grades[grade.id] : null;

      var html = '<nav class="crumbs" aria-label="Навигация">' +
        '<a href="#/">Главная</a><span class="crumb-sep">/</span>' +
        '<a href="#/' + esc(grade.id) + '">' + esc(grade.title) + '</a><span class="crumb-sep">/</span>' +
        '<span>' + esc(subject.title) + '</span></nav>' +
        '<h1 class="panel-title">' + esc(subject.title) + '</h1>' +
        '<p class="panel-sub">Выбери учебник или часть.</p>' +
        '<div class="book-grid">';

      (subject.textbooks || []).forEach(function (b) {
        var partMatch = /Часть\s*(\d)/.exec(b.title);
        var partLabel = partMatch ? ('ч. ' + partMatch[1]) : grade.title;
        var count = null;
        if (gstats && gstats.books && typeof gstats.books[b.file] === 'number') {
          count = gstats.books[b.file];
        }
        html += '<a class="bookcard" href="#/' + esc(grade.id) + '/' + esc(subject.id) + '/' + esc(b.id) + '">' +
          '<span class="bookcover"><span class="icon i-' + esc(subject.icon || subject.id) + '" aria-hidden="true"></span>' +
          '<span class="bookcover-part">' + esc(partLabel) + '</span></span>' +
          '<span class="bookmeta"><h2>' + esc(b.title) + '</h2>' +
          '<p>' + esc(b.author || '') + '</p>' +
          '<p>' + esc(b.year || '') + '</p>' +
          '<span class="bookcount">' + (count === null ? 'открыть задания' : tasksWord(count)) + '</span></span></a>';
      });

      html += '</div>';
      screenEl.innerHTML = html;
    });
  }

  /* =========================================================
     экран: сетка заданий
     ========================================================= */

  function renderTasks(grade, subject, bookRef, token, listQuery) {
    return loadBook(bookRef.file).then(function (book) {
      if (token !== renderToken) return;

      var tasks = sortedTasks(book);
      document.title = bookRef.title + ' — ' + subject.title + ' — ГДЗ НЭЛ';
      setMetaDescription('Задания учебника «' + bookRef.title + '» (' + subject.title + ', ' + grade.title +
        '): решения и ответы. Открывай номер — условия, шаги решения и ответ.');

      var html = '<nav class="crumbs" aria-label="Навигация">' +
        '<a href="#/">Главная</a><span class="crumb-sep">/</span>' +
        '<a href="#/' + esc(grade.id) + '">' + esc(grade.title) + '</a><span class="crumb-sep">/</span>' +
        '<a href="#/' + esc(grade.id) + '/' + esc(subject.id) + '">' + esc(subject.title) + '</a><span class="crumb-sep">/</span>' +
        '<span>' + esc(bookRef.title) + '</span></nav>' +
        '<h1 class="panel-title">' + esc(bookRef.title) + '</h1>' +
        '<p class="panel-sub">' + esc(bookRef.author || '') + '</p>';

      if (!tasks.length) {
        html += '<p class="empty">Задания для этого учебника ещё не загружены.</p>';
        screenEl.innerHTML = html;
        return;
      }

      // группировка по разделам: в сетке — только реально существующие задания
      var groups = [];
      var current = null;
      tasks.forEach(function (t) {
        var name = t.section || (current ? current.name : 'Все задания');
        if (!current || current.name !== name) {
          current = { name: name, tasks: [], count: 0 };
          groups.push(current);
        }
        current.tasks.push(t);
        current.count++;
      });

      var onlyDefault = groups.length === 1 && groups[0].name === 'Все задания';

      html += '<div class="task-toolbar"><span class="task-count" id="task-count">' +
        tasksWord(tasks.length) + ' в ' + esc(bookRef.title) + '</span></div>';

      // чипы разделов
      if (!onlyDefault) {
        html += '<nav class="section-chips" aria-label="Разделы учебника">';
        groups.forEach(function (g, i) {
          html += '<button class="section-chip" type="button" data-target="group-' + i + '">' +
            esc(g.name) + '</button>';
        });
        html += '</nav>';
      }

      groups.forEach(function (g, i) {
        html += '<section class="group" data-group="' + i + '">';
        if (!onlyDefault) {
          html += '<div class="group-head" id="group-' + i + '"><h2>' + esc(g.name) + '</h2>' +
            '<span class="group-count">' + g.count + '</span></div>';
        } else {
          html += '<div class="group-head" id="group-' + i + '"><h2>Все задания</h2></div>';
        }
        html += '<div class="task-grid">';
        g.tasks.forEach(function (t) {
          html += '<a class="task-cell" href="#/' + esc(grade.id) + '/' + esc(subject.id) + '/' + esc(bookRef.id) + '/' +
            encodeURIComponent(t.number) + '" ' +
            'data-number="' + esc(t.number) + '" aria-label="Задание ' + esc(t.number) + '">' +
            '<span>' + esc(t.number) + '</span></a>';
        });
        html += '</div></section>';
      });

      if (!onlyDefault) {
        html += '<div class="next-section"><button class="btn btn-outline btn-sm" id="next-section-btn" type="button">' +
          '<span>Следующий раздел</span><span class="icon i-chevron-down" aria-hidden="true"></span></button></div>';
      }

      screenEl.innerHTML = html;

      // фильтр из адресной строки (?q=12) — такой ссылкой можно поделиться
      if (listQuery) {
        searchInput.value = listQuery;
        searchClear.hidden = false;
        applyTaskFilter(listQuery.replace(',', '.'));
      }

      // чипы: скролл к разделу
      Array.prototype.forEach.call(screenEl.querySelectorAll('.section-chip'), function (chip) {
        chip.addEventListener('click', function () {
          var target = byId(chip.getAttribute('data-target'));
          if (target) target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
        });
      });

      // «следующий раздел»: ищем заголовок ниже текущего скролла
      var nextBtn = byId('next-section-btn');
      if (nextBtn) {
        nextBtn.addEventListener('click', function () {
          var heads = screenEl.querySelectorAll('.group-head');
          var y = window.scrollY + 90;
          var target = null;
          Array.prototype.forEach.call(heads, function (head) {
            if (!target && head.getBoundingClientRect().top + window.scrollY > y) target = head;
          });
          if (target) {
            target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
          } else {
            window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
          }
        });
      }
    });
  }

  // локальный фильтр сетки по номеру (без перезагрузки)
  function applyTaskFilter(query) {
    var cells = screenEl.querySelectorAll('.task-cell[data-number]');
    if (!cells.length) return;

    var visible = 0;
    Array.prototype.forEach.call(cells, function (cell) {
      var show = cell.getAttribute('data-number').indexOf(query) === 0;
      cell.hidden = !show;
      if (show) visible++;
    });

    Array.prototype.forEach.call(screenEl.querySelectorAll('.group'), function (group) {
      group.hidden = !group.querySelector('.task-cell[data-number]:not([hidden])');
    });

    var counter = byId('task-count');
    if (counter) {
      counter.textContent = visible
        ? 'найдено ' + tasksWord(visible)
        : 'ничего не найдено — очисти поиск';
    }
  }

  /* =========================================================
     экран: задание
     ========================================================= */

  function renderTask(grade, subject, bookRef, number, token) {
    return loadBook(bookRef.file).then(function (book) {
      if (token !== renderToken) return;

      var tasks = sortedTasks(book);
      var index = -1;
      tasks.forEach(function (t, i) { if (String(t.number) === String(number)) index = i; });

      if (index === -1) return renderNotFound('Задания с таким номером нет в этом учебнике.');

      var task = tasks[index];
      var prev = index > 0 ? tasks[index - 1] : null;
      var next = index < tasks.length - 1 ? tasks[index + 1] : null;

      var base = '#/' + grade.id + '/' + subject.id + '/' + bookRef.id;
      var taskLabel = 'Задание ' + task.number;

      currentTask = {
        prev: prev ? base + '/' + prev.number : null,
        next: next ? base + '/' + next.number : null,
        back: base
      };

      document.title = taskLabel + ' — ' + subject.title + ' — ГДЗ НЭЛ';

      var entry = {
        grade: grade.id,
        subject: subject.id,
        book: bookRef.id,
        number: task.number,
        title: subject.title + ' · ' + bookRef.title + ' · №' + task.number,
        snippet: String(task.condition || '').slice(0, 160)
      };
      addHistory(entry);

      var bookmarked = isBookmarked(entry);

      var html = '<nav class="crumbs" aria-label="Навигация">' +
        '<a href="#/">Главная</a><span class="crumb-sep">/</span>' +
        '<a href="#/' + esc(grade.id) + '">' + esc(grade.title) + '</a><span class="crumb-sep">/</span>' +
        '<a href="#/' + esc(grade.id) + '/' + esc(subject.id) + '">' + esc(subject.title) + '</a><span class="crumb-sep">/</span>' +
        '<a href="' + base + '">' + esc(bookRef.title) + '</a><span class="crumb-sep">/</span>' +
        '<span>' + taskLabel + '</span></nav>' +
        '<div class="task-view">' +
        '<h1 class="panel-title">' + taskLabel + '</h1>' +

        '<section class="task-block task-block--cond">' +
        '<p class="task-label">Условие</p>' +
        '<div class="task-text">' + textToHtml(task.condition) + '</div>' +
        '</section>' +

        solutionSectionHtml(task) +

        (String(task.answer || '').trim()
          ? '<section class="task-block task-block--answer">' +
            '<p class="task-label">Ответ</p>' +
            '<div class="answer">' + textToHtml(task.answer) + '</div>' +
            '</section>'
          : '') +

        '<div class="task-actions no-print">' +
        '<button class="btn btn-outline btn-sm" id="bm-btn" type="button" aria-pressed="' + bookmarked + '">' +
        '<span class="icon ' + (bookmarked ? 'i-star-filled' : 'i-star') + '" aria-hidden="true"></span>' +
        '<span id="bm-label">' + (bookmarked ? 'В избранном' : 'В избранное') + '</span></button>' +
        '<button class="btn btn-outline btn-sm" id="share-btn" type="button">' +
        '<span class="icon i-share" aria-hidden="true"></span><span>Поделиться</span></button>' +
        '<button class="btn btn-outline btn-sm" id="copy-btn" type="button">' +
        '<span class="icon i-copy" aria-hidden="true"></span><span>Скопировать ссылку</span></button>' +
        '<a class="btn btn-outline btn-sm" id="report-link" href="' + reportHref(entry) + '">' +
        '<span class="icon i-flag" aria-hidden="true"></span><span>Сообщить об ошибке</span></a>' +
        '</div>' +

        '<nav class="task-nav no-print" aria-label="Навигация по заданиям">' +
        (prev
          ? '<a class="btn btn-outline" href="' + base + '/' + prev.number + '">' +
            '<span class="icon i-arrow-left" aria-hidden="true"></span><span>Задание ' + prev.number + '</span></a>'
          : '<span class="btn btn-outline is-disabled" aria-hidden="true">' +
            '<span class="icon i-arrow-left"></span><span>Назад</span></span>') +
        '<a class="btn btn-outline" href="' + base + '">К списку</a>' +
        (next
          ? '<a class="btn btn-outline" href="' + base + '/' + next.number + '">' +
            '<span>Задание ' + next.number + '</span><span class="icon i-arrow-right" aria-hidden="true"></span></a>'
          : '<span class="btn btn-outline is-disabled" aria-hidden="true">' +
            '<span>Вперёд</span><span class="icon i-arrow-right"></span></span>') +
        '</nav>' +

        reviewsSectionHtml() +
        '</div>';

      screenEl.innerHTML = html;

      // столбик: показать/скрыть (Ф4)
      var columnToggle = byId('column-toggle');
      if (columnToggle) {
        columnToggle.addEventListener('click', function () {
          var wrap = byId('math-column-wrap');
          var willShow = wrap.hasAttribute('hidden');
          if (willShow) wrap.removeAttribute('hidden');
          else wrap.setAttribute('hidden', '');
          columnToggle.setAttribute('aria-expanded', String(willShow));
          byId('column-toggle-label').textContent = willShow ? 'Скрыть столбик' : 'Показать столбик';
        });
      }

      // скачать PDF (Ф35)
      var pdfBtn = byId('pdf-btn');
      if (pdfBtn) pdfBtn.addEventListener('click', printTask);

      // SEO: описание и JSON-LD для страницы задания (Ф20)
      var snippetText = String(task.condition || '').replace(/\s+/g, ' ').trim().slice(0, 160);
      setMetaDescription(snippetText
        ? snippetText + ' — решение и ответ, задание ' + task.number + '.'
        : 'Решение и ответ к заданию ' + task.number + ' — ' + subject.title + ', ' + bookRef.title + '.');
      setTaskJsonLd(grade, subject, bookRef, task, snippetText);

      // аналитика: просмотр задания (Ф26)
      if (window.gdzTrack) {
        window.gdzTrack('task_view', { task: bookRef.id + ':' + task.number, grade: grade.id, subject: subject.id });
      }

      // история просмотров в Supabase — для ачивок и профиля (Ф11, Ф16)
      supaPromise.then(function (lib) {
        if (!lib) return;
        lib.getSession().then(function (session) {
          if (!session) return;
          lib.supabase.from('history').upsert({
            user_id: session.user.id,
            task_id: bookRef.id + ':' + task.number,
            viewed_at: new Date().toISOString()
          }, { onConflict: 'user_id,task_id' }).then(function () {
            syncAchievements(lib);
          });
        });
      });

      // избранное
      byId('bm-btn').addEventListener('click', function () {
        var added = toggleBookmark(entry);
        this.setAttribute('aria-pressed', String(added));
        byId('bm-label').textContent = added ? 'В избранном' : 'В избранное';
        var icon = this.querySelector('.icon');
        icon.classList.toggle('i-star', !added);
        icon.classList.toggle('i-star-filled', added);
        showToast(added ? 'Добавлено в избранное' : 'Убрано из избранного');
      });

      // поделиться
      byId('share-btn').addEventListener('click', function () {
        if (navigator.share) {
          navigator.share({ title: entry.title, text: entry.snippet, url: location.href })
            .catch(function () { /* пользователь отменил */ });
          return;
        }
        copyText(location.href).then(function () {
          showToast('Ссылка скопирована');
        }, function () {
          showToast('Не удалось скопировать ссылку');
        });
      });

      // скопировать ссылку (с анимацией «Скопировано», Ф13.9)
      byId('copy-btn').addEventListener('click', function () {
        var btn = this;
        copyText(location.href).then(function () {
          showToast('Ссылка скопирована');
          flashCopied(btn);
        }, function () {
          showToast('Не удалось скопировать ссылку');
        });
      });

      // отзывы к заданию
      renderReviews({ taskId: bookRef.id + ':' + task.number }, token);

      // подсказка о клавишах — один раз
      if (!storeGet(LS_HINT, false)) hintEl.hidden = false;
    });
  }

  // пошаговое решение: каждая строка — шаг
  // если строки уже пронумерованы («1) …», «2) …») — убираем номера,
  // нумерацию рисует нумерованный список (Ф4, Ф29)
  function solutionSteps(solution) {
    var lines = String(solution || '').split(/\n+/)
      .map(function (line) { return line.trim(); })
      .filter(Boolean);
    if (!lines.length) return '';

    var numbered = lines.some(function (line) { return /^1[).]\s+/.test(line); });
    if (numbered) {
      lines = lines.map(function (line) { return line.replace(/^\d{1,2}[).]\s+/, ''); });
    }

    return lines.map(function (line) {
      return '<li class="step-line"><p>' + mathHtml(line) + '</p></li>';
    }).join('');
  }

  // блок решения: пошаговый текст, картинки из источника и «столбик» с переключателем
  function solutionSectionHtml(task) {
    var hasSolution = String(task.solution || '').trim().length > 0;
    var images = Array.isArray(task.images) ? task.images.filter(Boolean) : [];
    var column = String(task.column_solution || '');

    var html = '<section class="task-block" id="solution-block">' +
      '<div class="solution-head">' +
      '<p class="task-label">Решение</p>' +
      (hasSolution || images.length || column
        ? '<button class="btn btn-outline btn-sm" id="pdf-btn" type="button">' +
          '<span class="icon i-download" aria-hidden="true"></span><span>Скачать PDF</span></button>'
        : '') +
      '</div>';

    if (hasSolution) {
      html += '<p class="steps-intro">Выполните действие:</p>' +
        '<ol class="steps-list">' + solutionSteps(task.solution) + '</ol>';
    } else if (!images.length && !column) {
      html += '<p class="empty">Решение появится позже.</p>';
    }

    // SVG-визуализация (круговая диаграмма / координатная прямая) — в блоке решения
    html += taskVisualHtml(task);

    if (images.length) {
      html += '<div class="task-images">' + images.map(function (src, i) {
        return '<a class="task-image" href="' + esc(src) + '" target="_blank" rel="noopener">' +
          '<img src="' + esc(src) + '" alt="Решение задания ' + esc(task.number) +
          ' — страница ' + (i + 1) + '" loading="lazy" decoding="async"></a>';
      }).join('') + '</div>';
    }

    if (column) {
      html += '<div class="column-head">' +
        '<p class="column-title"><span class="icon i-code" aria-hidden="true"></span>Решение столбиком</p>' +
        '<button class="btn btn-outline btn-sm" id="column-toggle" type="button" aria-expanded="true" aria-controls="math-column-wrap">' +
        '<span class="icon i-chevron-down" aria-hidden="true" id="column-toggle-icon"></span>' +
        '<span id="column-toggle-label">Скрыть столбик</span></button>' +
        '</div>' +
        '<div class="math-column-wrap" id="math-column-wrap">' +
        '<pre class="math-column" aria-label="Вычисление в столбик">' + esc(column) + '</pre>' +
        '</div>';
    }

    html += '</section>';
    return html;
  }

  // PDF задания: window.print() по печатным стилям; бесплатным — водяной знак (Ф35)
  function printTask() {
    var layer = byId('print-layer');
    if (!layer) {
      layer = document.createElement('div');
      layer.id = 'print-layer';
      layer.setAttribute('aria-hidden', 'true');
      var stamps = '';
      for (var i = 0; i < 36; i++) stamps += '<span>ГДЗ НЭЛ — бесплатная версия</span>';
      layer.innerHTML = stamps;
      document.body.appendChild(layer);
    }
    document.body.classList.toggle('is-free-print', !premiumActive);
    window.print();
  }

  window.addEventListener('afterprint', function () {
    document.body.classList.remove('is-free-print');
  });

  function reportHref(entry) {
    var subjectLine = 'Ошибка в задании ' + entry.number + ' учебника ' + entry.book;
    var body = 'Ссылка: ' + location.href + '\n\nОпиши ошибку: ';
    return 'mailto:bdfy.tu@yandex.ru?subject=' + encodeURIComponent(subjectLine) + '&body=' + encodeURIComponent(body);
  }

  // ---------- SEO: описание и JSON-LD ----------

  var DEFAULT_DESCRIPTION = document.querySelector('meta[name="description"]')
    ? document.querySelector('meta[name="description"]').getAttribute('content') : '';

  function setMetaDescription(text) {
    var meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute('content', text || DEFAULT_DESCRIPTION);
  }

  function setTaskJsonLd(grade, subject, bookRef, task, snippetText) {
    var el = byId('task-jsonld');
    if (!el) return;
    var pageUrl = 'https://gdz-nel.pages.dev/app/#/' + grade.id + '/' + subject.id + '/' +
      encodeURIComponent(bookRef.id) + '/' + encodeURIComponent(task.number);
    var data = {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'CreativeWork',
          'name': 'Задание ' + task.number + ' — ' + subject.title + ', ' + bookRef.title,
          'description': snippetText || ('Решение и ответ к заданию ' + task.number + '.'),
          'inLanguage': 'ru',
          'url': pageUrl,
          'learningResourceType': 'решение задания',
          'isPartOf': {
            '@type': 'Book',
            'name': bookRef.title,
            'author': { '@type': 'Person', 'name': bookRef.author || 'автор учебника' }
          }
        },
        {
          '@type': 'BreadcrumbList',
          'itemListElement': [
            { '@type': 'ListItem', 'position': 1, 'name': 'Классы', 'item': 'https://gdz-nel.pages.dev/app/' },
            { '@type': 'ListItem', 'position': 2, 'name': grade.title },
            { '@type': 'ListItem', 'position': 3, 'name': subject.title },
            { '@type': 'ListItem', 'position': 4, 'name': bookRef.title },
            { '@type': 'ListItem', 'position': 5, 'name': 'Задание ' + task.number }
          ]
        }
      ]
    };
    el.textContent = JSON.stringify(data);
  }

  var APP_JSONLD = {
    '@context': 'https://schema.org',
    '@type': 'WebApplication',
    'name': 'ГДЗ НЭЛ — готовые домашние задания',
    'url': 'https://gdz-nel.pages.dev/app/',
    'applicationCategory': 'EducationalApplication',
    'operatingSystem': 'Any',
    'inLanguage': 'ru',
    'description': 'Условия, пошаговые решения и ответы для 3–11 классов Новосибирского экономического лицея.',
    'offers': { '@type': 'Offer', 'price': '0', 'priceCurrency': 'RUB' }
  };

  function setAppJsonLd() {
    var el = byId('task-jsonld');
    if (el) el.textContent = JSON.stringify(APP_JSONLD);
  }

  function clearJsonLd() {
    // на главной/поиске не оставляем пустой ld+json: описываем само приложение,
    // иначе после рендера поисковик видит пустой блок (на экране задания его
    // заменяет setTaskJsonLd)
    setAppJsonLd();
    setMetaDescription('');
  }

  // ---------- ачивки: сравнение с локальным списком и тост о новых (Ф16) ----------

  var LS_BADGES = 'gdz-nel-badges';

  function badgeTitleOf(lib, badge) {
    if (lib && lib.badgeTitle) return lib.badgeTitle(badge);
    return String(badge);
  }

  function syncAchievements(lib) {
    if (!lib || !lib.supabase) return;
    lib.supabase.from('achievements').select('badge_type').then(function (res) {
      if (res.error || !res.data) return;
      var known = storeGet(LS_BADGES, null);
      var now = res.data.map(function (r) { return r.badge_type; });
      if (known === null) { storeSet(LS_BADGES, now); return; }
      var fresh = now.filter(function (b) { return known.indexOf(b) === -1; });
      storeSet(LS_BADGES, now);
      if (fresh.length) {
        showToast('Новая ачивка: ' + fresh.map(function (b) { return badgeTitleOf(lib, b); }).join(', '));
      }
    });
  }

  /* =========================================================
     отзывы (Supabase)
     ========================================================= */

  // модуль supabase.js отдаёт window.gdzSupabase; если он не загрузился
  // (офлайн, CDN недоступен) — через 6 секунд сдаёмся и показываем заглушку
  var supaPromise = new Promise(function (resolve) {
    if (window.gdzSupabase) { resolve(window.gdzSupabase); return; }
    var timer = setTimeout(function () { resolve(window.gdzSupabase || null); }, 6000);
    window.addEventListener('gdz-supabase-ready', function () {
      clearTimeout(timer);
      resolve(window.gdzSupabase || null);
    }, { once: true });
  });

  // при входе сверяем ачивки: новые — тостом (Ф16)
  supaPromise.then(function (lib) {
    if (!lib) return;
    lib.getSession().then(function (session) { if (session) syncAchievements(lib); });
  });

  // «ГДЗ+»: статус подписки для PDF без водяного знака (Ф35)
  var premiumActive = false;
  supaPromise.then(function (lib) {
    if (!lib || !lib.isPremiumActive) return;
    lib.getProfile().then(function (profile) {
      premiumActive = lib.isPremiumActive(profile);
    });
  });

  function authHref() {
    return '../auth.html?next=' + encodeURIComponent('app/index.html' + location.hash);
  }

  function starsHtml(n) {
    var html = '';
    for (var i = 1; i <= 5; i++) {
      html += '<span class="icon ' + (i <= n ? 'i-star-filled' : 'i-star') + '" aria-hidden="true"></span>';
    }
    return html;
  }

  function reviewsSectionHtml() {
    return '<section class="reviews no-print" id="reviews" aria-label="Отзывы к заданию">' +
      '<div class="reviews-head"><h2>Отзывы</h2><span class="reviews-count" id="reviews-count"></span></div>' +
      '<div class="reviews-list" id="reviews-list" aria-busy="true">' +
        '<div class="sk sk-review"></div><div class="sk sk-review"></div><div class="sk sk-review"></div>' +
      '</div>' +
      '<div id="review-form-wrap"></div>' +
      '</section>';
  }

  function reviewCard(r, lib, mine) {
    var name = r.username || 'Аноним';
    var initial = String(name).trim().charAt(0).toUpperCase() || 'А';
    var isPro = !!r.author_premium;
    var badge = '';
    if (mine) {
      if (r.ai_status === 'rejected') badge = '<span class="review-mine-badge is-rejected">отклонён</span>';
      else if (r.is_approved) badge = '<span class="review-mine-badge is-approved">опубликован</span>';
      else badge = '<span class="review-mine-badge is-pending">на проверке ИИ</span>';
    }
    return '<article class="review' + (mine ? ' is-mine' : '') + (r.ai_status === 'pending' ? ' is-pending' : '') + '">' +
      '<span class="review-avatar' + (isPro ? ' is-pro' : '') + '" style="background:' + lib.avatarColor(name) + '" aria-hidden="true">' + esc(initial) + '</span>' +
      '<div class="review-body">' +
      '<div class="review-top"><span class="review-name">' + esc(name) + '</span>' +
      (isPro ? '<span class="pro-badge pro-badge--sm" title="Подписка ГДЗ+">PRO</span>' : '') +
      '<span class="review-stars" aria-label="Оценка: ' + r.rating + ' из 5">' + starsHtml(r.rating) + '</span>' +
      badge +
      '<time class="review-date">' + esc(formatDate(r.created_at)) + '</time></div>' +
      '<p class="review-text">' + esc(r.text).replace(/\n/g, '<br>') + '</p>' +
      '</div></article>';
  }

  function renderReviews(ctx, token) {
    var listEl = byId('reviews-list');
    if (!listEl) return;

    supaPromise.then(function (lib) {
      if (token !== renderToken) return;

      if (!lib) {
        listEl.innerHTML = '<p class="empty">Отзывы недоступны: не удалось подключиться к серверу. Проверь интернет и обнови страницу.</p>';
        return;
      }

      var db = lib.supabase;

      async function load() {
        var session = await lib.getSession();

        // RPC отдаёт отзывы + статус «ГДЗ+» автора (чужой профиль RLS не читает)
        var res = await db.rpc('reviews_for_task', { p_task_id: ctx.taskId });
        if (res.error) {
          // миграция ещё не применена — обычный select, без PRO-бейджей
          res = await db.from('reviews').select('*').eq('task_id', ctx.taskId)
            .order('created_at', { ascending: false }).limit(50);
        }
        if (token !== renderToken) return;

        if (res.error) {
          listEl.innerHTML = '<p class="empty">Не получилось загрузить отзывы. Попробуй обновить страницу.</p>';
          return;
        }

        var rows = res.data || [];
        var approved = rows.filter(function (r) { return r.is_approved; });
        var mine = session ? rows.filter(function (r) { return r.user_id === session.user.id; })[0] : null;

        // свой статус берём из профиля (в RPC он тоже есть, но так свежее)
        if (session && lib.getProfile) {
          try {
            var ownProfile = await lib.getProfile();
            var ownPro = lib.isPremiumActive ? lib.isPremiumActive(ownProfile) : false;
            premiumActive = ownPro;
            rows.forEach(function (r) {
              if (r.user_id === session.user.id) r.author_premium = ownPro;
            });
          } catch (e) { /* останутся бейджи из RPC */ }
        }
        if (token !== renderToken) return;

        var countEl = byId('reviews-count');
        if (countEl) {
          countEl.textContent = approved.length
            ? approved.length + ' ' + plural(approved.length, 'отзыв', 'отзыва', 'отзывов')
            : '';
        }

        listEl.innerHTML = approved.length
          ? approved.map(function (r) { return reviewCard(r, lib, false); }).join('')
          : '<p class="empty">Отзывов пока нет. Оставь первый — он поможет другим.</p>';

        renderReviewForm(lib, db, session, mine, ctx, token);
      }
      load();
    });
  }

  function renderReviewForm(lib, db, session, mine, ctx, token) {
    var wrap = byId('review-form-wrap');
    if (!wrap) return;

    if (!session) {
      wrap.innerHTML = '<p class="review-login">Чтобы оставить отзыв, <a href="' + authHref() + '">войди в аккаунт</a>.</p>';
      return;
    }

    if (mine) {
      var note = mine.ai_status === 'rejected'
        ? 'Отклонён модерацией: отзывы с нарушениями правил не публикуются.'
        : 'Опубликован. Спасибо!';
      if (mine.ai_status === 'pending') {
        note += ' ИИ-модератор ещё проверит текст — если найдёт нарушения, отзыв скроют.';
      }
      wrap.innerHTML = '<div class="review-form is-mine-note">' +
        '<p class="review-form-label">Твой отзыв</p>' +
        reviewCard(mine, lib, true) +
        '<p class="review-note">' + note + '</p>' +
        '</div>';
      return;
    }

    var rating = 5;

    wrap.innerHTML =
      '<form class="review-form" id="review-form" novalidate>' +
      '<div class="review-form-row"><span class="review-form-label">Оценка:</span>' +
      '<div class="star-picker" id="star-picker" role="group" aria-label="Оценка от 1 до 5">' +
      [1, 2, 3, 4, 5].map(function (i) {
        return '<button class="star-btn' + (i <= rating ? ' is-on' : '') + '" type="button" data-value="' + i +
          '" aria-pressed="' + (i <= rating) + '" aria-label="' + i + ' из 5">' +
          '<span class="icon i-star-filled" aria-hidden="true"></span></button>';
      }).join('') +
      '</div></div>' +
      '<textarea id="review-text" maxlength="2000" placeholder="Понятно ли решение? Есть замечания? Отзыв проверит ИИ-модератор." required></textarea>' +
      '<div class="review-form-foot">' +
      '<button class="btn btn-primary btn-sm" type="submit" id="review-submit">' +
      '<span class="icon i-send" aria-hidden="true"></span><span>Отправить</span></button>' +
      '<p class="form-status" id="review-status" role="status" aria-live="polite"></p>' +
      '</div></form>';

    var picker = byId('star-picker');
    picker.addEventListener('click', function (event) {
      var btn = event.target.closest ? event.target.closest('.star-btn') : null;
      if (!btn) return;
      rating = Number(btn.getAttribute('data-value'));
      btn.classList.add('is-pop');
      setTimeout(function () { btn.classList.remove('is-pop'); }, 360);
      Array.prototype.forEach.call(picker.querySelectorAll('.star-btn'), function (b) {
        var on = Number(b.getAttribute('data-value')) <= rating;
        b.classList.toggle('is-on', on);
        b.setAttribute('aria-pressed', String(on));
      });
    });

    byId('review-form').addEventListener('submit', function (event) {
      event.preventDefault();

      var textEl = byId('review-text');
      var statusEl = byId('review-status');
      var text = textEl.value.trim();

      statusEl.className = 'form-status';
      statusEl.textContent = '';

      if (text.length < 3) {
        statusEl.className = 'form-status is-err';
        statusEl.textContent = 'Напиши хотя бы пару слов (минимум 3 символа).';
        textEl.focus();
        return;
      }

      var btn = byId('review-submit');
      btn.disabled = true;
      statusEl.textContent = 'Отправляю…';

      db.from('reviews').insert({
        task_id: ctx.taskId,
        user_id: session.user.id,
        rating: rating,
        text: text
      }).select('*').single().then(function (res) {
        btn.disabled = false;
        if (res.error) {
          statusEl.className = 'form-status is-err';
          var message = String(res.error.message || '');
          statusEl.textContent = message.indexOf('row-level security') !== -1
            ? 'Не получилось: возможно, аккаунт заблокирован или отзыв уже отправлен.'
            : 'Не получилось отправить отзыв. Попробуй ещё раз.';
          return;
        }
        showToast('Отзыв успешно добавлен');
        if (res.data) res.data.author_premium = premiumActive;
        renderReviewForm(lib, db, session, res.data, ctx, token);
        // отзыв публикуется сразу — через секунду обновим список принудительно
        setTimeout(function () {
          if (token === renderToken) renderReviews(ctx, token);
        }, 1500);
      }).catch(function () {
        btn.disabled = false;
        statusEl.className = 'form-status is-err';
        statusEl.textContent = 'Нет связи с сервером. Попробуй ещё раз.';
      });
    });
  }

  /* =========================================================
     экран: избранное и недавние
     ========================================================= */

  function renderList(kind) {
    var isFavorites = kind === 'favorites';
    var items = isFavorites ? getBookmarks() : storeGet(LS_HISTORY, []);

    document.title = (isFavorites ? 'Избранное' : 'Недавние') + ' — ГДЗ НЭЛ';

    var html = '<nav class="crumbs" aria-label="Навигация">' +
      '<a href="#/">Главная</a><span class="crumb-sep">/</span>' +
      '<span>' + (isFavorites ? 'Избранное' : 'Недавние') + '</span></nav>' +
      '<h1 class="panel-title">' + (isFavorites ? 'Избранное' : 'Недавние') + '</h1>';

    if (!items.length) {
      html += '<p class="empty">' + (isFavorites
        ? 'Пока пусто. Открой задание и нажми «В избранное» — оно появится здесь.'
        : 'История пуста. Последние 20 просмотренных заданий появятся здесь.') + '</p>';
      screenEl.innerHTML = html;
      return Promise.resolve();
    }

    html += '<p class="panel-sub">' + (isFavorites
      ? 'Сохранённые задания: ' + items.length
      : 'Последние ' + items.length + ' просмотренных заданий') + '</p>' +
      '<button class="btn btn-outline btn-sm" id="list-clear" type="button" style="margin-bottom:16px">' +
      '<span class="icon i-trash" aria-hidden="true"></span><span>' +
      (isFavorites ? 'Очистить избранное' : 'Очистить историю') + '</span></button>' +
      '<ul class="list">';

    items.forEach(function (item, i) {
      var url = '#/' + (item.grade || DEFAULT_GRADE) + '/' + item.subject + '/' + item.book + '/' + item.number;
      html += '<li class="list-item">' +
        '<span class="subject-icon" style="width:40px;height:40px"><span class="icon i-' + esc(item.subject) + '" aria-hidden="true"></span></span>' +
        '<div class="list-main">' +
        '<a class="list-title" href="' + url + '">' + esc(item.title) + '</a>' +
        '<p class="list-snippet">' + esc(item.snippet) + '</p>' +
        '<p class="list-meta">' + (isFavorites
          ? 'добавлено ' + esc(formatDate(item.addedAt))
          : 'просмотрено ' + esc(formatDate(item.viewedAt))) + '</p>' +
        '</div>' +
        '<div class="list-actions">' +
        '<button class="icon-btn icon-btn--sm" type="button" data-remove="' + i + '" ' +
        'aria-label="' + (isFavorites ? 'Убрать из избранного' : 'Убрать из истории') + '">' +
        '<span class="icon i-trash" aria-hidden="true"></span></button>' +
        '</div></li>';
    });

    html += '</ul>';
    screenEl.innerHTML = html;

    byId('list-clear').addEventListener('click', function () {
      storeSet(isFavorites ? LS_BOOKMARKS : LS_HISTORY, []);
      showToast(isFavorites ? 'Избранное очищено' : 'История очищена');
      renderList(kind);
    });

    Array.prototype.forEach.call(screenEl.querySelectorAll('[data-remove]'), function (btn) {
      btn.addEventListener('click', function () {
        var idx = Number(btn.getAttribute('data-remove'));
        var list = isFavorites ? getBookmarks() : storeGet(LS_HISTORY, []);
        list.splice(idx, 1);
        storeSet(isFavorites ? LS_BOOKMARKS : LS_HISTORY, list);
        renderList(kind);
      });
    });

    return Promise.resolve();
  }

  /* =========================================================
     глобальный поиск
     ========================================================= */

  function renderSearchResults(query) {
    var token = ++renderToken;
    currentTask = null;
    screenEl.classList.remove('screen--out');
    window.scrollTo(0, 0);

    if (!query) {
      document.title = 'Поиск — ГДЗ НЭЛ';
      screenEl.innerHTML = '<h1 class="panel-title">Поиск</h1>' +
        '<p class="panel-sub">Введи номер задания или слово из условия — поищу по всем учебникам.</p>';
      return;
    }

    document.title = 'Поиск: ' + query + ' — ГДЗ НЭЛ';
    screenEl.innerHTML = '<h1 class="panel-title">Поиск</h1>' +
      '<p class="panel-sub">Ищу «' + esc(query) + '»…</p>';

    loadSearchIndex().then(function (list) {
      if (token !== renderToken) return;

      var q = query.toLowerCase();
      var isDigits = /^\d+(?:[.,]\d+)?$/.test(query);
      var found = [];
      for (var i = 0; i < list.length && found.length < 50; i++) {
        var item = list[i];
        var hit = isDigits
          ? String(item.n).indexOf(query) === 0
          : String(item.c || '').toLowerCase().indexOf(q) !== -1;
        if (hit) found.push(item);
      }

      var html = '<h1 class="panel-title">Поиск</h1>' +
        '<p class="panel-sub">' + (found.length
          ? 'Нашлось: ' + tasksWord(found.length) + (found.length === 50 ? ' (первые 50)' : '')
          : 'Ничего не найдено по запросу «' + esc(query) + '»') +
        ' · <a href="../search.html?q=' + encodeURIComponent(query) + '">расширенный поиск</a></p>';

      if (!found.length) {
        html += '<p class="empty">Попробуй другой номер или слово из условия.</p>';
      } else {
        html += '<ul class="list">';
        found.forEach(function (item) {
          var url = '#/' + item.g + '/' + item.s + '/' + item.b + '/' + item.n;
          html += '<li class="list-item">' +
            '<span class="subject-icon" style="width:40px;height:40px"><span class="icon i-' + esc(item.s) + '" aria-hidden="true"></span></span>' +
            '<div class="list-main">' +
            '<a class="list-title" href="' + url + '">' + esc(item.st + ' · ' + item.bt + ' · №' + item.n) + '</a>' +
            '<p class="list-snippet">' + snippet(item.c, isDigits ? '' : query) + '</p>' +
            '</div>' +
            '<div class="list-actions"><span class="icon i-chevron-right" aria-hidden="true"></span></div></li>';
        });
        html += '</ul>';
      }

      // аналитика: поисковый запрос (Ф26)
      if (window.gdzTrack) window.gdzTrack('search', { q: query, found: found.length });

      screenEl.innerHTML = html;
      staggerList(screenEl, '.list-item');
    }).catch(function () {
      if (token !== renderToken) return;
      screenEl.innerHTML = '<h1 class="panel-title">Поиск</h1>' +
        '<p class="empty">Не получилось загрузить поисковый индекс. Проверь соединение и попробуй ещё раз.</p>';
    });
  }

  /* =========================================================
     поиск, клавиатура, свайпы
     ========================================================= */

  var onSearchInput = debounce(function () {
    var query = searchInput.value.trim();
    searchClear.hidden = !query;

    if (!query) {
      var clean = currentParts().map(function (p) { return String(p).split('?')[0]; });
      history.replaceState(null, '', '#/' + clean.map(encodeURIComponent).join('/'));
      route();
      return;
    }

    var parts = currentParts();
    // на сетке заданий: цифры фильтруют номера, текст ищется глобально
    if (parts.length === 3 && /^\d+(?:[.,]\d+)?$/.test(query)) {
      applyTaskFilter(query.replace(',', '.'));
      // фильтр отражаем в адресной строке — ссылкой можно поделиться (Ф3.13)
      var cleanParts = parts.map(function (p) { return String(p).split('?')[0]; });
      history.replaceState(null, '', '#/' + cleanParts.map(encodeURIComponent).join('/') +
        '?q=' + encodeURIComponent(query));
      return;
    }
    history.replaceState(null, '', '#/search/' + encodeURIComponent(query));
    renderSearchResults(query);
  }, 300);

  searchInput.addEventListener('input', onSearchInput);

  searchClear.addEventListener('click', function () {
    searchInput.value = '';
    searchClear.hidden = true;
    var clean = currentParts().map(function (p) { return String(p).split('?')[0]; });
    history.replaceState(null, '', '#/' + clean.map(encodeURIComponent).join('/'));
    searchInput.focus();
    route();
  });

  // на телефоне поиск разворачивается кнопкой
  byId('search-toggle').addEventListener('click', function () {
    headerEl.classList.toggle('is-search-open');
    if (headerEl.classList.contains('is-search-open')) searchInput.focus();
  });

  // клавиатура: ← → Esc на экране задания
  document.addEventListener('keydown', function (event) {
    var tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      if (event.key === 'Escape' && event.target === searchInput) {
        searchInput.value = '';
        searchClear.hidden = true;
        searchInput.blur();
        route();
      }
      return;
    }

    // «/» фокусирует поиск (Ф13.8)
    if (event.key === '/') {
      event.preventDefault();
      headerEl.classList.add('is-search-open');
      searchInput.focus();
      return;
    }

    if (!currentTask) return;

    if (event.key === 'ArrowLeft' && currentTask.prev) {
      location.hash = currentTask.prev;
    } else if (event.key === 'ArrowRight' && currentTask.next) {
      location.hash = currentTask.next;
    } else if (event.key === 'Escape') {
      location.hash = currentTask.back;
    }
  });

  // свайпы на экране задания
  var touchStart = null;
  screenEl.addEventListener('touchstart', function (event) {
    if (event.touches.length === 1) {
      touchStart = { x: event.touches[0].clientX, y: event.touches[0].clientY };
    }
  }, { passive: true });

  screenEl.addEventListener('touchend', function (event) {
    if (!touchStart || !event.changedTouches.length || !currentTask) {
      touchStart = null;
      return;
    }
    var dx = event.changedTouches[0].clientX - touchStart.x;
    var dy = event.changedTouches[0].clientY - touchStart.y;
    touchStart = null;
    if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy)) return;

    if (dx < 0 && currentTask.next) location.hash = currentTask.next;
    if (dx > 0 && currentTask.prev) location.hash = currentTask.prev;
  }, { passive: true });

  // подсказка о клавишах
  byId('hint-close').addEventListener('click', function () {
    hintEl.hidden = true;
    storeSet(LS_HINT, true);
  });

  /* =========================================================
     мелочи: тень шапки, прогресс, «наверх», офлайн, обновление
     ========================================================= */

  var toTopBtn = byId('to-top');
  var progressBar = byId('read-progress');

  var onScroll = function () {
    headerEl.classList.toggle('is-stuck', window.scrollY > 6);
    if (toTopBtn) toTopBtn.hidden = window.scrollY < 600;
    if (progressBar) {
      var doc = document.documentElement;
      var max = doc.scrollHeight - window.innerHeight;
      progressBar.style.width = max > 0 ? Math.min(100, (window.scrollY / max) * 100) + '%' : '0%';
    }
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // кнопка «наверх» (Ф3.9, 13.2)
  if (toTopBtn) {
    toTopBtn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
    });
  }

  // активный пункт нижней навигации (Ф14)
  function updateBottomNav(parts) {
    var nav = byId('bottom-nav');
    if (!nav) return;
    var key = !parts.length ? 'home'
      : (parts[0] === 'favorites' ? 'favorites'
        : (parts[0] === 'recent' ? 'recent'
          : (parts[0] === 'search' ? 'search' : '')));
    Array.prototype.forEach.call(nav.querySelectorAll('[data-nav]'), function (el) {
      el.classList.toggle('is-active', el.getAttribute('data-nav') === key);
    });
  }

  var navSearchBtn = byId('nav-search');
  if (navSearchBtn) {
    navSearchBtn.addEventListener('click', function () {
      headerEl.classList.add('is-search-open');
      window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
      searchInput.focus();
    });
  }

  // офлайн-плашка (Ф15.7)
  var offlineBar = byId('offline-bar');
  function updateOnline() {
    if (!offlineBar) return;
    offlineBar.hidden = navigator.onLine;
  }
  window.addEventListener('online', updateOnline);
  window.addEventListener('offline', updateOnline);
  updateOnline();

  // ripple и лёгкая вибрация на кликах (Ф13.1, 13.4)
  document.addEventListener('pointerdown', function (event) {
    var el = event.target && event.target.closest ? event.target.closest('.task-cell, .btn, .section-chip') : null;
    if (!el || reduced) return;
    if (navigator.vibrate) { try { navigator.vibrate(8); } catch (err) { /* ignore */ } }
    var rect = el.getBoundingClientRect();
    var ripple = document.createElement('span');
    ripple.className = 'ripple';
    ripple.style.left = (event.clientX - rect.left) + 'px';
    ripple.style.top = (event.clientY - rect.top) + 'px';
    el.appendChild(ripple);
    setTimeout(function () { if (ripple.parentNode) ripple.parentNode.removeChild(ripple); }, 520);
  });

  // сервис-воркер: офлайн, версии и кнопка «обновить приложение» (Ф15)
  var swUpdateBox = byId('sw-update');
  var swUpdateBtn = byId('sw-update-btn');
  var swReg = null;
  var swReloading = false;

  function showSwUpdate() {
    if (swUpdateBox) swUpdateBox.hidden = false;
  }

  if ('serviceWorker' in navigator && location.protocol.indexOf('http') === 0) {
    var hadController = !!navigator.serviceWorker.controller;

    navigator.serviceWorker.addEventListener('controllerchange', function () {
      if (!hadController || swReloading) return;
      swReloading = true;
      location.reload();
    });

    window.addEventListener('load', function () {
      navigator.serviceWorker.register('service-worker.js').then(function (reg) {
        swReg = reg;
        if (reg.waiting) showSwUpdate();
        reg.addEventListener('updatefound', function () {
          var worker = reg.installing;
          if (!worker) return;
          worker.addEventListener('statechange', function () {
            if (worker.state === 'installed' && navigator.serviceWorker.controller) showSwUpdate();
          });
        });
      }).catch(function () { /* ещё не собран */ });
    });

    if (swUpdateBtn) {
      swUpdateBtn.addEventListener('click', function () {
        var waiting = swReg && swReg.waiting;
        if (waiting) waiting.postMessage({ type: 'SKIP_WAITING' });
        else location.reload();
        swUpdateBtn.disabled = true;
      });
    }
  }

  /* =========================================================
     старт
     ========================================================= */

  window.addEventListener('hashchange', route);
  route();

  // визуализации доступны автотестам (Ф23): SVG-диаграммы по тексту задачи
  window.gdzVisuals = { taskVisualHtml: taskVisualHtml, pieSvg: pieSvg, numberLineSvg: numberLineSvg, fracify: fracify, mathHtml: mathHtml };
})();
