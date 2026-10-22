/* ГДЗ НЭЛ 4.0 — прогресс, серия, рефералка и промокод в профиле. */
import { supabase, getSession } from './supabase.js';

const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function status(el, text, ok) {
  if (!el) return;
  el.className = 'form-status ' + (ok ? 'is-ok' : 'is-err');
  el.textContent = text;
}

function paintProgress(profile, localXp) {
  const xp = Math.max(0, Number(profile && profile.xp) || Number(localXp) || 0);
  const streak = Math.max(0, Number(profile && profile.streak_days) || 0);
  const level = Math.floor(xp / 100) + 1;
  const inside = xp % 100;
  const left = 100 - inside;
  $('progress-section').hidden = false;
  $('xp-level').textContent = String(level);
  $('xp-fill').style.width = inside + '%';
  $('xp-bar').setAttribute('aria-valuenow', String(inside));
  $('xp-text').textContent = xp + ' XP · до уровня ' + (level + 1) + ' осталось ' + left + ' XP';
  $('streak-days').textContent = String(streak);
}

function localXp() {
  try { return Number(JSON.parse(localStorage.getItem('gdz-nel-xp') || '0')) || 0; }
  catch (err) { return 0; }
}

async function loadReferrals(profile) {
  const code = String((profile && profile.referral_code) || '').toUpperCase();
  const section = $('referral-section');
  if (!code) { section.hidden = false; $('referral-status').textContent = 'Код ещё создаётся — обнови страницу через минуту.'; return; }
  section.hidden = false;
  const link = location.origin + new URL('auth.html', location.href).pathname + '?ref=' + encodeURIComponent(code);
  $('referral-link').value = link;
  const res = await supabase.from('referrals').select('id, reward_days', { count: 'exact' });
  if (!res.error) {
    const count = res.count || (res.data || []).length;
    const days = (res.data || []).reduce((sum, row) => sum + (Number(row.reward_days) || 0), 0);
    $('referral-status').textContent = 'Приглашено: ' + count + ' · бонусных дней ГДЗ+: ' + days;
  }
}

async function init() {
  const session = await getSession();
  if (!session) return;

  let profile = null;
  const res = await supabase.from('profiles')
    .select('xp, streak_days, referral_code, is_premium, premium_until')
    .eq('id', session.user.id).single();
  if (!res.error) profile = res.data;

  paintProgress(profile, localXp());
  loadReferrals(profile);

  // серия и дневной XP начисляются сервером, повторный вызов безопасен
  const streak = await supabase.rpc('touch_streak');
  if (!streak.error && streak.data && streak.data[0]) {
    profile = Object.assign({}, profile, streak.data[0]);
    paintProgress(profile, localXp());
  }

  $('referral-copy').addEventListener('click', async () => {
    const input = $('referral-link');
    try {
      await navigator.clipboard.writeText(input.value);
      status($('referral-note'), 'Ссылка скопирована — отправь другу.', true);
    } catch (err) {
      input.select();
      document.execCommand('copy');
      status($('referral-note'), 'Ссылка скопирована.', true);
    }
  });

  $('promo-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const code = $('promo-input').value.trim().toUpperCase();
    const btn = $('promo-submit');
    if (!code) { status($('promo-status'), 'Введи промокод.', false); return; }
    btn.disabled = true;
    const out = await supabase.rpc('redeem_promo', { p_code: code });
    btn.disabled = false;
    if (out.error) {
      status($('promo-status'), out.error.message || 'Промокод не сработал.', false);
      return;
    }
    const row = Array.isArray(out.data) ? out.data[0] : out.data;
    const until = row && row.premium_until ? new Date(row.premium_until).toLocaleDateString('ru-RU') : '';
    status($('promo-status'), 'Готово: +' + ((row && row.days) || 0) + ' дней ГДЗ+' + (until ? ' до ' + until : '') + '.', true);
    $('promo-input').value = '';
    const premiumText = $('premium-status-text');
    if (premiumText && until) premiumText.textContent = 'ГДЗ+ активен до ' + until + '.';
  });
}

init().catch(() => { /* профиль продолжает работать без блока прогресса */ });
