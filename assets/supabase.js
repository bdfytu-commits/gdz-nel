/* =========================================================
   ГДЗ НЭЛ — подключение к Supabase (вход, профиль, отзывы,
   «решить по фото»).

   В этом файле только публикуемый ключ (publishable). Он и
   предназначен для клиентского кода: доступ к данным ограничивают
   RLS-политики на стороне базы. Секретный служебный ключ в браузер
   не попадает никогда.

   Модуль подключается как <script type="module">. Если он не
   загрузился (офлайн, CDN недоступен), страницы продолжают
   работать: в шапке остаётся статичная кнопка «Войти», а блок
   отзывов показывает заглушку.
   ========================================================= */

import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';

export const SUPABASE_URL = 'https://qncqeoklwblztbnoktwk.supabase.co';
export const SUPABASE_KEY = 'sb_publishable_uyBIZ2gNPuDqxre3ea989w_WbctezF4';

export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

/* ---------- утилиты ---------- */

export function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// цвет аватара по нику: стабильный и достаточно тёмный для белых букв
export function avatarColor(text) {
  var palette = ['#1AA3A3', '#0070C0', '#16A085', '#8E44AD', '#B35C00', '#C2185B', '#3F51B5', '#2E7D32'];
  var s = String(text || '');
  var h = 0;
  for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 9973;
  return palette[h % palette.length];
}

/* ---------- ачивки ---------- */

export const BADGES = {
  welcome: { title: 'Добро пожаловать', desc: 'Аккаунт создан — начало положено' },
  review1: { title: 'Первый отзыв', desc: 'Оставлен первый отзыв к заданию' },
  tasks10: { title: 'Десять задач', desc: 'Просмотрено 10 разных заданий' },
  tasks100: { title: 'Сто задач', desc: 'Просмотрено 100 разных заданий' }
};

var BADGE_MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

export function badgeTitle(badge) {
  if (BADGES[badge]) return BADGES[badge].title;
  var daily = /^daily-(\d{4})-(\d{2})-(\d{2})$/.exec(String(badge));
  if (daily) return 'Заходил ' + Number(daily[3]) + ' ' + BADGE_MONTHS[Number(daily[2]) - 1];
  return String(badge);
}

export function badgeDesc(badge) {
  if (BADGES[badge]) return BADGES[badge].desc;
  if (/^daily-/.test(String(badge))) return 'Открыто хотя бы одно задание в этот день';
  return '';
}

/* ---------- сессия и профиль ---------- */

export async function getSession() {
  var res = await supabase.auth.getSession();
  return (res.data && res.data.session) || null;
}

/* «ГДЗ+» активна: флаг стоит и срок не истёк */
export function isPremiumActive(profile) {
  return !!(profile && profile.is_premium && profile.premium_until &&
    new Date(profile.premium_until) > new Date());
}

export async function getProfile() {
  var session = await getSession();
  if (!session) return null;
  var res = await supabase.from('profiles').select('*').eq('id', session.user.id).single();
  return res.data || null;
}

/* Если пользователь не вошёл — уводим на страницу входа.
   options: { authHref, next } */
export async function requireSession(options) {
  var opts = options || {};
  var session = await getSession();
  if (session) return session;
  var href = opts.authHref || 'auth.html';
  var next = opts.next;
  location.replace(href + (next ? '?next=' + encodeURIComponent(next) : ''));
  return null;
}

/* ---------- «Войти» / аватар в шапке ---------- */

/* options: { authHref, profileHref }
   В разметке страницы слот: <span class="auth-slot" data-auth-slot>…</span>
   Внутри — статичная кнопка «Войти», она работает и без модуля. */
export function initHeaderAuth(options) {
  var opts = options || {};
  var authHref = opts.authHref || 'auth.html';
  var profileHref = opts.profileHref || 'profile.html';
  var slot = document.querySelector('[data-auth-slot]');
  if (!slot) return;

  var iconVariant = opts.variant === 'icon';

  function renderLoggedOut() {
    if (iconVariant) {
      slot.innerHTML = '<a class="icon-btn" href="' + authHref + '" aria-label="Войти">' +
        '<span class="icon i-user" aria-hidden="true"></span></a>';
      return;
    }
    slot.innerHTML = '<a class="btn btn-outline btn-sm auth-btn" href="' + authHref + '">' +
      '<span class="icon i-user" aria-hidden="true"></span>' +
      '<span class="btn-label">Войти</span></a>';
  }

  function renderLoggedIn(profile, user) {
    var name = (profile && profile.username) ||
      (user && user.email ? String(user.email).split('@')[0] : 'Профиль');
    var letter = String(name).trim().charAt(0).toUpperCase() || 'П';
    var avatar = (profile && profile.avatar_url)
      ? '<img class="avatar" src="' + escapeHtml(profile.avatar_url) + '" alt="" loading="lazy">'
      : '<span class="avatar" style="background:' + avatarColor(name) + '" aria-hidden="true">' +
        escapeHtml(letter) + '</span>';
    slot.innerHTML = '<a class="auth-chip" href="' + profileHref + '" title="Профиль: ' + escapeHtml(name) + '">' +
      avatar +
      (iconVariant ? '' : '<span class="auth-chip-name">' + escapeHtml(name) + '</span>') + '</a>';
  }

  async function refresh(session) {
    if (!session) { renderLoggedOut(); return; }
    try {
      var res = await supabase.from('profiles').select('username, avatar_url').eq('id', session.user.id).single();
      renderLoggedIn(res.data, session.user);
    } catch (err) {
      renderLoggedIn(null, session.user);
    }
  }

  getSession().then(refresh).catch(renderLoggedOut);

  supabase.auth.onAuthStateChange(function (event, session) {
    if (event === 'SIGNED_OUT') { renderLoggedOut(); return; }
    refresh(session);
  });
}
