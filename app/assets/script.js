'use strict';

/* =========================================================
   ГДЗ НЭЛ — приложение.
   Хэш-роутинг:
     #/                      список предметов
     #/favorites             избранное
     #/recent                недавние
     #/<subject>             учебники предмета
     #/<subject>/<book>      сетка заданий
     #/<subject>/<book>/<n>  задание
   Данные — app/data/*.json через fetch (кэш в памяти).
   ========================================================= */

(function () {
  var DATA_DIR = 'data/';

  var LS_THEME = 'gdz-nel-theme';
  var LS_BOOKMARKS = 'gdz-nel-bookmarks';
  var LS_HISTORY = 'gdz-nel-history';
  var LS_HINT = 'gdz-nel-hint-done';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var screenEl = document.getElementById('screen');
  var headerEl = document.getElementById('app-header');
  var toastEl = document.getElementById('toast');
  var hintEl = document.getElementById('hint');
  var searchInput = document.getElementById('search-input');
  var searchClear = document.getElementById('search-clear');

  var catalog = null;
  var bookCache = {};     // file -> данные учебника
  var allTasks = null;    // плоский список для поиска
  var renderToken = 0;    // защита от гонок при быстрой навигации
  var currentTask = null; // prev/next для клавиатуры и свайпов

  /* =========================================================
     утилиты
     ========================================================= */

  function esc(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
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

  // текст с переносами -> абзацы
  function textToHtml(text) {
    return String(text || '')
      .split(/\n+/)
      .map(function (line) { return line.trim(); })
      .filter(Boolean)
      .map(function (line) { return '<p>' + esc(line) + '</p>'; })
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

  function entryKey(entry) { return entry.subject + '/' + entry.book + '/' + entry.number; }

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

  function findSubject(id) {
    return loadCatalog().then(function (cat) {
      return cat.subjects.filter(function (s) { return s.id === id; })[0] || null;
    });
  }

  function findBook(subject, id) {
    return (subject.textbooks || []).filter(function (b) { return b.id === id; })[0] || null;
  }

  // все задания всех учебников — для глобального поиска
  function loadAllTasks() {
    if (allTasks) return Promise.resolve(allTasks);
    return loadCatalog().then(function (cat) {
      var jobs = [];
      cat.subjects.forEach(function (s) {
        (s.textbooks || []).forEach(function (b) {
          jobs.push(loadBook(b.file).then(function (book) {
            return (book.tasks || []).map(function (t) {
              return {
                subject: s.id,
                subjectTitle: s.title,
                book: b.id,
                bookTitle: b.title,
                number: t.number,
                condition: t.condition || ''
              };
            });
          }));
        });
      });
      return Promise.all(jobs).then(function (chunks) {
        allTasks = [];
        chunks.forEach(function (chunk) { allTasks = allTasks.concat(chunk); });
        return allTasks;
      });
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

  // пропущенные номера между соседними задачами — для серых зачёркнутых кнопок
  function missingBetween(a, b) {
    var sa = String(a);
    var sb = String(b);
    var out = [];
    var ma = /^(\d+)\.(\d+)$/.exec(sa);
    var mb = /^(\d+)\.(\d+)$/.exec(sb);
    if (ma && mb && ma[1] === mb[1]) {
      for (var k = Number(ma[2]) + 1; k < Number(mb[2]) && out.length < 30; k++) {
        out.push(ma[1] + '.' + k);
      }
      return out;
    }
    if (/^\d+$/.test(sa) && /^\d+$/.test(sb)) {
      for (var k2 = Number(sa) + 1; k2 < Number(sb) && out.length < 30; k2++) {
        out.push(String(k2));
      }
    }
    return out;
  }

  /* =========================================================
     тема
     ========================================================= */

  var root = document.documentElement;

  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
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

    // при любой смене маршрута очищаем строку поиска
    if (document.activeElement !== searchInput && searchInput.value) {
      searchInput.value = '';
      searchClear.hidden = true;
    }

    screenEl.classList.add('screen--out');

    setTimeout(function () {
      if (token !== renderToken) return;
      renderRoute(parts, token).then(function () {
        if (token !== renderToken) return;
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

    return findSubject(parts[0]).then(function (subject) {
      if (token !== renderToken) return;
      if (!subject) return renderNotFound('Такого предмета нет.');
      if (subject.active === false) return renderNotFound('Этот предмет пока не заполнен.');

      // предмет с одним учебником открываем сразу на сетке
      if (parts.length === 1) {
        var books = subject.textbooks || [];
        if (books.length === 1) {
          location.replace('#/' + subject.id + '/' + books[0].id);
          return;
        }
        return renderSubject(subject);
      }

      var bookRef = findBook(subject, parts[1]);
      if (!bookRef) return renderNotFound('Такого учебника нет.');

      if (parts.length === 2) return renderTasks(subject, bookRef, token);

      return renderTask(subject, bookRef, parts[2], token);
    });
  }

  function renderNotFound(message) {
    document.title = 'Ничего не найдено — ГДЗ НЭЛ';
    screenEl.innerHTML = '<h1 class="panel-title">Ничего не найдено</h1>' +
      '<p class="panel-sub">' + esc(message) + '</p>' +
      '<p><a class="btn btn-outline" href="#/"><span class="icon i-arrow-left" aria-hidden="true"></span><span>К предметам</span></a></p>';
    return Promise.resolve();
  }

  /* =========================================================
     экран: предметы
     ========================================================= */

  function renderHome(token) {
    return Promise.all([loadCatalog(), loadStats()]).then(function (res) {
      if (token !== renderToken) return;
      var cat = res[0];
      var stats = res[1];

      document.title = 'ГДЗ НЭЛ — готовые домашние задания для 6 класса';

      var html = '<h1 class="panel-title">Предметы</h1>' +
        '<p class="panel-sub">6 класс, 2026–2027 учебный год. Выбери предмет, затем учебник и номер задания.</p>' +
        '<div class="subject-grid">';

      cat.subjects.forEach(function (s) {
        var books = (s.textbooks || []).length;
        var count = stats && stats.subjects && stats.subjects[s.id] ? stats.subjects[s.id].tasks : null;
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
          html += '<a class="subject-card" href="#/' + esc(s.id) + '">' + icon +
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

  function renderSubject(subject) {
    return loadStats().then(function (stats) {
      document.title = subject.title + ' — ГДЗ НЭЛ';

      var html = '<nav class="crumbs" aria-label="Навигация">' +
        '<a href="#/">Главная</a><span class="crumb-sep">/</span>' +
        '<span>' + esc(subject.title) + '</span></nav>' +
        '<h1 class="panel-title">' + esc(subject.title) + '</h1>' +
        '<p class="panel-sub">Выбери учебник или часть.</p>' +
        '<div class="book-grid">';

      (subject.textbooks || []).forEach(function (b) {
        var partMatch = /Часть\s*(\d)/.exec(b.title);
        var partLabel = partMatch ? ('ч. ' + partMatch[1]) : '6 класс';
        var count = null;
        if (stats && stats.books && typeof stats.books[b.file] === 'number') {
          count = stats.books[b.file];
        }
        html += '<a class="bookcard" href="#/' + esc(subject.id) + '/' + esc(b.id) + '">' +
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

  function renderTasks(subject, bookRef, token) {
    return loadBook(bookRef.file).then(function (book) {
      if (token !== renderToken) return;

      var tasks = sortedTasks(book);
      document.title = bookRef.title + ' — ' + subject.title + ' — ГДЗ НЭЛ';

      var html = '<nav class="crumbs" aria-label="Навигация">' +
        '<a href="#/">Главная</a><span class="crumb-sep">/</span>' +
        '<a href="#/' + esc(subject.id) + '">' + esc(subject.title) + '</a><span class="crumb-sep">/</span>' +
        '<span>' + esc(bookRef.title) + '</span></nav>' +
        '<h1 class="panel-title">' + esc(bookRef.title) + '</h1>' +
        '<p class="panel-sub">' + esc(bookRef.author || '') + '</p>';

      if (!tasks.length) {
        html += '<p class="empty">Задания для этого учебника ещё не загружены.</p>';
        screenEl.innerHTML = html;
        return;
      }

      // группировка по разделам: задачи идут по порядку,
      // пропущенные номера внутри раздела остаются серыми кнопками
      var groups = [];
      var current = null;
      var prevNumber = null;
      tasks.forEach(function (t) {
        var name = t.section || (current ? current.name : 'Все задания');
        if (!current || current.name !== name) {
          current = { name: name, cells: [], count: 0 };
          groups.push(current);
          prevNumber = null;
        }
        if (prevNumber !== null) {
          missingBetween(prevNumber, t.number).forEach(function (missed) {
            current.cells.push({ number: missed, task: null });
          });
        }
        current.cells.push({ number: t.number, task: t });
        current.count++;
        prevNumber = t.number;
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
        g.cells.forEach(function (cell) {
          if (cell.task) {
            html += '<a class="task-cell" href="#/' + esc(subject.id) + '/' + esc(bookRef.id) + '/' +
              encodeURIComponent(cell.number) + '" ' +
              'data-number="' + esc(cell.number) + '" aria-label="Задание ' + esc(cell.number) + '">' +
              '<span>' + esc(cell.number) + '</span></a>';
          } else {
            html += '<span class="task-cell is-missing" data-number="' + esc(cell.number) + '" aria-hidden="true">' +
              '<span>' + esc(cell.number) + '</span></span>';
          }
        });
        html += '</div></section>';
      });

      if (!onlyDefault) {
        html += '<div class="next-section"><button class="btn btn-outline btn-sm" id="next-section-btn" type="button">' +
          '<span>Следующий раздел</span><span class="icon i-chevron-down" aria-hidden="true"></span></button></div>';
      }

      screenEl.innerHTML = html;

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

  function renderTask(subject, bookRef, number, token) {
    return loadBook(bookRef.file).then(function (book) {
      if (token !== renderToken) return;

      var tasks = sortedTasks(book);
      var index = -1;
      tasks.forEach(function (t, i) { if (String(t.number) === String(number)) index = i; });

      if (index === -1) return renderNotFound('Задания с таким номером нет в этом учебнике.');

      var task = tasks[index];
      var prev = index > 0 ? tasks[index - 1] : null;
      var next = index < tasks.length - 1 ? tasks[index + 1] : null;

      var base = '#/' + subject.id + '/' + bookRef.id;
      var taskLabel = 'Задание ' + task.number;

      currentTask = {
        prev: prev ? base + '/' + prev.number : null,
        next: next ? base + '/' + next.number : null,
        back: base
      };

      document.title = taskLabel + ' — ' + subject.title + ' — ГДЗ НЭЛ';

      var entry = {
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
        '<a href="#/' + esc(subject.id) + '">' + esc(subject.title) + '</a><span class="crumb-sep">/</span>' +
        '<a href="' + base + '">' + esc(bookRef.title) + '</a><span class="crumb-sep">/</span>' +
        '<span>' + taskLabel + '</span></nav>' +
        '<div class="task-view">' +
        '<h1 class="panel-title">' + taskLabel + '</h1>' +

        '<section class="task-block task-block--cond">' +
        '<p class="task-label">Условие</p>' +
        '<div class="task-text">' + textToHtml(task.condition) + '</div>' +
        '</section>' +

        '<section class="task-block">' +
        '<p class="task-label">Решение</p>' +
        '<ol class="steps-list">' + solutionSteps(task.solution) + '</ol>' +
        '</section>' +

        '<section class="task-block task-block--answer">' +
        '<p class="task-label">Ответ</p>' +
        '<div class="answer">' + textToHtml(task.answer) + '</div>' +
        '</section>' +

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
        '</div>';

      screenEl.innerHTML = html;

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

      // скопировать ссылку
      byId('copy-btn').addEventListener('click', function () {
        copyText(location.href).then(function () {
          showToast('Ссылка скопирована');
        }, function () {
          showToast('Не удалось скопировать ссылку');
        });
      });

      // подсказка о клавишах — один раз
      if (!storeGet(LS_HINT, false)) hintEl.hidden = false;
    });
  }

  // пошаговое решение: каждая строка — шаг
  function solutionSteps(solution) {
    var lines = String(solution || '').split(/\n+/)
      .map(function (line) { return line.trim(); })
      .filter(Boolean);
    if (!lines.length) return '<li class="step-line"><p>Решение появится позже.</p></li>';
    return lines.map(function (line, i) {
      return '<li class="step-line"><span class="step-num" aria-hidden="true">' + (i + 1) + '</span><p>' + esc(line) + '</p></li>';
    }).join('');
  }

  function reportHref(entry) {
    var subjectLine = 'Ошибка в задании ' + entry.number + ' учебника ' + entry.book;
    var body = 'Ссылка: ' + location.href + '\n\nОпиши ошибку: ';
    return 'mailto:bdfy.tu@yandex.ru?subject=' + encodeURIComponent(subjectLine) + '&body=' + encodeURIComponent(body);
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
      var url = '#/' + item.subject + '/' + item.book + '/' + item.number;
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

    document.title = 'Поиск: ' + query + ' — ГДЗ НЭЛ';
    screenEl.innerHTML = '<h1 class="panel-title">Поиск</h1>' +
      '<p class="panel-sub">Ищу «' + esc(query) + '»…</p>';

    loadAllTasks().then(function (list) {
      if (token !== renderToken) return;

      var q = query.toLowerCase();
      var isDigits = /^\d+(?:[.,]\d+)?$/.test(query);
      var found = [];
      for (var i = 0; i < list.length && found.length < 50; i++) {
        var item = list[i];
        var hit = isDigits
          ? String(item.number).indexOf(query) === 0
          : item.condition.toLowerCase().indexOf(q) !== -1;
        if (hit) found.push(item);
      }

      var html = '<h1 class="panel-title">Поиск</h1>' +
        '<p class="panel-sub">' + (found.length
          ? 'Нашлось: ' + tasksWord(found.length) + (found.length === 50 ? ' (первые 50)' : '')
          : 'Ничего не найдено по запросу «' + esc(query) + '»') + '</p>';

      if (!found.length) {
        html += '<p class="empty">Попробуй другой номер или слово из условия.</p>';
      } else {
        html += '<ul class="list">';
        found.forEach(function (item) {
          var url = '#/' + item.subject + '/' + item.book + '/' + item.number;
          html += '<li class="list-item">' +
            '<span class="subject-icon" style="width:40px;height:40px"><span class="icon i-' + esc(item.subject) + '" aria-hidden="true"></span></span>' +
            '<div class="list-main">' +
            '<a class="list-title" href="' + url + '">' + esc(item.subjectTitle + ' · ' + item.bookTitle + ' · №' + item.number) + '</a>' +
            '<p class="list-snippet">' + snippet(item.condition, isDigits ? '' : query) + '</p>' +
            '</div>' +
            '<div class="list-actions"><span class="icon i-chevron-right" aria-hidden="true"></span></div></li>';
        });
        html += '</ul>';
      }

      screenEl.innerHTML = html;
    });
  }

  /* =========================================================
     поиск, клавиатура, свайпы
     ========================================================= */

  var onSearchInput = debounce(function () {
    var query = searchInput.value.trim();
    searchClear.hidden = !query;

    if (!query) { route(); return; }

    var parts = currentParts();
    // на сетке заданий: цифры фильтруют номера, текст ищется глобально
    if (parts.length === 2 && /^\d+(?:[.,]\d+)?$/.test(query)) {
      applyTaskFilter(query.replace(',', '.'));
      return;
    }
    renderSearchResults(query);
  }, 200);

  searchInput.addEventListener('input', onSearchInput);

  searchClear.addEventListener('click', function () {
    searchInput.value = '';
    searchClear.hidden = true;
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
     мелочи: тень шапки, офлайн
     ========================================================= */

  var onScroll = function () {
    headerEl.classList.toggle('is-stuck', window.scrollY > 6);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  if ('serviceWorker' in navigator && location.protocol.indexOf('http') === 0) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('service-worker.js').catch(function () { /* ещё не собран */ });
    });
  }

  /* =========================================================
     старт
     ========================================================= */

  window.addEventListener('hashchange', route);
  route();
})();
