/* =========================================================
   ГДЗ НЭЛ — админка. Доступ: profiles.role = 'admin'.
   Вкладки: обзор, пользователи, модерация отзывов, ИИ-логи,
   фото-логи. Пагинация по 20 записей.
   ========================================================= */

import { supabase, getSession, escapeHtml as esc, avatarColor } from '../assets/supabase.js';

var PAGE = 20;

var state = {
  tab: 'overview',
  me: null,
  users: { rows: [], page: 0, count: 0, search: '', filter: 'all', focusSearch: false },
  reviews: { rows: [], page: 0, count: 0, filter: 'all' },
  ai: { rows: [], page: 0, count: 0 },
  photos: { rows: [], page: 0, count: 0 }
};

function $(id) { return document.getElementById(id); }

/* ---------- мелкие рендеры ---------- */

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
  toastTimer = setTimeout(function () { el.className = 'admin-toast'; }, 2600);
}

function countOf(table, mod) {
  var q = supabase.from(table).select('id', { count: 'exact', head: true });
  if (mod) q = mod(q);
  return q.then(function (res) { return res.count || 0; });
}

/* ---------- обзор ---------- */

async function renderOverview() {
  var content = $('admin-content');
  content.innerHTML = '<p class="admin-muted">Считаю статистику…</p>';

  var dayAgo = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  var weekAgo = new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString();

  var res = await Promise.all([
    countOf('profiles'),
    countOf('reviews'),
    countOf('reviews', function (q) { return q.eq('ai_status', 'pending'); }),
    countOf('photo_requests', function (q) { return q.gte('created_at', dayAgo); }),
    supabase.from('reviews').select('id, username, task_id, ai_status, created_at').gte('created_at', weekAgo),
    supabase.from('reviews').select('id, username, task_id, ai_status, created_at')
      .order('created_at', { ascending: false }).limit(5),
    supabase.from('photo_requests').select('id, user_id, created_at')
      .order('created_at', { ascending: false }).limit(5)
  ]);

  var usersCount = res[0];
  var reviewsCount = res[1];
  var pendingCount = res[2];
  var photosToday = res[3];
  var weekRows = (res[4].data || []);
  var lastReviews = (res[5].data || []);
  var lastPhotos = (res[6].data || []);

  // столбики по дням за неделю
  var days = [];
  var byKey = {};
  for (var i = 6; i >= 0; i--) {
    var d = new Date(Date.now() - i * 86400000);
    var item = { key: d.toISOString().slice(0, 10), label: d.toLocaleDateString('ru-RU', { weekday: 'short' }), count: 0 };
    days.push(item);
    byKey[item.key] = item;
  }
  weekRows.forEach(function (row) {
    var bucket = byKey[String(row.created_at).slice(0, 10)];
    if (bucket) bucket.count++;
  });
  var maxCount = 1;
  days.forEach(function (day) { if (day.count > maxCount) maxCount = day.count; });

  var bars = days.map(function (day) {
    var h = day.count ? Math.max(3, Math.round(day.count / maxCount * 110)) : 3;
    return '<div class="chart-col">' +
      '<span class="chart-count">' + (day.count || '') + '</span>' +
      '<span class="chart-bar" style="height:' + h + 'px"></span>' +
      '<span class="chart-day">' + esc(day.label) + '</span></div>';
  }).join('');

  // лента последних действий
  var statusWord = { pending: 'на проверке', approved: 'одобрен', rejected: 'отклонён' };
  var feed = [];
  lastReviews.forEach(function (rv) {
    feed.push({
      ts: rv.created_at,
      icon: 'i-message',
      text: 'Отзыв ' + (statusWord[rv.ai_status] || rv.ai_status) + ' — ' + (rv.username || 'аноним') + ', ' + rv.task_id
    });
  });
  lastPhotos.forEach(function (p) {
    feed.push({ ts: p.created_at, icon: 'i-camera', text: 'Фото на решение' });
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

  content.innerHTML =
    '<div class="dash-cards">' +
    card('i-user', usersCount, 'Всего пользователей') +
    card('i-message', reviewsCount, 'Всего отзывов') +
    card('i-clock', pendingCount, 'Ожидают модерации') +
    card('i-camera', photosToday, 'Фото за сутки') +
    '</div>' +
    '<div class="dash-grid">' +
    '<div class="panel"><h2>Отзывы за 7 дней</h2><div class="chart">' + bars + '</div></div>' +
    '<div class="panel"><h2>Последние действия</h2>' + feedHtml + '</div>' +
    '</div>';
}

/* ---------- пользователи ---------- */

async function loadUsers() {
  var sc = state.users;
  var content = $('admin-content');
  content.innerHTML = '<p class="admin-muted">Загружаю…</p>';

  var q = supabase.from('profiles')
    .select('id, username, email, age, gender, role, ban, created_at', { count: 'exact' });

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

  var html = '<div class="toolbar">' +
    '<input type="search" id="users-search" placeholder="Поиск по логину или email" value="' + esc(sc.search) + '">' +
    '<select id="users-filter" aria-label="Фильтр пользователей">' +
    '<option value="all"' + (sc.filter === 'all' ? ' selected' : '') + '>Все</option>' +
    '<option value="banned"' + (sc.filter === 'banned' ? ' selected' : '') + '>Забаненные</option>' +
    '<option value="admins"' + (sc.filter === 'admins' ? ' selected' : '') + '>Админы</option>' +
    '</select></div>' +
    '<div class="table-wrap"><table class="admin-table"><thead><tr>' +
    '<th></th><th>Логин</th><th>Email</th><th>Возраст</th><th>Пол</th><th>Дата регистрации</th><th>Роль</th><th>Статус</th><th>Действия</th>' +
    '</tr></thead><tbody>';

  if (!sc.rows.length) {
    html += '<tr><td colspan="9"><p class="empty-note">Никого не найдено.</p></td></tr>';
  }

  sc.rows.forEach(function (u) {
    var self = state.me && u.id === state.me.id;
    var name = u.username || (u.email || '').split('@')[0] || 'Аноним';
    html += '<tr>' +
      '<td><span class="avatar" style="background:' + avatarColor(name) + '">' +
      esc(name.trim().charAt(0).toUpperCase() || 'А') + '</span></td>' +
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
        ? '<button class="btn btn-outline btn-sm" type="button" data-act="user" data-op="demote" data-id="' + u.id + '"' +
          (self ? ' disabled' : '') + '>Снять админа</button>'
        : '<button class="btn btn-outline btn-sm" type="button" data-act="user" data-op="promote" data-id="' + u.id + '">Сделать админом</button>') + ' ' +
      '<button class="btn btn-outline btn-sm" type="button" data-act="user" data-op="delete" data-id="' + u.id + '"' +
      (self ? ' disabled' : '') + '><span class="icon i-trash" aria-hidden="true"></span><span>Удалить</span></button>' +
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

/* ---------- отзывы и ИИ-логи ---------- */

async function loadReviewTable(kind) {
  var sc = state[kind];
  var isAi = kind === 'ai';
  var content = $('admin-content');
  content.innerHTML = '<p class="admin-muted">Загружаю…</p>';

  var q = supabase.from('reviews').select('*', { count: 'exact' });
  if (isAi) q = q.eq('ai_status', 'rejected');
  else if (sc.filter !== 'all') q = q.eq('ai_status', sc.filter);

  var res = await q.order('created_at', { ascending: false }).range(sc.page * PAGE, sc.page * PAGE + PAGE - 1);
  if (res.error) {
    content.innerHTML = '<p class="empty-note">Не получилось загрузить отзывы: ' + esc(res.error.message) + '</p>';
    return;
  }

  sc.rows = res.data || [];
  sc.count = res.count || 0;

  var html;
  if (!isAi) {
    var filters = [['all', 'Все'], ['pending', 'На проверке'], ['approved', 'Одобренные'], ['rejected', 'Отклонённые']];
    html = '<div class="toolbar"><div class="chips">' + filters.map(function (f) {
      return '<button class="chip' + (sc.filter === f[0] ? ' is-active' : '') + '" type="button" ' +
        'data-act="reviews-filter" data-value="' + f[0] + '">' + f[1] + '</button>';
    }).join('') + '</div></div>';
  } else {
    html = '<p class="admin-muted" style="margin-bottom:14px">Отзывы, которые ИИ-модератор отклонил. ' +
      'Если ИИ ошибся — «Разрешить вручную» опубликует отзыв.</p>';
  }

  html += '<div class="table-wrap"><table class="admin-table"><thead><tr>' +
    '<th>Автор</th><th>Задание</th><th>Текст</th><th>Оценка</th><th>Статус</th><th>Дата</th><th>Действия</th>' +
    '</tr></thead><tbody>';

  if (!sc.rows.length) {
    html += '<tr><td colspan="7"><p class="empty-note">' +
      (isAi ? 'Отклонённых отзывов нет — ИИ пока никого не отклонил.' : 'Отзывов не найдено.') +
      '</p></td></tr>';
  }

  sc.rows.forEach(function (r) {
    html += '<tr>' +
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
      '<button class="btn btn-outline btn-sm" type="button" data-act="review" data-op="delete" data-id="' + r.id + '">' +
      '<span class="icon i-trash" aria-hidden="true"></span><span>Удалить</span></button>' +
      '</td></tr>';
  });

  html += '</tbody></table></div>' + pagerHtml(kind, sc);
  content.innerHTML = html;
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
  content.innerHTML = '<p class="admin-muted">Загружаю…</p>';

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
      '<button class="btn btn-outline btn-sm" type="button" data-act="photo" data-op="view" data-id="' + r.id + '">Посмотреть ответ</button> ' +
      '<button class="btn btn-outline btn-sm" type="button" data-act="photo" data-op="delete" data-id="' + r.id +
      '" data-url="' + url + '"><span class="icon i-trash" aria-hidden="true"></span><span>Удалить</span></button>' +
      '</td></tr>' +
      '<tr id="answer-' + r.id + '" hidden><td colspan="4" style="background:var(--c-surface-2)">' +
      '<div class="answer-cell">' + esc(r.ai_response || 'Ответа нет — запрос не завершился.') + '</div>' +
      '</td></tr>';
  });

  html += '</tbody></table></div>' + pagerHtml('photos', sc);
  content.innerHTML = html;
}

/* ---------- действия ---------- */

async function userOp(id, op) {
  var confirms = {
    ban: 'Забанить пользователя? Он не сможет оставлять отзывы и решать по фото.',
    unban: 'Разбанить пользователя?',
    promote: 'Выдать этому аккаунту роль администратора?',
    demote: 'Снять роль администратора?',
    delete: 'Удалить аккаунт навсегда? Вместе с ним уйдут отзывы и фото.'
  };
  if (!confirm(confirms[op] || 'Продолжить?')) return;

  var res;
  if (op === 'ban') res = await supabase.from('profiles').update({ ban: true }).eq('id', id);
  else if (op === 'unban') res = await supabase.from('profiles').update({ ban: false }).eq('id', id);
  else if (op === 'promote') res = await supabase.from('profiles').update({ role: 'admin' }).eq('id', id);
  else if (op === 'demote') res = await supabase.from('profiles').update({ role: 'user' }).eq('id', id);
  else if (op === 'delete') res = await supabase.rpc('admin_delete_user', { target: id });

  if (res && res.error) { toast('Не получилось: ' + res.error.message, true); return; }
  toast('Готово');
  loadUsers();
}

async function reviewOp(id, op) {
  if (op === 'delete' && !confirm('Удалить отзыв навсегда?')) return;
  if (op === 'approve' && !confirm('Опубликовать отзыв?')) return;
  if (op === 'reject' && !confirm('Отклонить отзыв? Он пропадёт из списка и из ИИ-логов.')) return;

  var res;
  if (op === 'approve') {
    res = await supabase.from('reviews').update({ is_approved: true, ai_status: 'approved' }).eq('id', id);
  } else if (op === 'reject') {
    res = await supabase.from('reviews').update({ is_approved: false, ai_status: 'rejected' }).eq('id', id);
  } else if (op === 'delete') {
    res = await supabase.from('reviews').delete().eq('id', id);
  }

  if (res && res.error) { toast('Не получилось: ' + res.error.message, true); return; }
  toast('Готово');
  route();
}

async function photoOp(id, op, url) {
  if (op === 'view') {
    var row = $('answer-' + id);
    if (row) row.hidden = !row.hidden;
    return;
  }
  if (op === 'delete') {
    if (!confirm('Удалить фото и запись о нём?')) return;
    var path = storagePath(url);
    if (path) {
      var rm = await supabase.storage.from('photos').remove([path]);
      if (rm.error) toast('Файл не удалился: ' + rm.error.message, true);
    }
    var res = await supabase.from('photo_requests').delete().eq('id', id);
    if (res.error) { toast('Не получилось удалить запись: ' + res.error.message, true); return; }
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

  if (act === 'reviews-filter') {
    state.reviews.filter = el.getAttribute('data-value');
    state.reviews.page = 0;
    loadReviewTable('reviews');
    return;
  }

  if (act === 'user') { userOp(el.getAttribute('data-id'), el.getAttribute('data-op')); return; }
  if (act === 'review') { reviewOp(el.getAttribute('data-id'), el.getAttribute('data-op')); return; }
  if (act === 'photo') { photoOp(el.getAttribute('data-id'), el.getAttribute('data-op'), el.getAttribute('data-url')); }
}

var searchTimer = 0;
function onContentInput(event) {
  if (event.target.id !== 'users-search') return;
  var value = event.target.value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function () {
    state.users.search = value.trim();
    state.users.page = 0;
    state.users.focusSearch = true;
    loadUsers();
  }, 350);
}

function onContentChange(event) {
  if (event.target.id === 'users-filter') {
    state.users.filter = event.target.value;
    state.users.page = 0;
    loadUsers();
  }
}

/* ---------- роутинг и запуск ---------- */

function route() {
  var tab = (location.hash || '#overview').replace('#', '') || 'overview';
  if (['overview', 'users', 'reviews', 'ai', 'photos'].indexOf(tab) === -1) tab = 'overview';
  state.tab = tab;

  Array.prototype.forEach.call(document.querySelectorAll('.admin-nav a'), function (a) {
    a.classList.toggle('is-active', a.getAttribute('data-tab') === tab);
  });

  var titles = {
    overview: 'Обзор',
    users: 'Пользователи',
    reviews: 'Модерация отзывов',
    ai: 'ИИ-логи',
    photos: 'Фото-логи'
  };
  $('admin-title').textContent = titles[tab];

  if (tab === 'overview') renderOverview();
  else if (tab === 'users') loadUsers();
  else if (tab === 'reviews') loadReviewTable('reviews');
  else if (tab === 'ai') loadReviewTable('ai');
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
  });
}

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
    var letter = String(me.username || 'А').trim().charAt(0).toUpperCase() || 'А';
    $('admin-avatar').textContent = letter;
    $('admin-avatar').style.background = avatarColor(me.username || 'А');

    $('logout').addEventListener('click', async function () {
      await supabase.auth.signOut();
      location.replace('../index.html');
    });

    wireTheme();

    var content = $('admin-content');
    content.addEventListener('click', onContentClick);
    content.addEventListener('input', onContentInput);
    content.addEventListener('change', onContentChange);

    window.addEventListener('hashchange', route);
    route();
  } catch (err) {
    $('admin-loading').textContent = 'Не получилось подключиться к серверу: ' + err.message;
  }
})();
