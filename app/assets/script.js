'use strict';

/* =========================================================
   ГДЗ НЭЛ — приложение.
   Чистая статика: хэш-роутинг, данные из JSON через fetch.
   Маршруты:
     #/                         выбор предмета
     #/math                     выбор учебника
     #/math/vilenkin-6-1        сетка заданий
     #/math/vilenkin-6-1/5      страница задания
   ========================================================= */

var DATA_DIR = 'data/';
var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
var TRANSITION_MS = 180;

var screenEl = document.getElementById('screen');

var renderToken = 0;   // защита от гонок при быстрой навигации
var firstRender = true;

/* ---------- утилиты ---------- */

function wait(ms) {
  return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

function escapeHtml(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
  });
}

// многострочный текст из JSON -> абзацы html
function textToHtml(value) {
  return String(value == null ? '' : value)
    .split('\n')
    .map(function (line) { return line.trim(); })
    .filter(Boolean)
    .map(function (line) { return '<p>' + escapeHtml(line) + '</p>'; })
    .join('');
}

function htmlToNode(html) {
  var tpl = document.createElement('template');
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}

function plural(n, one, few, many) {
  var m10 = n % 10;
  var m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

/* ---------- загрузка данных ---------- */

var catalogPromise = fetch(DATA_DIR + 'catalog.json').then(function (res) {
  if (!res.ok) throw new Error('catalog.json: ' + res.status);
  return res.json();
});
catalogPromise.catch(function () { /* ошибку покажет render() */ });

var bookCache = new Map();

function loadBook(file) {
  if (!bookCache.has(file)) {
    bookCache.set(file, fetch(DATA_DIR + file).then(function (res) {
      if (!res.ok) throw new Error(file + ': ' + res.status);
      return res.json();
    }));
  }
  return bookCache.get(file);
}

/* ---------- маршрут ---------- */

function parseRoute() {
  return location.hash
    .replace(/^#\/?/, '')
    .split('/')
    .filter(Boolean)
    .map(decodeURIComponent);
}

function findSubject(catalog, id) {
  for (var i = 0; i < catalog.subjects.length; i++) {
    if (catalog.subjects[i].id === id) return catalog.subjects[i];
  }
  return null;
}

function findBook(subject, id) {
  if (!subject) return null;
  for (var i = 0; i < subject.textbooks.length; i++) {
    if (subject.textbooks[i].id === id) return subject.textbooks[i];
  }
  return null;
}

// ссылка на предмет: если учебник один — он открывается сразу, крошка ведёт на главную
function subjectHref(subject) {
  return subject.textbooks.length > 1 ? '#/' + subject.id : '#/';
}

/* ---------- общие куски разметки ---------- */

function crumbsHtml(items) {
  var parts = items.map(function (item, i) {
    var last = i === items.length - 1;
    if (last || !item.href) return '<span>' + escapeHtml(item.text) + '</span>';
    return '<a href="' + item.href + '">' + escapeHtml(item.text) + '</a>';
  });
  return '<nav class="crumbs" aria-label="Навигация">' + parts.join('<span class="crumb-sep">/</span>') + '</nav>';
}

function skeletonCells(count) {
  var out = '';
  for (var i = 0; i < count; i++) out += '<span class="sk sk-cell"></span>';
  return out;
}

function skeletonLines(count, widths) {
  var out = '';
  for (var i = 0; i < count; i++) {
    var w = (widths && widths[i]) || (88 - i * 14);
    out += '<span class="sk sk-line" style="width:' + w + '%"></span>';
  }
  return out;
}

function errorScreenHtml(message) {
  return '' +
    '<section class="panel">' +
      '<h1 class="panel-title">Не удалось загрузить данные</h1>' +
      '<p class="error">' + escapeHtml(message) + '</p>' +
      '<p class="empty">Открой сайт через локальный сервер или с хостинга: при открытии файла напрямую (file://) fetch не работает. Команда: <code>uv run python -m http.server 8000</code></p>' +
    '</section>';
}

/* ---------- экраны ---------- */

// экран 1: предметы
function buildSubjects(catalog) {
  var cards = catalog.subjects.map(function (subject) {
    var soon = !subject.active || !subject.textbooks || subject.textbooks.length === 0;

    if (soon) {
      return '' +
        '<div class="subject-card is-soon">' +
          '<span class="subject-soon">скоро</span>' +
          '<span class="subject-name">' + escapeHtml(subject.title) + '</span>' +
          '<span class="subject-meta">Задания готовятся</span>' +
        '</div>';
    }

    // один учебник — открываем его сразу, несколько — показываем выбор
    var href = subject.textbooks.length === 1
      ? '#/' + subject.id + '/' + subject.textbooks[0].id
      : '#/' + subject.id;

    var meta = subject.textbooks.map(function (b) { return b.title; }).join(' · ');

    return '' +
      '<a class="subject-card" href="' + href + '">' +
        '<span class="subject-name">' + escapeHtml(subject.title) + '</span>' +
        '<span class="subject-meta">' + escapeHtml(meta) + '</span>' +
        '<span class="subject-open">Открыть ›</span>' +
      '</a>';
  }).join('');

  var node = htmlToNode('' +
    '<section class="panel">' +
      '<h1 class="panel-title">Готовые домашние задания</h1>' +
      '<p class="panel-sub">6 класс, МАОУ «Новосибирский экономический лицей»</p>' +
      '<div class="subject-grid">' + cards + '</div>' +
    '</section>');

  return { node: node, title: 'ГДЗ НЭЛ — 6 класс' };
}

// экран 2: учебники предмета
function buildTextbooks(subject) {
  var tiles = subject.textbooks.map(function (book) {
    return '' +
      '<a class="tile" href="#/' + subject.id + '/' + book.id + '">' +
        '<span class="tile-title">' + escapeHtml(book.title) + '</span>' +
        '<span class="tile-meta">' + escapeHtml(book.author) + '</span>' +
        '<span class="tile-meta">' + escapeHtml(book.year) + '</span>' +
      '</a>';
  }).join('');

  var node = htmlToNode('' +
    '<section class="panel">' +
      crumbsHtml([
        { text: 'Предметы', href: '#/' },
        { text: subject.title }
      ]) +
      '<h1 class="panel-title">' + escapeHtml(subject.title) + '</h1>' +
      '<p class="panel-sub">Выбери учебник</p>' +
      '<div class="tile-grid">' + tiles + '</div>' +
    '</section>');

  return { node: node, title: subject.title + ' — ГДЗ НЭЛ' };
}

// экран 3: сетка номеров заданий
function buildTasks(subject, book) {
  var node = htmlToNode('' +
    '<section class="panel">' +
      crumbsHtml([
        { text: 'Предметы', href: '#/' },
        { text: subject.title, href: subjectHref(subject) },
        { text: book.title }
      ]) +
      '<h1 class="panel-title">' + escapeHtml(book.title) + '</h1>' +
      '<p class="panel-sub">' + escapeHtml(book.author) + ' · ' + escapeHtml(book.year) + '</p>' +
      '<div class="task-toolbar">' +
        '<input id="task-search" class="search" type="search" placeholder="Поиск по номеру задания" autocomplete="off" aria-label="Поиск по номеру задания">' +
        '<span id="task-count" class="task-count"></span>' +
      '</div>' +
      '<div id="task-grid" class="task-grid">' + skeletonCells(30) + '</div>' +
      '<p id="task-empty" class="empty" hidden>Ничего не найдено</p>' +
    '</section>');

  return {
    node: node,
    title: book.title + ' — ГДЗ НЭЛ',
    subject: subject,
    book: book,
    fill: fillTasks
  };
}

// догрузка сетки заданий
function fillTasks(view, token) {
  var grid = view.node.querySelector('#task-grid');
  var countEl = view.node.querySelector('#task-count');
  var emptyEl = view.node.querySelector('#task-empty');
  var search = view.node.querySelector('#task-search');
  var subject = view.subject;
  var book = view.book;

  return loadBook(book.file).then(function (data) {
    if (token !== renderToken) return;

    var tasks = (data.tasks || []).slice().sort(function (a, b) { return a.number - b.number; });

    if (!tasks.length) {
      grid.innerHTML = '';
      emptyEl.hidden = false;
      emptyEl.textContent = 'В этом учебнике пока нет заданий';
      return;
    }

    countEl.textContent = tasks.length + ' ' + plural(tasks.length, 'задание', 'задания', 'заданий');

    var present = {};
    tasks.forEach(function (t) { present[t.number] = true; });

    // сетка от 1 до последнего номера; пропуски — серые некликабельные
    var max = tasks[tasks.length - 1].number;
    var cells = '';
    for (var n = 1; n <= max; n++) {
      if (present[n]) {
        cells += '<a class="task-cell" href="#/' + subject.id + '/' + book.id + '/' + n + '" data-num="' + n + '"><span>' + n + '</span></a>';
      } else {
        cells += '<span class="task-cell is-missing" data-num="' + n + '" aria-disabled="true" title="Задания нет в базе"><span>' + n + '</span></span>';
      }
    }
    grid.innerHTML = cells;

    // живой фильтр по номеру
    search.addEventListener('input', function () {
      var q = search.value.trim();
      var cellsAll = grid.querySelectorAll('.task-cell');
      var visible = 0;

      for (var i = 0; i < cellsAll.length; i++) {
        var num = cellsAll[i].getAttribute('data-num');
        var match = q === '' || num.indexOf(q) === 0;
        cellsAll[i].hidden = !match;
        if (match) visible++;
      }

      emptyEl.hidden = visible > 0;
      emptyEl.textContent = 'Ничего не найдено';
    });
  }).catch(function () {
    if (token !== renderToken) return;
    grid.innerHTML = '<p class="error">Не удалось загрузить список заданий</p>';
  });
}

// экран 4: страница задания
function buildTask(subject, book, number) {
  var node = htmlToNode('' +
    '<section class="panel task-view">' +
      crumbsHtml([
        { text: 'Предметы', href: '#/' },
        { text: subject.title, href: subjectHref(subject) },
        { text: book.title, href: '#/' + subject.id + '/' + book.id },
        { text: 'Задание ' + number }
      ]) +
      '<div id="task-body">' +
        '<span class="sk sk-line" style="width:36%"></span>' +
        skeletonLines(3, [92, 78, 55]) +
        '<span class="sk sk-line" style="width:64%"></span>' +
      '</div>' +
    '</section>');

  return {
    node: node,
    title: 'Задание ' + number + ' — ' + book.title,
    subject: subject,
    book: book,
    number: number,
    fill: fillTask
  };
}

// догрузка страницы задания
function fillTask(view, token) {
  var body = view.node.querySelector('#task-body');
  var subject = view.subject;
  var book = view.book;
  var number = view.number;
  var listHref = '#/' + subject.id + '/' + book.id;

  return loadBook(book.file).then(function (data) {
    if (token !== renderToken) return;

    var tasks = (data.tasks || []).slice().sort(function (a, b) { return a.number - b.number; });
    var task = null;
    for (var i = 0; i < tasks.length; i++) {
      if (tasks[i].number === number) { task = tasks[i]; break; }
    }

    if (!task) {
      body.innerHTML = '' +
        '<h1 class="panel-title">Задание ' + number + '</h1>' +
        '<p class="empty">Этого задания пока нет в базе. <a href="' + listHref + '">К списку заданий</a></p>';
      return;
    }

    // соседние задания для кнопок назад/вперёд (пропуски пропускаются)
    var idx = tasks.indexOf(task);
    var prev = tasks[idx - 1];
    var next = tasks[idx + 1];

    function navBtn(t, dir) {
      if (!t) {
        return '<span class="btn btn-outline is-disabled"><span>' + (dir === 'prev' ? '‹ Назад' : 'Вперёд ›') + '</span></span>';
      }
      var href = '#/' + subject.id + '/' + book.id + '/' + t.number;
      return '<a class="btn btn-outline" href="' + href + '"><span>' + (dir === 'prev' ? '‹ ' + t.number + ' назад' : t.number + ' вперёд ›') + '</span></a>';
    }

    body.innerHTML = '' +
      '<h1 class="panel-title">Задание ' + task.number + '</h1>' +
      '<div class="task-block">' +
        '<h2 class="task-label">Условие</h2>' +
        '<div class="task-text">' + textToHtml(task.condition) + '</div>' +
      '</div>' +
      '<div class="task-block">' +
        '<div class="task-block-head">' +
          '<h2 class="task-label">Решение</h2>' +
          '<button class="toggle" type="button" aria-expanded="true">скрыть</button>' +
        '</div>' +
        '<div class="collapse" id="solution">' +
          '<div class="collapse-inner task-text">' + textToHtml(task.solution) + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="task-block task-block--answer">' +
        '<h2 class="task-label">Ответ</h2>' +
        '<div class="answer">' + textToHtml(task.answer) + '</div>' +
      '</div>' +
      '<div class="task-nav">' +
        navBtn(prev, 'prev') +
        '<a class="btn btn-outline" href="' + listHref + '"><span>К списку заданий</span></a>' +
        navBtn(next, 'next') +
      '</div>';

    // плавное раскрытие решения при открытии страницы
    var collapse = body.querySelector('#solution');
    requestAnimationFrame(function () {
      if (token === renderToken) collapse.classList.add('is-open');
    });

    var toggle = body.querySelector('.toggle');
    toggle.addEventListener('click', function () {
      var open = collapse.classList.toggle('is-open');
      toggle.textContent = open ? 'скрыть' : 'показать';
      toggle.setAttribute('aria-expanded', String(open));
    });
  }).catch(function () {
    if (token !== renderToken) return;
    body.innerHTML = '<p class="error">Не удалось загрузить задание</p>';
  });
}

/* ---------- роутинг ---------- */

// по маршруту решает, что показывать; может вернуть { redirect: '...' }
function resolveView(route, catalog) {
  if (route.length === 0) return buildSubjects(catalog);

  var subject = findSubject(catalog, route[0]);
  if (!subject) return { redirect: '/' };

  if (route.length === 1) {
    if (!subject.active || !subject.textbooks.length) return { redirect: '/' };
    if (subject.textbooks.length === 1) return { redirect: '/' + subject.id + '/' + subject.textbooks[0].id };
    return buildTextbooks(subject);
  }

  var book = findBook(subject, route[1]);
  if (!book) return { redirect: '/' + subject.id };

  if (route.length === 2) return buildTasks(subject, book);

  var number = Number(route[2]);
  if (!isFinite(number) || number < 1 || Math.floor(number) !== number) {
    return { redirect: '/' + subject.id + '/' + book.id };
  }
  return buildTask(subject, book, number);
}

function render() {
  var token = ++renderToken;
  var route = parseRoute();

  var fade = firstRender
    ? Promise.resolve()
    : Promise.resolve(screenEl.classList.add('screen--out')).then(function () {
        return REDUCED ? null : wait(TRANSITION_MS);
      });

  return fade.then(function () {
    if (token !== renderToken) return;

    return catalogPromise.then(function (catalog) {
      if (token !== renderToken) return;

      var view = resolveView(route, catalog);

      if (view.redirect) {
        location.replace('#' + view.redirect);
        return;
      }

      screenEl.replaceChildren(view.node);
      screenEl.classList.remove('screen--out');
      document.title = view.title;
      window.scrollTo(0, 0);
      firstRender = false;

      if (view.fill) {
        view.fill(view, token).catch(function () { /* ошибки экранов обрабатываются внутри */ });
      }
    }, function (err) {
      if (token !== renderToken) return;
      screenEl.classList.remove('screen--out');
      screenEl.innerHTML = errorScreenHtml(err.message || 'неизвестная ошибка');
    });
  });
}

window.addEventListener('hashchange', render);
render();
