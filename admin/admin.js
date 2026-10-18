/* =========================================================
   ГДЗ НЭЛ — админка 2.0. Доступ: profiles.role = 'admin'.

   Вкладки: обзор (график Chart.js, лента, топ), пользователи
   (поиск, фильтры, массовые операции, CSV, сброс пароля),
   модерация отзывов, ИИ-логи, фото-логи, достижения.

   Все действия администратора пишутся в admin_logs (Ф24.7).
   Новые отзывы и фото приходят в реальном времени (Ф9.14).
   ========================================================= */

import {
  supabase, getSession, escapeHtml as esc, avatarColor,
  BADGES, badgeTitle
} from '../assets/supabase.js';

var PAGE = 20;

var state = {
  tab: 'overview',
  me: null,
  users: { rows: [], page: 0, count: 0, search: '', filter: 'all', focusSearch: false, selected: {} },
  reviews: { rows: [], page: 0, count: 0, filter: 'all', search: '', selected: {} },
  ai: { rows: [], page: 0, count: 0 },
  photos: { rows: [], page: 0, count: 0 },
  achievements: { rows: [], page: 0, count: 0 }
};

function $(id) { return document.getElementById(id); }

/* ---------- формат и мелкие блоки ---------- */

function fmtDate(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString('ru-RU', {
      day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
    });
  } catch (err) { return '—'; }
}

function starsMini(n) {
  var html = '<span class="stars-mini" aria-label="Оценка ' + n + ' из 5">';
  for (var i = 1; i <= 5; i++) {
    html += '<span class="icon i-star-filled' + (i <= n ? '' : ' is-off') + '" aria-hidden="true"></span>';
  }
  return html + '</span>';
}

function statusBadge(status) {
  if (status === 'approved') return '<span class="badge is-approved">одобрен</span>';
  if (status === 'rejected') return '<span class="badge is-rejected">отклонён</span>';
  return '<span class="badge is-pending">на проверке</span>';
}

function skeleton(rows) {
  var html = '<div class="sk">';
  for (var i = 0; i < (rows || 6); i++) html += '<div class="sk-row"></div>';
  return html + '</div>';
}

function pagerHtml(tab, sc) {
  var pages = Math.max(1, Math.ceil(sc.count / PAGE));
  var page = sc.page + 1;
  return '<div class="pager">' +
    '<button class="btn btn-outline btn-sm" type="button" data-act="page" data-tab="' + tab + '" data-dir="-1"' +
    (sc.page === 0 ? ' disabled' : '') + '>' +
    '<span class="icon i-arrow-left" aria-hidden="true"></span><span>Назад</span></button>' +
    '<span class="pager-info">стр. ' + page + ' из ' + pages + ' · всего ' + sc.count + '</span>' +
    '<button class="btn btn-outline btn-sm" type="button" data-act="page" data-tab="' + tab + '" data-dir="1"' +
    (sc.page >= pages - 1 ? ' disabled' : '') + '>' +
    '<span>Вперёд</span><span class="icon i-arrow-right" aria-hidden="true"></span></button>' +
    '</div>';
}

var toastTimer = 0;
function toast(message, isError) {
  var el = $('admin-toast');
  el.textContent = message;
  el.className = 'admin-toast is-visible' + (isError ? ' is-err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { el.className = 'admin-toast'; }, 3000);
}

function countOf(table, mod) {
  var q = supabase.from(table).select('id', { count: 'exact', head: true });
  if (mod) mod(q);
  return q.then(function (res) { return res.count || 0; });
}

/* ---------- журнал действий администратора ---------- */

function logAction(action, target, meta) {
  if (!state.me) return;
  supabase.from('admin_logs').insert({
    admin_id: state.me.id,
    action: action,
    target: target || null,
    meta: meta || null
  }).then(function () { /* журнал не должен ломать действие */ });
}

/* ---------- модалки вместо confirm() (Ф10.3) ---------- */

function openModal(opts) {
  return new Promise(function (resolve) {
    var root = $('admin-modal');
    var isDanger = !!opts.danger;
    root.innerHTML =
      '<div class="modal-card" role="dialog" aria-modal="true" aria-label="' + esc(opts.title) + '">' +
      '<h2 class="modal-title">' + esc(opts.title) + '</h2>' +
      '<div class="modal-body">' + (opts.body || '') + '</div>' +
      '<div class="modal-actions">' +
      '<button class="btn btn-outline" type="button" data-modal="no">' + esc(opts.cancelText || 'Отмена') + '</button>' +
      '<button class="btn ' + (isDanger ? 'btn-danger' : 'btn-primary') + '" type="button" data-modal="yes">' +
      esc(opts.confirmText || 'Готово') + '</button>' +
      '</div></div>';
    root.hidden = false;

    var input = root.querySelector('input');
    if (input) setTimeout(function () { input.focus(); }, 30);

    function done(value) {
      root.hidden = true;
      root.innerHTML = '';
      document.removeEventListener('keydown', onKey);
      resolve(value);
    }
    function onKey(event) {
      if (event.key === 'Escape') done(false);
      if (event.key === 'Enter' && (event.target.tagName === 'INPUT')) done(true);
    }

    root.onclick = function (event) {
      var btn = event.target.closest('[data-modal]');
      if (btn) done(btn.getAttribute('data-modal') === 'yes');
      else if (event.target === root) done(false);
    };
    document.addEventListener('keydown', onKey);
  });
}

/* ---------- CSV (Ф9.12) ---------- */

function csvCell(value) {
  var s = String(value == null ? '' : value).replace(/"/g, '""');
  return /[";\n]/.test(s) ? '"' + s + '"' : s;
}

function csvDownload(filename, headers, rows) {
  var lines = [headers.join(';')];
  rows.forEach(function (row) { lines.push(row.map(csvCell).join(';')); });
  var blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
}

// выгружаем всё, порциями по 1000 (с потолком, чтобы не утащить весь интернет)
async function fetchAllChunks(buildQuery, cap) {
  var rows = [];
  var step = 1000;
  for (var from = 0; from < (cap || 5000); from += step) {
    var res = await buildQuery().range(from, from + step - 1);
    if (res.error) return { rows: rows, error: res.error };
    rows = rows.concat(res.data || []);
    if (!res.data || res.data.length < step) break;
  }
  return { rows: rows, error: null };
}

/* ---------- обзор ---------- */

var chart = null;

async function renderOverview() {
  var content = $('admin-content');
  content.innerHTML = skeleton(4);

  var dayAgo = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  var weeksAgo = new Date(Date.now() - 14 * 86400000).toISOString();

  var res = await Promise.all([
    countOf('profiles'),
    countOf('reviews'),
    countOf('reviews', function (q) { return q.eq('ai_status', 'pending'); }),
    countOf('photo_requests', function (q) { return q.gte('created_at', dayAgo); }),
    countOf('events', function (q) { return q.gte('created_at', dayAgo); }),
    countOf('achievements'),
    supabase.from('reviews').select('id, username, task_id, ai_status, created_at').gte('created_at', weeksAgo).limit(1000),
    supabase.from('photo_requests').select('id, created_at').gte('created_at', weeksAgo).limit(1000),
    supabase.from('events').select('name, path, created_at').gte('created_at', weeksAgo).limit(1000),
    supabase.from('admin_logs').select('action, target, created_at').order('created_at', { ascending: false }).limit(6),
    supabase.from('reviews').select('id, username, task_id, ai_status, created_at').order('created_at', { ascending: false }).limit(5),
    supabase.from('photo_requests').select('id, created_at').order('created_at', { ascending: false }).limit(4)
  ]);

  var usersCount = res[0];
  var reviewsCount = res[1];
  var pendingCount = res[2];
  var photosToday = res[3];
  var eventsToday = res[4];
  var badgesCount = res[5];
  var reviewRows = res[6].data || [];
  var photoRows = res[7].data || [];
  var eventRows = res[8].data || [];
  var logRows = res[9].data || [];
  var lastReviews = res[10].data || [];
  var lastPhotos = res[11].data || [];

  // дни за 2 недели
  var days = [];
  var byKey = {};
  for (var i = 13; i >= 0; i--) {
    var d = new Date(Date.now() - i * 86400000);
    var item = {
      key: d.toISOString().slice(0, 10),
      label: d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }),
      reviews: 0, photos: 0, events: 0
    };
    days.push(item);
    byKey[item.key] = item;
  }
  reviewRows.forEach(function (r) { var b = byKey[String(r.created_at).slice(0, 10)]; if (b) b.reviews++; });
  photoRows.forEach(function (r) { var b = byKey[String(r.created_at).slice(0, 10)]; if (b) b.photos++; });
  eventRows.forEach(function (r) { var b = byKey[String(r.created_at).slice(0, 10)]; if (b) b.events++; });

  // топ пользователей по отзывам (Ф16.12)
  var byUser = {};
  reviewRows.forEach(function (r) {
    var name = r.username || 'аноним';
    byUser[name] = (byUser[name] || 0) + 1;
  });
  var top = Object.keys(byUser).map(function (name) { return { name: name, count: byUser[name] }; })
    .sort(function (a, b) { return b.count - a.count; }).slice(0, 5);

  // популярные страницы по событиям
  var byPath = {};
  eventRows.forEach(function (e) {
    if (e.name !== 'page_view' || !e.path) return;
    byPath[e.path] = (byPath[e.path] || 0) + 1;
  });
  var topPages = Object.keys(byPath).map(function (p) { return { path: p, count: byPath[p] }; })
    .sort(function (a, b) { return b.count - a.count; }).slice(0, 5);

  // лента
  var statusWord = { pending: 'на проверке', approved: 'одобрен', rejected: 'отклонён' };
  var feed = [];
  lastReviews.forEach(function (rv) {
    feed.push({ ts: rv.created_at, icon: 'i-message', text: 'Отзыв ' + (statusWord[rv.ai_status] || rv.ai_status) + ' — ' + (rv.username || 'аноним') + ', ' + rv.task_id });
  });
  lastPhotos.forEach(function (p) {
    feed.push({ ts: p.created_at, icon: 'i-camera', text: 'Фото на решение' });
  });
  logRows.forEach(function (l) {
    feed.push({ ts: l.created_at, icon: 'i-shield', text: 'Админ: ' + l.action + (l.target ? ' — ' + String(l.target).slice(0, 40) : '') });
  });
  feed.sort(function (a, b) { return String(b.ts).localeCompare(String(a.ts)); });

  var feedHtml = feed.length
    ? '<ul class="feed">' + feed.slice(0, 8).map(function (f) {
        return '<li><span class="icon ' + f.icon + '" aria-hidden="true"></span>' +
          '<span>' + esc(f.text) + '</span><time>' + fmtDate(f.ts) + '</time></li>';
      }).join('') + '</ul>'
    : '<p class="admin-muted">Пока пусто.</p>';

  function card(icon, value, label) {
    return '<div class="dash-card">' +
      '<span class="dash-card-icon"><span class="icon ' + icon + '" aria-hidden="true"></span></span>' +
      '<span><span class="dash-card-value">' + value + '</span><br>' +
      '<span class="dash-card-label">' + label + '</span></span></div>';
  }

  var listBlock = function (title, items, render) {
    if (!items.length) return '<div class="panel"><h2>' + title + '</h2><p class="admin-muted">Пока пусто.</p></div>';
    return '<div class="panel"><h2>' + title + '</h2><ul class="mini-list">' + items.map(render).join('') + '</ul></div>';
  };

  content.innerHTML =
    '<div class="dash-cards">' +
    card('i-user', usersCount, 'Пользователей') +
    card('i-message', reviewsCount, 'Отзывов') +
    card('i-clock', pendingCount, 'Ждут модерации') +
    card('i-camera', photosToday, 'Фото за сутки') +
    card('i-chart', eventsToday, 'Просмотров за сутки') +
    card('i-award', badgesCount, 'Выдано достижений') +
    '</div>' +
    '<div class="dash-grid">' +
    '<div class="panel"><h2>Активность за 2 недели</h2>' +
    '<div class="chart-box"><canvas id="dash-chart" height="220" aria-label="График активности"></canvas></div>' +
    '<div class="chart-legend">' +
    '<span><i class="dot dot--reviews"></i>отзывы</span>' +
    '<span><i class="dot dot--photos"></i>фото</span>' +
    '<span><i class="dot dot--events"></i>просмотры</span>' +
    '</div></div>' +
    '<div class="panel"><h2>Последние действия</h2>' + feedHtml + '</div>' +
    '</div>' +
    '<div class="dash-grid">' +
    listBlock('Топ авторов отзывов', top, function (t) {
      return '<li><span>' + esc(t.name) + '</span><b>' + t.count + '</b></li>';
    }) +
    listBlock('Популярные страницы', topPages, function (t) {
      return '<li><span class="cell-task">' + esc(t.path) + '</span><b>' + t.count + '</b></li>';
    }) +
    '</div>';

  drawChart(days);
}

function drawChart(days) {
  var canvas = $('dash-chart');
  if (!canvas) return;

  var labels = days.map(function (d) { return d.label; });

  if (typeof window.Chart === 'undefined') {
    // офлайн/CDN недоступен — рисуем простые столбики
    var max = 1;
    days.forEach(function (d) { max = Math.max(max, d.reviews + d.photos + d.events); });
    var bars = days.map(function (d) {
      var total = d.reviews + d.photos + d.events;
      var h = total ? Math.max(3, Math.round(total / max * 110)) : 3;
      return '<div class="chart-col"><span class="chart-count">' + (total || '') + '</span>' +
        '<span class="chart-bar" style="height:' + h + 'px"></span>' +
        '<span class="chart-day">' + esc(d.label.split(' ')[0]) + '</span></div>';
    }).join('');
    canvas.parentNode.innerHTML = '<div class="chart">' + bars + '</div>';
    return;
  }

  if (chart) { chart.destroy(); chart = null; }

  var styles = getComputedStyle(document.documentElement);
  var line = styles.getPropertyValue('--c-border').trim() || '#ddd';
  var muted = styles.getPropertyValue('--c-text-muted').trim() || '#888';

  chart = new window.Chart(canvas, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        { label: 'Отзывы', data: days.map(function (d) { return d.reviews; }), borderColor: '#1AA3A3', backgroundColor: 'rgba(26,163,163,0.15)', tension: 0.35, fill: true, pointRadius: 2 },
        { label: 'Фото', data: days.map(function (d) { return d.photos; }), borderColor: '#E5A13A', backgroundColor: 'rgba(229,161,58,0.15)', tension: 0.35, fill: true, pointRadius: 2 },
        { label: 'Просмотры', data: days.map(function (d) { return d.events; }), borderColor: '#8B5CF6', backgroundColor: 'rgba(139,92,246,0.12)', tension: 0.35, fill: true, pointRadius: 2 }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: muted, maxRotation: 0 } },
        y: { beginAtZero: true, grid: { color: line }, ticks: { color: muted, precision: 0 } }
      }
    }
  });
}

/* ---------- пользователи ---------- */

async function loadUsers() {
  var sc = state.users;
  var content = $('admin-content');
  content.innerHTML = skeleton(8);

  var q = supabase.from('profiles')
    .select('id, username, email, age, gender, role, ban, avatar_url, created_at', { count: 'exact' });

  var search = sc.search.replace(/[,()%]/g, ' ').trim();
  if (search) q = q.or('username.ilike.%' + search + '%,email.ilike.%' + search + '%');
  if (sc.filter === 'banned') q = q.eq('ban', true);
  if (sc.filter === 'admins') q = q.eq('role', 'admin');

  var res = await q.order('created_at', { ascending: false }).range(sc.page * PAGE, sc.page * PAGE + PAGE - 1);
  if (res.error) {
    content.innerHTML = '<p class="empty-note">Не получилось загрузить пользователей: ' + esc(res.error.message) + '</p>';
    return;
  }

  sc.rows = res.data || [];
  sc.count = res.count || 0;

  var selectedCount = Object.keys(sc.selected).length;

  var html = '<div class="toolbar">' +
    '<input type="search" id="users-search" placeholder="Поиск по логину или email" value="' + esc(sc.search) + '">' +
    '<select id="users-filter" aria-label="Фильтр пользователей">' +
    '<option value="all"' + (sc.filter === 'all' ? ' selected' : '') + '>Все</option>' +
    '<option value="banned"' + (sc.filter === 'banned' ? ' selected' : '') + '>Забаненные</option>' +
    '<option value="admins"' + (sc.filter === 'admins' ? ' selected' : '') + '>Админы</option>' +
    '</select>' +
    '<button class="btn btn-outline btn-sm" type="button" data-act="export-users">' +
    '<span class="icon i-download" aria-hidden="true"></span><span>CSV</span></button>' +
    '</div>';

  if (selectedCount) {
    html += '<div class="bulk-bar">Выбрано: ' + selectedCount +
      '<button class="btn btn-outline btn-sm" type="button" data-act="bulk" data-op="ban" data-kind="users">Забанить</button>' +
      '<button class="btn btn-outline btn-sm" type="button" data-act="bulk" data-op="unban" data-kind="users">Разбанить</button>' +
      '<button class="btn btn-danger btn-sm" type="button" data-act="bulk" data-op="delete" data-kind="users">Удалить</button>' +
      '</div>';
  }

  html += '<div class="table-wrap"><table class="admin-table"><thead><tr>' +
    '<th><input type="checkbox" data-act="sel-all" data-kind="users" aria-label="Выбрать всех на странице"></th>' +
    '<th></th><th>Логин</th><th>Email</th><th>Возраст</th><th>Пол</th><th>Регистрация</th><th>Роль</th><th>Статус</th><th>Действия</th>' +
    '</tr></thead><tbody>';

  if (!sc.rows.length) {
    html += '<tr><td colspan="10"><p class="empty-note">Никого не найдено.</p></td></tr>';
  }

  sc.rows.forEach(function (u) {
    var self = state.me && u.id === state.me.id;
    var name = u.username || (u.email || '').split('@')[0] || 'Аноним';
    var avatar = u.avatar_url
      ? '<img class="avatar-img" src="' + esc(u.avatar_url) + '" alt="">'
      : '<span class="avatar" style="background:' + avatarColor(name) + '">' + esc(name.trim().charAt(0).toUpperCase() || 'А') + '</span>';
    html += '<tr>' +
      '<td><input type="checkbox" data-act="sel" data-kind="users" data-id="' + u.id + '"' +
      (sc.selected[u.id] ? ' checked' : '') + ' aria-label="Выбрать ' + esc(name) + '"></td>' +
      '<td>' + avatar + '</td>' +
      '<td>' + esc(name) + (self ? ' <span class="badge">это ты</span>' : '') + '</td>' +
      '<td>' + esc(u.email || '—') + '</td>' +
      '<td>' + (u.age == null ? '—' : u.age) + '</td>' +
      '<td>' + esc(u.gender || '—') + '</td>' +
      '<td>' + fmtDate(u.created_at) + '</td>' +
      '<td>' + (u.role === 'admin' ? '<span class="badge is-admin">admin</span>' : '<span class="badge">user</span>') + '</td>' +
      '<td>' + (u.ban ? '<span class="badge is-banned">забанен</span>' : '<span class="badge is-ok">активен</span>') + '</td>' +
      '<td class="row-actions">' +
      '<button class="btn btn-outline btn-sm" type="button" data-act="user" data-op="' + (u.ban ? 'unban' : 'ban') + '" data-id="' + u.id + '">' +
      (u.ban ? 'Разбанить' : 'Забанить') + '</button> ' +
      (u.role === 'admin'
        ? '<button class="btn btn-outline btn-sm" type="button" data-act="user" data-op="demote" data-id="' + u.id + '"' + (self ? ' disabled' : '') + '>Снять админа</button>'
        : '<button class="btn btn-outline btn-sm" type="button" data-act="user" data-op="promote" data-id="' + u.id + '">В админы</button>') + ' ' +
      '<button class="btn btn-outline btn-sm" type="button" data-act="user" data-op="reset" data-id="' + u.id + '">Сбросить пароль</button> ' +
      '<button class="btn btn-danger btn-sm" type="button" data-act="user" data-op="delete" data-id="' + u.id + '"' + (self ? ' disabled' : '') + '>' +
      '<span class="icon i-trash" aria-hidden="true"></span><span>Удалить</span></button>' +
      '</td></tr>';
  });

  html += '</tbody></table></div>' + pagerHtml('users', sc);
  content.innerHTML = html;

  if (sc.focusSearch) {
    var searchEl = $('users-search');
    if (searchEl) {
      searchEl.focus();
      searchEl.setSelectionRange(searchEl.value.length, searchEl.value.length);
    }
    sc.focusSearch = false;
  }
}

async function exportUsersCsv() {
  var sc = state.users;
  var search = sc.search.replace(/[,()%]/g, ' ').trim();
  var build = function () {
    var q = supabase.from('profiles')
      .select('id, username, email, age, gender, role, ban, created_at');
    if (search) q = q.or('username.ilike.%' + search + '%,email.ilike.%' + search + '%');
    if (sc.filter === 'banned') q = q.eq('ban', true);
    if (sc.filter === 'admins') q = q.eq('role', 'admin');
    return q.order('created_at', { ascending: false });
  };
  var res = await fetchAllChunks(build, 5000);
  if (res.error) { toast('Не получилось выгрузить: ' + res.error.message, true); return; }
  csvDownload('gdz-nel-users-' + new Date().toISOString().slice(0, 10) + '.csv',
    ['id', 'логин', 'email', 'возраст', 'пол', 'роль', 'бан', 'регистрация'],
    res.rows.map(function (u) {
      return [u.id, u.username || '', u.email || '', u.age == null ? '' : u.age,
        u.gender || '', u.role || '', u.ban ? 'да' : 'нет', u.created_at || ''];
    }));
  toast('Выгружено строк: ' + res.rows.length);
  logAction('export_users', sc.filter + (search ? ' / ' + search : ''), { rows: res.rows.length });
}

/* ---------- отзывы и ИИ-логи ---------- */

async function loadReviewTable(kind) {
  var sc = state[kind];
  var isAi = kind === 'ai';
  var content = $('admin-content');
  content.innerHTML = skeleton(8);

  var q = supabase.from('reviews').select('*', { count: 'exact' });
  if (isAi) q = q.eq('ai_status', 'rejected');
  else if (sc.filter !== 'all') q = q.eq('ai_status', sc.filter);

  var search = String(sc.search || '').replace(/[,()%]/g, ' ').trim();
  if (search) q = q.or('text.ilike.%' + search + '%,username.ilike.%' + search + '%,task_id.ilike.%' + search + '%');

  var res = await q.order('created_at', { ascending: false }).range(sc.page * PAGE, sc.page * PAGE + PAGE - 1);
  if (res.error) {
    content.innerHTML = '<p class="empty-note">Не получилось загрузить отзывы: ' + esc(res.error.message) + '</p>';
    return;
  }

  sc.rows = res.data || [];
  sc.count = res.count || 0;

  var selectedCount = Object.keys(sc.selected || {}).length;
  var html;

  if (!isAi) {
    var filters = [['all', 'Все'], ['pending', 'На проверке'], ['approved', 'Одобренные'], ['rejected', 'Отклонённые']];
    html = '<div class="toolbar">' +
      '<input type="search" id="reviews-search" placeholder="Поиск по тексту, автору, заданию" value="' + esc(sc.search) + '">' +
      '<div class="chips">' + filters.map(function (f) {
        return '<button class="chip' + (sc.filter === f[0] ? ' is-active' : '') + '" type="button" ' +
          'data-act="reviews-filter" data-value="' + f[0] + '">' + f[1] + '</button>';
      }).join('') + '</div>' +
      '<button class="btn btn-outline btn-sm" type="button" data-act="export-reviews">' +
      '<span class="icon i-download" aria-hidden="true"></span><span>CSV</span></button>' +
      '</div>';
  } else {
    html = '<p class="admin-muted" style="margin-bottom:14px">Отзывы, которые ИИ-модератор отклонил. ' +
      'Если ИИ ошибся — «Разрешить вручную» опубликует отзыв.</p>';
  }

  if (selectedCount) {
    html += '<div class="bulk-bar">Выбрано: ' + selectedCount +
      '<button class="btn btn-outline btn-sm" type="button" data-act="bulk" data-op="approve" data-kind="' + kind + '">Одобрить</button>' +
      '<button class="btn btn-outline btn-sm" type="button" data-act="bulk" data-op="reject" data-kind="' + kind + '">Отклонить</button>' +
      '<button class="btn btn-danger btn-sm" type="button" data-act="bulk" data-op="delete" data-kind="' + kind + '">Удалить</button>' +
      '</div>';
  }

  html += '<div class="table-wrap"><table class="admin-table"><thead><tr>' +
    '<th><input type="checkbox" data-act="sel-all" data-kind="' + kind + '" aria-label="Выбрать всех на странице"></th>' +
    '<th>Автор</th><th>Задание</th><th>Текст</th><th>Оценка</th><th>Статус</th><th>Дата</th><th>Действия</th>' +
    '</tr></thead><tbody>';

  if (!sc.rows.length) {
    html += '<tr><td colspan="8"><p class="empty-note">' +
      (isAi ? 'Отклонённых отзывов нет — ИИ пока никого не отклонил.' : 'Отзывов не найдено.') +
      '</p></td></tr>';
  }

  sc.rows.forEach(function (r) {
    html += '<tr>' +
      '<td><input type="checkbox" data-act="sel" data-kind="' + kind + '" data-id="' + r.id + '"' +
      ((sc.selected || {})[r.id] ? ' checked' : '') + ' aria-label="Выбрать отзыв"></td>' +
      '<td>' + esc(r.username || 'Аноним') + '</td>' +
      '<td class="cell-task">' + esc(r.task_id) + '</td>' +
      '<td><div class="cell-text">' + esc(r.text) + '</div></td>' +
      '<td>' + starsMini(r.rating) + '</td>' +
      '<td>' + statusBadge(r.ai_status) + '</td>' +
      '<td>' + fmtDate(r.created_at) + '</td>' +
      '<td class="row-actions">' +
      (r.ai_status !== 'approved'
        ? '<button class="btn btn-outline btn-sm" type="button" data-act="review" data-op="approve" data-id="' + r.id + '">' +
          (isAi ? 'Разрешить вручную' : 'Одобрить') + '</button> '
        : '') +
      (!isAi && r.ai_status !== 'rejected'
        ? '<button class="btn btn-outline btn-sm" type="button" data-act="review" data-op="reject" data-id="' + r.id + '">Отклонить</button> '
        : '') +
      '<button class="btn btn-danger btn-sm" type="button" data-act="review" data-op="delete" data-id="' + r.id + '">' +
      '<span class="icon i-trash" aria-hidden="true"></span><span>Удалить</span></button>' +
      '</td></tr>';
  });

  html += '</tbody></table></div>' + pagerHtml(kind, sc);
  content.innerHTML = html;

  if (sc.focusSearch) {
    var revSearch = $('reviews-search');
    if (revSearch) {
      revSearch.focus();
      revSearch.setSelectionRange(revSearch.value.length, revSearch.value.length);
    }
    sc.focusSearch = false;
  }
}

async function exportReviewsCsv() {
  var sc = state.reviews;
  var search = String(sc.search || '').replace(/[,()%]/g, ' ').trim();
  var build = function () {
    var q = supabase.from('reviews')
      .select('id, username, task_id, rating, text, ai_status, ai_reason, created_at');
    if (sc.filter !== 'all') q = q.eq('ai_status', sc.filter);
    if (search) q = q.or('text.ilike.%' + search + '%,username.ilike.%' + search + '%,task_id.ilike.%' + search + '%');
    return q.order('created_at', { ascending: false });
  };
  var res = await fetchAllChunks(build, 5000);
  if (res.error) { toast('Не получилось выгрузить: ' + res.error.message, true); return; }
  csvDownload('gdz-nel-reviews-' + new Date().toISOString().slice(0, 10) + '.csv',
    ['id', 'автор', 'задание', 'оценка', 'текст', 'статус', 'причина ИИ', 'дата'],
    res.rows.map(function (r) {
      return [r.id, r.username || '', r.task_id || '', r.rating, r.text || '',
        r.ai_status || '', r.ai_reason || '', r.created_at || ''];
    }));
  toast('Выгружено строк: ' + res.rows.length);
  logAction('export_reviews', sc.filter, { rows: res.rows.length });
}

/* ---------- фото-логи ---------- */

function storagePath(url) {
  var marker = '/storage/v1/object/public/photos/';
  var idx = String(url || '').indexOf(marker);
  if (idx === -1) return null;
  try {
    return decodeURIComponent(String(url).slice(idx + marker.length));
  } catch (err) {
    return String(url).slice(idx + marker.length);
  }
}

async function loadPhotos() {
  var sc = state.photos;
  var content = $('admin-content');
  content.innerHTML = skeleton(6);

  var res = await supabase.from('photo_requests').select('*', { count: 'exact' })
    .order('created_at', { ascending: false }).range(sc.page * PAGE, sc.page * PAGE + PAGE - 1);
  if (res.error) {
    content.innerHTML = '<p class="empty-note">Не получилось загрузить фото: ' + esc(res.error.message) + '</p>';
    return;
  }

  sc.rows = res.data || [];
  sc.count = res.count || 0;

  var ids = [];
  sc.rows.forEach(function (r) { if (ids.indexOf(r.user_id) === -1) ids.push(r.user_id); });
  var names = {};
  if (ids.length) {
    var pres = await supabase.from('profiles').select('id, username, email').in('id', ids);
    (pres.data || []).forEach(function (p) { names[p.id] = p.username || p.email || '—'; });
  }

  var html = '<div class="table-wrap"><table class="admin-table"><thead><tr>' +
    '<th>Пользователь</th><th>Фото</th><th>Время</th><th>Действия</th>' +
    '</tr></thead><tbody>';

  if (!sc.rows.length) {
    html += '<tr><td colspan="4"><p class="empty-note">Фото ещё не отправляли.</p></td></tr>';
  }

  sc.rows.forEach(function (r) {
    var url = esc(r.image_url);
    html += '<tr>' +
      '<td>' + esc(names[r.user_id] || r.user_id.slice(0, 8)) + '</td>' +
      '<td><a href="' + url + '" target="_blank" rel="noopener">' +
      '<img class="thumb" src="' + url + '" alt="Фото задания" loading="lazy"></a></td>' +
      '<td>' + fmtDate(r.created_at) + '</td>' +
      '<td class="row-actions">' +
      '<button class="btn btn-outline btn-sm" type="button" data-act="photo" data-op="view" data-id="' + r.id + '">Ответ</button> ' +
      '<button class="btn btn-outline btn-sm" type="button" data-act="photo" data-op="copy" data-url="' + url + '">Ссылка</button> ' +
      '<button class="btn btn-danger btn-sm" type="button" data-act="photo" data-op="delete" data-id="' + r.id +
      '" data-url="' + url + '"><span class="icon i-trash" aria-hidden="true"></span><span>Удалить</span></button>' +
      '</td></tr>' +
      '<tr id="answer-' + r.id + '" hidden><td colspan="4" style="background:var(--c-surface-2)">' +
      '<div class="answer-cell">' + esc(r.ai_response || 'Ответа нет — запрос не завершился.') + '</div>' +
      '</td></tr>';
  });

  html += '</tbody></table></div>' + pagerHtml('photos', sc);
  content.innerHTML = html;
}

/* ---------- достижения (Ф16.11) ---------- */

async function loadAchievements() {
  var sc = state.achievements;
  var content = $('admin-content');
  content.innerHTML = skeleton(6);

  var res = await Promise.all([
    supabase.from('achievements').select('badge_type, unlocked_at, user_id', { count: 'exact' })
      .order('unlocked_at', { ascending: false }).range(0, 999),
    supabase.rpc('achievement_top', { limit_n: 5 }),
    countOf('achievements')
  ]);

  var rows = res[0].data || [];
  var total = res[2];
  var top = res[1].data || [];

  var byType = {};
  rows.forEach(function (r) { byType[r.badge_type] = (byType[r.badge_type] || 0) + 1; });

  var ids = [];
  rows.slice(0, 30).forEach(function (r) { if (ids.indexOf(r.user_id) === -1) ids.push(r.user_id); });
  var names = {};
  if (ids.length) {
    var pres = await supabase.from('profiles').select('id, username, email').in('id', ids);
    (pres.data || []).forEach(function (p) { names[p.id] = p.username || p.email || '—'; });
  }

  function typeCard(id, title) {
    var staticTitles = { welcome: 'Добро пожаловать', review1: 'Первый отзыв', tasks10: 'Десять задач', tasks100: 'Сто задач' };
    var name = staticTitles[id] || badgeTitle(id);
    return '<div class="dash-card"><span class="dash-card-icon"><span class="icon i-award" aria-hidden="true"></span></span>' +
      '<span><span class="dash-card-value">' + (byType[id] || 0) + '</span><br>' +
      '<span class="dash-card-label">' + esc(name) + '</span></span></div>';
  }

  var dailyCount = Object.keys(byType).filter(function (k) { return /^daily-/.test(k); })
    .reduce(function (sum, k) { return sum + byType[k]; }, 0);

  var recent = rows.slice(0, 20).map(function (r) {
    return '<tr><td>' + esc(names[r.user_id] || r.user_id.slice(0, 8)) + '</td>' +
      '<td>' + esc(badgeTitle(r.badge_type)) + '</td>' +
      '<td class="cell-task">' + esc(r.badge_type) + '</td>' +
      '<td>' + fmtDate(r.unlocked_at) + '</td></tr>';
  }).join('');

  content.innerHTML =
    '<div class="dash-cards">' +
    typeCard('welcome', 'welcome') +
    typeCard('review1', 'review1') +
    typeCard('tasks10', 'tasks10') +
    typeCard('tasks100', 'tasks100') +
    '<div class="dash-card"><span class="dash-card-icon"><span class="icon i-check" aria-hidden="true"></span></span>' +
    '<span><span class="dash-card-value">' + dailyCount + '</span><br>' +
    '<span class="dash-card-label">Дневные отметки</span></span></div>' +
    '<div class="dash-card"><span class="dash-card-icon"><span class="icon i-chart" aria-hidden="true"></span></span>' +
    '<span><span class="dash-card-value">' + total + '</span><br>' +
    '<span class="dash-card-label">Всего выдано</span></span></div>' +
    '</div>' +
    '<div class="dash-grid">' +
    '<div class="panel"><h2>Топ по достижениям</h2>' +
    (top.length
      ? '<ul class="mini-list">' + top.map(function (t) {
          return '<li><span>' + esc(t.username || '—') + '</span><b>' + t.badges + '</b></li>';
        }).join('') + '</ul>'
      : '<p class="admin-muted">Пока пусто.</p>') +
    '</div>' +
    '<div class="panel"><h2>Последние достижения</h2>' +
    '<div class="table-wrap"><table class="admin-table"><thead><tr>' +
    '<th>Пользователь</th><th>Достижение</th><th>Код</th><th>Когда</th></tr></thead><tbody>' +
    (recent || '<tr><td colspan="4"><p class="empty-note">Пока пусто.</p></td></tr>') +
    '</tbody></table></div></div>';

  sc.count = total;
}

/* ---------- действия ---------- */

async function userOp(id, op) {
  var sc = state.users;
  var user = sc.rows.filter(function (u) { return u.id === id; })[0];
  var name = user ? (user.username || user.email) : id.slice(0, 8);

  var ok;
  if (op === 'ban') {
    ok = await openModal({
      title: 'Забанить пользователя?',
      body: '<p>«' + esc(name) + '» больше не сможет оставлять отзывы и решать по фото.</p>',
      confirmText: 'Забанить', danger: true
    });
  } else if (op === 'unban') {
    ok = await openModal({ title: 'Разбанить?', body: '<p>«' + esc(name) + '» снова сможет оставлять отзывы и решать по фото.</p>', confirmText: 'Разбанить' });
  } else if (op === 'promote') {
    ok = await openModal({ title: 'Выдать роль админа?', body: '<p>«' + esc(name) + '» получит полный доступ к админке.</p>', confirmText: 'Выдать' });
  } else if (op === 'demote') {
    ok = await openModal({ title: 'Снять роль админа?', body: '<p>«' + esc(name) + '» станет обычным пользователем.</p>', confirmText: 'Снять' });
  } else if (op === 'reset') {
    ok = await openModal({
      title: 'Сбросить пароль?',
      body: '<p>На почту <b>' + esc(user ? user.email : '') + '</b> уйдёт письмо со ссылкой для смены пароля.</p>',
      confirmText: 'Отправить письмо'
    });
  } else if (op === 'delete') {
    ok = await openModal({
      title: 'Удалить аккаунт навсегда?',
      body: '<p>«' + esc(name) + '» исчезнет вместе с отзывами, фото, историей и достижениями. Это необратимо.</p>',
      confirmText: 'Удалить', danger: true
    });
  }
  if (!ok) return;

  var res;
  if (op === 'ban') res = await supabase.from('profiles').update({ ban: true }).eq('id', id);
  else if (op === 'unban') res = await supabase.from('profiles').update({ ban: false }).eq('id', id);
  else if (op === 'promote') res = await supabase.from('profiles').update({ role: 'admin' }).eq('id', id);
  else if (op === 'demote') res = await supabase.from('profiles').update({ role: 'user' }).eq('id', id);
  else if (op === 'reset') {
    var redirect = location.href.split('/admin/')[0] + '/auth.html?reset=1';
    res = await supabase.auth.resetPasswordForEmail(user ? user.email : '', { redirectTo: redirect });
  } else if (op === 'delete') res = await supabase.rpc('admin_delete_user', { target: id });

  if (res && res.error) { toast('Не получилось: ' + res.error.message, true); return; }
  logAction('user_' + op, name || id, user && user.email ? { email: user.email } : null);
  toast(op === 'reset' ? 'Письмо отправлено' : 'Готово');
  loadUsers();
}

async function bulkOp(kind, op) {
  var sc = state[kind];
  var ids = Object.keys(sc.selected || {});
  if (!ids.length) return;

  var titles = {
    ban: 'Забанить выбранных (' + ids.length + ')?',
    unban: 'Разбанить выбранных (' + ids.length + ')?',
    delete: 'Удалить выбранное (' + ids.length + ')?',
    approve: 'Одобрить выбранные отзывы (' + ids.length + ')?',
    reject: 'Отклонить выбранные отзывы (' + ids.length + ')?'
  };
  var ok = await openModal({
    title: titles[op] || 'Продолжить?',
    body: op === 'delete' ? '<p>Действие необратимо.</p>' : '',
    confirmText: 'Продолжить',
    danger: op === 'delete' || op === 'ban' || op === 'reject'
  });
  if (!ok) return;

  var fails = 0;
  for (var i = 0; i < ids.length; i++) {
    var id = ids[i];
    var res;
    if (kind === 'users') {
      if (op === 'ban') res = await supabase.from('profiles').update({ ban: true }).eq('id', id);
      else if (op === 'unban') res = await supabase.from('profiles').update({ ban: false }).eq('id', id);
      else if (op === 'delete') res = await supabase.rpc('admin_delete_user', { target: id });
    } else {
      if (op === 'approve') res = await supabase.from('reviews').update({ is_approved: true, ai_status: 'approved' }).eq('id', id);
      else if (op === 'reject') res = await supabase.from('reviews').update({ is_approved: false, ai_status: 'rejected' }).eq('id', id);
      else if (op === 'delete') res = await supabase.from('reviews').delete().eq('id', id);
    }
    if (res && res.error) fails++;
  }

  logAction('bulk_' + kind + '_' + op, null, { count: ids.length, fails: fails });
  toast(fails ? ('Готово, ошибок: ' + fails) : ('Готово: ' + ids.length), !!fails);
  sc.selected = {};
  route();
}

async function reviewOp(id, op) {
  if (op === 'delete') {
    var ok = await openModal({ title: 'Удалить отзыв навсегда?', body: '<p>Действие необратимо.</p>', confirmText: 'Удалить', danger: true });
    if (!ok) return;
  }
  if (op === 'approve') {
    var ok2 = await openModal({ title: 'Опубликовать отзыв?', body: '<p>Отзыв увидят все посетители.</p>', confirmText: 'Опубликовать' });
    if (!ok2) return;
  }

  var res;
  if (op === 'approve') res = await supabase.from('reviews').update({ is_approved: true, ai_status: 'approved' }).eq('id', id);
  else if (op === 'reject') res = await supabase.from('reviews').update({ is_approved: false, ai_status: 'rejected' }).eq('id', id);
  else if (op === 'delete') res = await supabase.from('reviews').delete().eq('id', id);

  if (res && res.error) { toast('Не получилось: ' + res.error.message, true); return; }
  logAction('review_' + op, String(id));
  toast('Готово');
  route();
}

async function photoOp(id, op, url) {
  if (op === 'view') {
    var row = $('answer-' + id);
    if (row) row.hidden = !row.hidden;
    return;
  }
  if (op === 'copy') {
    try {
      await navigator.clipboard.writeText(url);
      toast('Ссылка скопирована');
    } catch (err) {
      toast('Не получилось скопировать', true);
    }
    return;
  }
  if (op === 'delete') {
    var ok = await openModal({
      title: 'Удалить фото?',
      body: '<p>Файл и запись о нём исчезнут навсегда.</p>',
      confirmText: 'Удалить', danger: true
    });
    if (!ok) return;
    var path = storagePath(url);
    if (path) {
      var rm = await supabase.storage.from('photos').remove([path]);
      if (rm.error) toast('Файл не удалился: ' + rm.error.message, true);
    }
    var res = await supabase.from('photo_requests').delete().eq('id', id);
    if (res.error) { toast('Не получилось удалить запись: ' + res.error.message, true); return; }
    logAction('photo_delete', String(id));
    toast('Удалено');
    loadPhotos();
  }
}

/* ---------- события ---------- */

function onContentClick(event) {
  var el = event.target.closest('[data-act]');
  if (!el) return;
  var act = el.getAttribute('data-act');

  if (act === 'page') {
    var tab = el.getAttribute('data-tab');
    var sc = state[tab];
    var pages = Math.max(1, Math.ceil(sc.count / PAGE));
    sc.page = Math.min(Math.max(0, sc.page + Number(el.getAttribute('data-dir'))), pages - 1);
    route();
    window.scrollTo(0, 0);
    return;
  }

  if (act === 'sel') {
    var kind = el.getAttribute('data-kind');
    var id = el.getAttribute('data-id');
    var bag = state[kind].selected || (state[kind].selected = {});
    if (el.checked) bag[id] = true; else delete bag[id];
    // перерисовываем панель массовых операций без полной перезагрузки
    if (kind === 'users') loadUsers();
    else loadReviewTable(kind);
    return;
  }

  if (act === 'sel-all') {
    var kind2 = el.getAttribute('data-kind');
    var sc2 = state[kind2];
    sc2.selected = sc2.selected || {};
    if (el.checked) {
      sc2.rows.forEach(function (row) { sc2.selected[row.id] = true; });
    } else {
      sc2.selected = {};
    }
    if (kind2 === 'users') loadUsers();
    else loadReviewTable(kind2);
    return;
  }

  if (act === 'export-users') { exportUsersCsv(); return; }
  if (act === 'export-reviews') { exportReviewsCsv(); return; }
  if (act === 'bulk') { bulkOp(el.getAttribute('data-kind'), el.getAttribute('data-op')); return; }

  if (act === 'reviews-filter') {
    state.reviews.filter = el.getAttribute('data-value');
    state.reviews.page = 0;
    state.reviews.selected = {};
    loadReviewTable('reviews');
    return;
  }

  if (act === 'user') { userOp(el.getAttribute('data-id'), el.getAttribute('data-op')); return; }
  if (act === 'review') { reviewOp(el.getAttribute('data-id'), el.getAttribute('data-op')); return; }
  if (act === 'photo') { photoOp(el.getAttribute('data-id'), el.getAttribute('data-op'), el.getAttribute('data-url')); }
}

var searchTimer = 0;
function onContentInput(event) {
  var id = event.target.id;
  if (id !== 'users-search' && id !== 'reviews-search') return;
  var value = event.target.value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function () {
    if (id === 'users-search') {
      state.users.search = value.trim();
      state.users.page = 0;
      state.users.focusSearch = true;
      loadUsers();
    } else {
      state.reviews.search = value.trim();
      state.reviews.page = 0;
      state.reviews.focusSearch = true;
      loadReviewTable('reviews');
    }
  }, 350);
}

function onContentChange(event) {
  if (event.target.id === 'users-filter') {
    state.users.filter = event.target.value;
    state.users.page = 0;
    state.users.selected = {};
    loadUsers();
  }
}

/* ---------- роутинг ---------- */

function route() {
  var tab = (location.hash || '#overview').replace('#', '') || 'overview';
  if (['overview', 'users', 'reviews', 'ai', 'photos', 'achievements'].indexOf(tab) === -1) tab = 'overview';
  state.tab = tab;

  Array.prototype.forEach.call(document.querySelectorAll('.admin-nav a'), function (a) {
    a.classList.toggle('is-active', a.getAttribute('data-tab') === tab);
  });

  var titles = {
    overview: 'Обзор',
    users: 'Пользователи',
    reviews: 'Модерация отзывов',
    ai: 'ИИ-логи',
    photos: 'Фото-логи',
    achievements: 'Достижения'
  };
  $('admin-title').textContent = titles[tab];

  if (tab === 'overview') renderOverview();
  else if (tab === 'users') loadUsers();
  else if (tab === 'reviews') loadReviewTable('reviews');
  else if (tab === 'ai') loadReviewTable('ai');
  else if (tab === 'achievements') loadAchievements();
  else loadPhotos();
}

function wireTheme() {
  var root = document.documentElement;
  var theme = null;
  try { theme = localStorage.getItem('gdz-nel-theme'); } catch (err) { /* ignore */ }
  if (!theme) theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  root.setAttribute('data-theme', theme);

  function syncIcon() {
    var icon = $('theme-toggle').querySelector('.icon');
    icon.classList.toggle('i-sun', root.getAttribute('data-theme') === 'dark');
    icon.classList.toggle('i-moon', root.getAttribute('data-theme') !== 'dark');
  }
  syncIcon();

  $('theme-toggle').addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('gdz-nel-theme', next); } catch (err) { /* ignore */ }
    syncIcon();
    if (state.tab === 'overview') renderOverview();
  });
}

// простая проверка «не робот» (Ф24.6): полноценная капча — на стороне
// провайдера (см. docs/SUPABASE.md, hCaptcha); здесь только комментарий-напоминание.

(async function boot() {
  try {
    var session = await getSession();
    if (!session) {
      location.replace('../auth.html?next=' + encodeURIComponent('admin/index.html'));
      return;
    }

    var res = await supabase.from('profiles').select('*').eq('id', session.user.id).single();
    var me = res.data;

    if (!me || me.role !== 'admin') {
      $('admin-loading').hidden = true;
      $('admin-denied').hidden = false;
      return;
    }

    state.me = me;

    $('admin-loading').hidden = true;
    $('admin').hidden = false;
    $('admin-name').textContent = me.username || me.email || 'админ';
    if (me.avatar_url) {
      $('admin-avatar').outerHTML = '<img class="avatar-img avatar-img--lg" id="admin-avatar" src="' +
        esc(me.avatar_url) + '" alt="">';
    } else {
      var letter = String(me.username || 'А').trim().charAt(0).toUpperCase() || 'А';
      $('admin-avatar').textContent = letter;
      $('admin-avatar').style.background = avatarColor(me.username || 'А');
    }

    $('logout').addEventListener('click', async function () {
      await supabase.auth.signOut();
      location.replace('../index.html');
    });

    var refresh = $('refresh-btn');
    if (refresh) {
      refresh.addEventListener('click', function () {
        refresh.classList.add('is-spinning');
        Promise.resolve(route()).then(function () {
          setTimeout(function () { refresh.classList.remove('is-spinning'); }, 500);
        });
      });
    }

    wireTheme();

    var content = $('admin-content');
    content.addEventListener('click', onContentClick);
    content.addEventListener('input', onContentInput);
    content.addEventListener('change', onContentChange);

    // realtime: новые отзывы и фото (Ф9.14)
    supabase.channel('admin-live')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'reviews' }, function (payload) {
        toast('Новый отзыв от ' + ((payload.new && payload.new.username) || 'анонима'));
        if (state.tab === 'reviews' || state.tab === 'overview') route();
      })
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'photo_requests' }, function () {
        toast('Новый запрос «решить по фото»');
        if (state.tab === 'photos' || state.tab === 'overview') route();
      })
      .subscribe();

    window.addEventListener('hashchange', route);
    route();
  } catch (err) {
    $('admin-loading').textContent = 'Не получилось подключиться к серверу: ' + err.message;
  }
})();
