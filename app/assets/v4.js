/* =========================================================
   ГДЗ НЭЛ 4.0 — клиентские фичи приложения.

   AI-репетитор, PNG-шер, выбор нескольких заданий и общий PDF,
   калькулятор на математике, подсветка кода, XP за просмотры,
   продолжение с главной и фоновое офлайн-скачивание для ГДЗ+.

   Модуль не перерисовывает роутер: он дополняет уже готовый DOM
   после каждого рендера #screen.
   ========================================================= */

import { supabase, getSession, getProfile, isPremiumActive } from '../../assets/supabase.js';

const screen = document.getElementById('screen');
const LS_XP = 'gdz-nel-xp';
const LS_STREAK = 'gdz-nel-streak';
const LS_LAST = 'gdz-nel-last-active';
const LS_VIEWS = 'gdz-nel-xp-views';

let enhanceTimer = 0;
let catalogPromise = null;
let autoOfflineStarted = false;
let calcReady = false;
let currentInfo = null;

function $(id) { return document.getElementById(id); }

function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function toast(text) {
  const el = $('toast');
  if (!el) return;
  el.textContent = text;
  el.classList.add('is-visible');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('is-visible'), 2600);
}

function routeInfo() {
  const raw = (location.hash || '#/').replace(/^#\/?/, '');
  let parts = [];
  try {
    parts = raw.split('/').filter(Boolean).map((part) => decodeURIComponent(part));
  } catch (err) {
    parts = raw.split('/').filter(Boolean);
  }
  return {
    parts,
    grade: parts[0] || '',
    subject: parts[1] || '',
    book: parts[2] || '',
    number: parts[3] || '',
    isTask: parts.length >= 4,
    isGrid: parts.length === 3,
    isHome: parts.length === 0
  };
}

function storeGet(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (err) { return fallback; }
}

function storeSet(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (err) { /* private mode */ }
}

function todayKey() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function localXp() {
  return Math.max(0, Number(storeGet(LS_XP, 0)) || 0);
}

function setLocalXp(xp, streak) {
  const value = Math.max(0, Number(xp) || 0);
  storeSet(LS_XP, value);
  if (typeof streak === 'number') storeSet(LS_STREAK, Math.max(0, streak));
}

function addLocalXp(amount, streak) {
  setLocalXp(localXp() + Math.max(0, amount), streak);
}

function touchLocalStreak() {
  const today = todayKey();
  const last = storeGet(LS_LAST, '');
  if (last === today) {
    addLocalXp(0);
    return;
  }
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const yKey = yesterday.getFullYear() + '-' + String(yesterday.getMonth() + 1).padStart(2, '0') + '-' + String(yesterday.getDate()).padStart(2, '0');
  const streak = last === yKey ? (Number(storeGet(LS_STREAK, 0)) || 0) + 1 : 1;
  storeSet(LS_LAST, today);
  addLocalXp(10, streak);
}

/* =========================================================
   маршрутизация и наблюдение за DOM
   ========================================================= */

function scheduleEnhance() {
  clearTimeout(enhanceTimer);
  enhanceTimer = setTimeout(enhance, 60);
}

function enhance() {
  if (!screen) return;
  currentInfo = routeInfo();
  toggleCalculator(['math', 'algebra', 'geometry'].includes(currentInfo.subject));

  if (currentInfo.isTask) enhanceTask(currentInfo);
  else if (currentInfo.isGrid) enhanceGrid(currentInfo);
  else if (currentInfo.isHome) enhanceHome();

  scheduleAutoOffline();
}

/* =========================================================
   XP: локальный кэш + сервер
   ========================================================= */

async function awardView(info) {
  const ref = info.book + ':' + info.number;
  const seen = storeGet(LS_VIEWS, {});
  const key = todayKey() + ':' + ref;
  if (seen[key]) return;
  seen[key] = 1;
  // чистим старые ключи, чтобы localStorage не рос бесконечно
  const keys = Object.keys(seen).filter((k) => k.indexOf(todayKey() + ':') === 0);
  const trimmed = {};
  keys.forEach((k) => { trimmed[k] = 1; });
  storeSet(LS_VIEWS, trimmed);

  try {
    const session = await getSession();
    if (!session) {
      addLocalXp(5);
      touchLocalStreak();
      return;
    }
    const res = await supabase.rpc('award_xp', { p_kind: 'view', p_ref: ref });
    if (res.error) addLocalXp(5);
    else if (res.data && res.data[0]) setLocalXp(res.data[0].xp, res.data[0].streak_days);
    const streak = await supabase.rpc('touch_streak');
    if (!streak.error && streak.data && streak.data[0]) {
      setLocalXp(streak.data[0].xp, streak.data[0].streak_days);
      storeSet(LS_LAST, streak.data[0].last_active_date || todayKey());
    }
  } catch (err) {
    addLocalXp(5);
    touchLocalStreak();
  }
}

async function awardShare(info) {
  const ref = info.book + ':' + info.number;
  try {
    const session = await getSession();
    if (session) await supabase.rpc('award_xp', { p_kind: 'share', p_ref: ref });
    else addLocalXp(5);
  } catch (err) {
    addLocalXp(5);
  }
}

/* =========================================================
   задание: AI-репетитор, код, PNG
   ========================================================= */

function taskContext(info) {
  const conditionEl = document.querySelector('.task-block--cond .task-text');
  const answerEl = document.querySelector('.task-block--answer .answer');
  const steps = Array.from(document.querySelectorAll('#solution-block .step-line'))
    .map((el) => el.textContent.trim())
    .filter(Boolean);
  return {
    condition: conditionEl ? conditionEl.textContent.trim() : '',
    solution: steps.join('\n'),
    answer: answerEl ? answerEl.textContent.trim() : '',
    subject: info.subject
  };
}

function aiOutputHtml(text) {
  const safe = esc(text)
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>');
  return '<p>' + safe + '</p>';
}

async function callAi(action, question) {
  const output = $('ai-output');
  if (!output) return;
  const info = currentInfo;
  const context = taskContext(info);
  output.hidden = false;
  output.className = 'ai-output is-loading';
  output.innerHTML = '<p>Думаю… Это может занять несколько секунд.</p>';

  const session = await getSession();
  if (!session) {
    output.className = 'ai-output is-error';
    output.innerHTML = '<p>Чтобы пользоваться ИИ, <a href="../auth.html?next=' +
      encodeURIComponent('app/index.html' + location.hash) + '">войди в аккаунт</a>.</p>';
    return;
  }

  try {
    const { data, error } = await supabase.functions.invoke('ai-tutor', {
      body: { action, task: context, question }
    });

    if (error) {
      let message = 'ИИ временно недоступен. Попробуй ещё раз.';
      try {
        if (error.context && error.context.json) {
          const body = await error.context.json();
          if (body && body.error) message = body.error;
        }
      } catch (err) { /* ignore */ }
      throw new Error(message);
    }
    if (!data || data.error) throw new Error((data && data.error) || 'пустой ответ ИИ');

    if (action === 'similar') {
      const tasks = Array.isArray(data.tasks) ? data.tasks : [];
      if (!tasks.length) {
        output.className = 'ai-output';
        output.innerHTML = aiOutputHtml(data.raw || 'Не получилось составить похожие задачи.');
        return;
      }
      output.className = 'ai-output';
      output.innerHTML = '<p class="ai-lead">Вот три похожие задачи. Сначала реши сам, потом проверь ответ.</p>' +
        tasks.map((task, i) => '<article class="similar-card">' +
          '<p class="similar-num">Задача ' + (i + 1) + '</p>' +
          '<p>' + esc(task.condition) + '</p>' +
          (task.hint ? '<p class="similar-hint">Подсказка: ' + esc(task.hint) + '</p>' : '') +
          '<details><summary>Показать ответ</summary><p><b>' + esc(task.answer || '—') + '</b></p></details>' +
          '</article>').join('');
      return;
    }

    output.className = 'ai-output';
    output.innerHTML = aiOutputHtml(data.answer || 'ИИ не вернул текст.');
  } catch (err) {
    output.className = 'ai-output is-error';
    output.innerHTML = aiOutputHtml(err.message || 'Ошибка ИИ');
  }
}

function enhanceTask(info) {
  const block = $('solution-block');
  if (!block) return;

  awardView(info);

  // подсветка кода в информатике
  if (info.subject === 'informatics') addCodeBlock(block);

  if ($('ai-tools')) return;

  const section = document.createElement('section');
  section.className = 'ai-tools no-print';
  section.id = 'ai-tools';
  section.innerHTML =
    '<div class="ai-head">' +
    '<span class="ai-badge">ИИ</span>' +
    '<div><h2>Не понял решение?</h2><p>Репетитор объяснит проще или придумает похожие задачи.</p></div>' +
    '</div>' +
    '<div class="ai-actions">' +
    '<button class="btn btn-primary btn-sm" type="button" id="ai-explain">' +
    '<span class="icon i-sparkles" aria-hidden="true"></span><span>Объясни проще</span></button>' +
    '<button class="btn btn-outline btn-sm" type="button" id="ai-similar">' +
    '<span class="icon i-refresh" aria-hidden="true"></span><span>Решить похожую</span></button>' +
    '</div>' +
    '<form class="ai-ask" id="ai-ask-form">' +
    '<label for="ai-question">Спроси про конкретный шаг</label>' +
    '<div class="ai-ask-row">' +
    '<input id="ai-question" type="text" maxlength="1200" placeholder="Почему здесь делим на 2?" autocomplete="off">' +
    '<button class="btn btn-outline btn-sm" type="submit" id="ai-ask-btn">Спросить</button>' +
    '</div></form>' +
    '<div class="ai-output" id="ai-output" role="status" aria-live="polite" hidden></div>';

  block.insertAdjacentElement('afterend', section);
  $('ai-explain').addEventListener('click', () => callAi('explain', ''));
  $('ai-similar').addEventListener('click', () => callAi('similar', ''));
  $('ai-ask-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const question = $('ai-question').value.trim();
    if (!question) {
      $('ai-question').focus();
      return;
    }
    callAi('ask', question);
  });
}

/* ---------- подсветка кода ---------- */

let hljsPromise = null;

function loadHighlight() {
  if (window.hljs) return Promise.resolve(window.hljs);
  if (hljsPromise) return hljsPromise;
  hljsPromise = new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.11.1/build/highlight.min.js';
    script.onload = () => resolve(window.hljs || null);
    script.onerror = () => resolve(null);
    document.head.appendChild(script);
  });
  return hljsPromise;
}

function looksLikeCode(text) {
  const value = String(text || '');
  const score = [
    /(^|\n)\s*(def|class|import|from)\s+\w+/m,
    /\b(print|len|range|input)\s*\(/,
    /\b(for|while)\s+.+:/,
    /\b(if|elif|else)\s*.*:/,
    /[{};]/,
    /\b(function|const|let|var|console\.log)\b/,
    /#include|public static|System\.out/,
    /[=<>]=|[-+*/]=/
  ].filter((re) => re.test(value)).length;
  return score >= 2;
}

async function addCodeBlock(block) {
  if (!block || block.querySelector('[data-v4-code]')) return;
  const steps = Array.from(block.querySelectorAll('.step-line'))
    .map((el) => el.textContent.trim())
    .filter(Boolean);
  const codeText = steps.join('\n');
  if (!looksLikeCode(codeText)) return;

  const wrap = document.createElement('div');
  wrap.className = 'code-solution';
  wrap.setAttribute('data-v4-code', '1');
  wrap.innerHTML = '<div class="code-head"><span class="icon i-code" aria-hidden="true"></span>Код решения</div>' +
    '<pre><code class="language-python">' + esc(codeText) + '</code></pre>';
  const intro = block.querySelector('.steps-list');
  if (intro && intro.nextSibling) block.insertBefore(wrap, intro.nextSibling);
  else block.appendChild(wrap);

  const code = wrap.querySelector('code');
  const hljs = await loadHighlight();
  if (hljs && code) {
    try { hljs.highlightElement(code); } catch (err) { /* остаётся обычный текст */ }
  }
}

/* ---------- PNG для соцсетей ---------- */

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function wrapCanvasText(ctx, text, maxWidth, maxLines) {
  const paragraphs = String(text || '').replace(/\s+/g, ' ').trim().split(/\n+/);
  const lines = [];
  paragraphs.forEach((paragraph) => {
    const words = paragraph.split(' ');
    let line = '';
    words.forEach((word) => {
      const test = line ? line + ' ' + word : word;
      if (ctx.measureText(test).width > maxWidth && line) {
        lines.push(line);
        line = word;
      } else {
        line = test;
      }
    });
    if (line) lines.push(line);
  });
  if (lines.length <= maxLines) return lines;
  const clipped = lines.slice(0, maxLines);
  clipped[maxLines - 1] = clipped[maxLines - 1].replace(/\s+\S*$/, '') + '…';
  return clipped;
}

async function shareTask() {
  const info = currentInfo || routeInfo();
  if (!info.isTask) return;
  const context = taskContext(info);
  if (!context.condition && !context.answer) {
    toast('На этой странице нечего сохранять');
    return;
  }

  try { await document.fonts.ready; } catch (err) { /* ignore */ }

  const canvas = document.createElement('canvas');
  canvas.width = 1080;
  canvas.height = 1350;
  const ctx = canvas.getContext('2d');

  const grad = ctx.createLinearGradient(0, 0, 1080, 1350);
  grad.addColorStop(0, '#0E6E75');
  grad.addColorStop(0.55, '#128080');
  grad.addColorStop(1, '#005CA8');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 1080, 1350);

  ctx.globalAlpha = 0.16;
  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.arc(930, 170, 240, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(90, 1190, 210, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;

  ctx.fillStyle = '#ffffff';
  roundRect(ctx, 64, 64, 952, 1222, 42);
  ctx.fill();

  // логотип
  try {
    const logo = new Image();
    logo.src = new URL('../../assets/img/logo-160.png', import.meta.url).href;
    await new Promise((resolve, reject) => {
      logo.onload = resolve;
      logo.onerror = reject;
    });
    ctx.save();
    ctx.beginPath();
    ctx.arc(142, 160, 46, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(logo, 96, 114, 92, 92);
    ctx.restore();
  } catch (err) { /* без логотипа */ }

  ctx.fillStyle = '#0F172A';
  ctx.font = '600 40px Unbounded, system-ui, sans-serif';
  ctx.fillText('ГДЗ НЭЛ', 208, 158);
  ctx.fillStyle = '#607080';
  ctx.font = '500 24px system-ui, sans-serif';
  ctx.fillText('задание ' + (info.number || '') + ' · ' + (info.subject || ''), 208, 194);

  ctx.strokeStyle = '#DCE7EA';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(104, 246);
  ctx.lineTo(976, 246);
  ctx.stroke();

  ctx.fillStyle = '#128080';
  ctx.font = '700 26px Unbounded, system-ui, sans-serif';
  ctx.fillText('УСЛОВИЕ', 104, 310);

  ctx.fillStyle = '#16202C';
  ctx.font = '500 35px system-ui, sans-serif';
  let lines = wrapCanvasText(ctx, context.condition, 872, 9);
  let y = 364;
  lines.forEach((line) => {
    ctx.fillText(line, 104, y);
    y += 48;
  });

  if (context.answer) {
    y = Math.max(y + 26, 760);
    ctx.fillStyle = '#0B6B4F';
    ctx.font = '700 26px Unbounded, system-ui, sans-serif';
    ctx.fillText('ОТВЕТ', 104, y);
    y += 56;
    ctx.fillStyle = '#16202C';
    ctx.font = '600 38px system-ui, sans-serif';
    const answerLines = wrapCanvasText(ctx, context.answer, 872, 7);
    answerLines.forEach((line) => {
      ctx.fillText(line, 104, y);
      y += 52;
    });
  }

  ctx.fillStyle = '#5D707A';
  ctx.font = '500 24px system-ui, sans-serif';
  ctx.fillText('gdz-nel.pages.dev', 104, 1232);
  ctx.textAlign = 'right';
  ctx.fillText('решения и ответы 1–11 класс', 976, 1232);
  ctx.textAlign = 'left';

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png', 0.94));
  if (!blob) throw new Error('не удалось собрать PNG');
  const file = new File([blob], 'gdz-nel-' + String(info.number || 'task').replace(/[^\w.-]+/g, '-') + '.png', { type: 'image/png' });

  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({
        files: [file],
        title: 'ГДЗ НЭЛ — задание ' + info.number,
        text: context.condition.slice(0, 180)
      });
      awardShare(info);
      return;
    } catch (err) {
      if (err && err.name === 'AbortError') return;
    }
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = file.name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  toast('PNG сохранился — можно отправить в чат');
  awardShare(info);
}

/* =========================================================
   сетка: выбор нескольких заданий и общий PDF
   ========================================================= */

function selectedNumbers() {
  return Array.from(document.querySelectorAll('.task-pick:checked')).map((el) => el.value);
}

function updateBulkButton() {
  const btn = $('bulk-pdf-btn');
  if (!btn) return;
  const count = selectedNumbers().length;
  btn.disabled = count === 0;
  const label = btn.querySelector('span:last-child');
  if (label) label.textContent = count ? 'PDF выбранных: ' + count : 'PDF выбранных';
}

function enhanceGrid(info) {
  if ($('bulk-pdf-btn')) return;
  const toolbar = document.querySelector('.task-toolbar');
  if (!toolbar) return;

  const actions = document.createElement('span');
  actions.className = 'task-bulk no-print';
  actions.innerHTML = '<button class="btn btn-outline btn-sm" type="button" id="bulk-pdf-btn" disabled>' +
    '<span class="icon i-download" aria-hidden="true"></span><span>PDF выбранных</span></button>';
  toolbar.appendChild(actions);

  Array.from(document.querySelectorAll('.task-grid .task-cell')).forEach((cell) => {
    if (cell.parentElement && cell.parentElement.classList.contains('task-pick-wrap')) return;
    const wrap = document.createElement('div');
    wrap.className = 'task-pick-wrap';
    cell.parentNode.insertBefore(wrap, cell);
    wrap.appendChild(cell);
    const pick = document.createElement('input');
    pick.type = 'checkbox';
    pick.className = 'task-pick';
    pick.value = cell.getAttribute('data-number') || '';
    pick.setAttribute('aria-label', 'Выбрать задание ' + pick.value);
    pick.addEventListener('change', updateBulkButton);
    wrap.appendChild(pick);
  });

  $('bulk-pdf-btn').addEventListener('click', () => printSelected(info));

}

function taskHtml(task) {
  const condition = esc(task.condition || '');
  const solution = esc(task.solution || '').replace(/\n/g, '<br>');
  const answer = esc(task.answer || '').replace(/\n/g, '<br>');
  const images = Array.isArray(task.images) ? task.images : [];
  return '<article class="bulk-item">' +
    '<h2>Задание ' + esc(task.number) + '</h2>' +
    (condition ? '<p class="bulk-label">Условие</p><p>' + condition + '</p>' : '') +
    (solution ? '<p class="bulk-label">Решение</p><p>' + solution + '</p>' : '') +
    (answer ? '<p class="bulk-label">Ответ</p><p class="bulk-answer">' + answer + '</p>' : '') +
    (images.length ? '<div class="bulk-images">' + images.map((src) =>
      '<img src="' + esc(src) + '" alt="Решение" loading="lazy">').join('') + '</div>' : '') +
    '</article>';
}

async function findBook(info) {
  if (!catalogPromise) catalogPromise = fetch('data/catalog.json').then((res) => res.json());
  const catalog = await catalogPromise;
  const grade = (catalog.grades || []).find((g) => String(g.id) === String(info.grade));
  if (!grade) return null;
  const subject = (grade.subjects || []).find((s) => String(s.id) === String(info.subject));
  if (!subject) return null;
  const book = (subject.textbooks || []).find((b) => String(b.id) === String(info.book));
  if (!book) return null;
  return { grade, subject, book };
}

async function printSelected(info) {
  const numbers = selectedNumbers();
  if (!numbers.length) return;
  const btn = $('bulk-pdf-btn');
  if (btn) btn.disabled = true;

  try {
    const found = await findBook(info);
    if (!found) throw new Error('не нашёл учебник');
    const res = await fetch('data/' + found.book.file);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const doc = await res.json();
    const wanted = new Set(numbers);
    const tasks = (doc.tasks || []).filter((task) => wanted.has(String(task.number)));

    const profile = await getProfile().catch(() => null);
    const premium = isPremiumActive(profile);
    const watermark = premium ? '' :
      '<span class="bulk-watermark" aria-hidden="true">ГДЗ НЭЛ — бесплатная версия</span>';

    let layer = $('bulk-print-layer');
    if (!layer) {
      layer = document.createElement('div');
      layer.id = 'bulk-print-layer';
      layer.className = 'bulk-print-layer';
      document.body.appendChild(layer);
    }
    layer.innerHTML = watermark +
      '<header class="bulk-head">' +
      '<p class="bulk-brand">ГДЗ НЭЛ</p>' +
      '<h1>' + esc(found.book.title) + ' · задание ' + numbers.join(', ') + '</h1>' +
      '<p>' + esc(found.subject.title) + ', ' + esc(found.grade.title) + '. Выбрано заданий: ' + tasks.length + '.</p>' +
      '</header>' + tasks.map(taskHtml).join('');

    document.body.classList.add('is-bulk-print');
    window.print();
  } catch (err) {
    toast('Не получилось собрать PDF: ' + (err.message || 'ошибка'));
  } finally {
    if (btn) btn.disabled = false;
    updateBulkButton();
  }
}

window.addEventListener('afterprint', () => {
  document.body.classList.remove('is-bulk-print');
  const layer = $('bulk-print-layer');
  if (layer) layer.innerHTML = '';
});

/* =========================================================
   главная приложения: продолжить
   ========================================================= */

function enhanceHome() {
  if ($('app-continue')) return;
  const history = storeGet('gdz-nel-history', []);
  if (!Array.isArray(history) || !history.length) return;
  const entry = history[0];
  if (!entry || !entry.book) return;
  const grid = document.querySelector('#screen .subject-grid');
  if (!grid) return;

  const href = '#/' + [entry.grade || '6', entry.subject, entry.book, entry.number]
    .map(encodeURIComponent).join('/');
  const card = document.createElement('a');
  card.id = 'app-continue';
  card.className = 'app-continue';
  card.href = href;
  card.innerHTML = '<span class="app-continue-icon"><span class="icon i-clock" aria-hidden="true"></span></span>' +
    '<span class="app-continue-body"><span class="app-continue-kicker">Продолжить с места остановки</span>' +
    '<b>' + esc(entry.title || ('Задание ' + entry.number)) + '</b>' +
    (entry.snippet ? '<small>' + esc(entry.snippet) + '</small>' : '') + '</span>' +
    '<span class="btn btn-primary btn-sm">Открыть<span class="icon i-arrow-right" aria-hidden="true"></span></span>';
  grid.parentNode.insertBefore(card, grid);
}

/* =========================================================
   калькулятор
   ========================================================= */

function evaluateMath(raw) {
  const expr = String(raw || '')
    .replace(/,/g, '.')
    .replace(/[×х]/g, '*')
    .replace(/÷/g, '/')
    .replace(/−/g, '-')
    .replace(/\s+/g, '');
  if (!expr) return '';
  if (!/^[0-9+\-*/^%().]+$/.test(expr)) throw new Error('только числа и + − × ÷ ^ %');

  let pos = 0;
  function peek() { return expr[pos]; }
  function parseExpression() {
    let value = parseTerm();
    while (peek() === '+' || peek() === '-') {
      const op = expr[pos++];
      const right = parseTerm();
      value = op === '+' ? value + right : value - right;
    }
    return value;
  }
  function parseTerm() {
    let value = parseUnary();
    while (peek() === '*' || peek() === '/' || peek() === '%') {
      const op = expr[pos++];
      const right = parseUnary();
      if ((op === '/' || op === '%') && right === 0) throw new Error('деление на ноль');
      value = op === '*' ? value * right : op === '/' ? value / right : value % right;
    }
    return value;
  }
  function parseUnary() {
    if (peek() === '+') { pos++; return parseUnary(); }
    if (peek() === '-') { pos++; return -parseUnary(); }
    return parsePower();
  }
  function parsePower() {
    const base = parsePrimary();
    if (peek() === '^') {
      pos++;
      return Math.pow(base, parseUnary());
    }
    return base;
  }
  function parsePrimary() {
    if (peek() === '(') {
      pos++;
      const value = parseExpression();
      if (peek() !== ')') throw new Error('не хватает скобки');
      pos++;
      return value;
    }
    const start = pos;
    while (/[0-9.]/.test(peek() || '')) pos++;
    if (start === pos) throw new Error('непонятное выражение');
    const value = Number(expr.slice(start, pos));
    if (!Number.isFinite(value)) throw new Error('плохое число');
    return value;
  }

  const result = parseExpression();
  if (pos !== expr.length) throw new Error('лишние символы');
  if (!Number.isFinite(result)) throw new Error('слишком большое число');
  return String(Math.round(result * 1e10) / 1e10);
}

function buildCalculator() {
  if (calcReady) return;
  calcReady = true;
  const wrap = document.createElement('div');
  wrap.className = 'calc-wrap no-print';
  wrap.innerHTML =
    '<button class="calc-toggle" id="calc-toggle" type="button" aria-label="Открыть калькулятор" aria-expanded="false">' +
    '<span class="icon i-math" aria-hidden="true"></span></button>' +
    '<div class="calc-panel" id="calc-panel" hidden>' +
    '<div class="calc-head"><b>Калькулятор</b><button type="button" id="calc-close" aria-label="Закрыть">×</button></div>' +
    '<input class="calc-input" id="calc-input" type="text" inputmode="decimal" autocomplete="off" aria-label="Выражение" placeholder="2+2×2">' +
    '<div class="calc-result" id="calc-result" aria-live="polite">0</div>' +
    '<div class="calc-keys">' +
    ['C', '(', ')', '÷', '7', '8', '9', '×', '4', '5', '6', '−', '1', '2', '3', '+', '0', '.', '%', '='].map((key) =>
      '<button type="button" data-key="' + key + '" class="' +
      (key === '=' ? 'is-eq' : (['C', '(', ')', '÷', '×', '−', '+', '%'].includes(key) ? 'is-op' : '')) + '">' + key + '</button>'
    ).join('') +
    '<button type="button" data-key="back" class="is-wide">⌫ Стереть</button>' +
    '</div></div>';
  document.body.appendChild(wrap);

  const toggle = $('calc-toggle');
  const panel = $('calc-panel');
  const input = $('calc-input');
  const result = $('calc-result');

  function open() {
    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    setTimeout(() => input.focus(), 30);
  }
  function close() {
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
  }
  function calculate() {
    try {
      const value = evaluateMath(input.value);
      result.textContent = value === '' ? '0' : value;
      result.classList.remove('is-error');
    } catch (err) {
      result.textContent = err.message;
      result.classList.add('is-error');
    }
  }

  toggle.addEventListener('click', () => panel.hidden ? open() : close());
  $('calc-close').addEventListener('click', close);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') { event.preventDefault(); calculate(); }
    if (event.key === 'Escape') close();
  });
  panel.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-key]');
    if (!btn) return;
    const key = btn.getAttribute('data-key');
    if (key === 'C') {
      input.value = '';
      result.textContent = '0';
      result.classList.remove('is-error');
    } else if (key === '=') {
      calculate();
    } else if (key === 'back') {
      input.value = input.value.slice(0, -1);
    } else {
      input.value += key;
    }
    input.focus();
  });
}

function toggleCalculator(show) {
  if (show) buildCalculator();
  const wrap = document.querySelector('.calc-wrap');
  if (!wrap) return;
  wrap.hidden = !show;
  if (!show) {
    const panel = $('calc-panel');
    if (panel && !panel.hidden) panel.hidden = true;
  }
}

/* =========================================================
   PRO: ставим последние 5 учебников в Background Sync
   ========================================================= */

async function scheduleAutoOffline() {
  if (autoOfflineStarted) return;
  autoOfflineStarted = true;

  try {
    if (!window.GdzOffline || !window.GdzOffline.queueAutoBooks) return;
    const session = await getSession();
    if (!session) return;
    const profile = await getProfile();
    if (!isPremiumActive(profile)) return;

    const history = storeGet('gdz-nel-history', []);
    if (!Array.isArray(history) || !history.length) return;

    const seen = new Set();
    const recent = [];
    for (const entry of history) {
      if (!entry || !entry.book) continue;
      const key = String(entry.book);
      if (seen.has(key)) continue;
      seen.add(key);
      recent.push(entry);
      if (recent.length >= 5) break;
    }

    if (!catalogPromise) catalogPromise = fetch('data/catalog.json').then((res) => res.json());
    const catalog = await catalogPromise;
    const metas = [];
    recent.forEach((entry) => {
      const grade = (catalog.grades || []).find((g) => String(g.id) === String(entry.grade || '6'));
      const subject = grade && (grade.subjects || []).find((s) => String(s.id) === String(entry.subject));
      const book = subject && (subject.textbooks || []).find((b) => String(b.id) === String(entry.book));
      if (!book) return;
      metas.push({
        file: book.file,
        id: book.id,
        title: book.title,
        author: book.author || '',
        year: book.year || '',
        grade: grade.id,
        gradeTitle: grade.title,
        subject: subject.id,
        subjectTitle: subject.title
      });
    });

    const missing = [];
    for (const meta of metas) {
      const offline = await window.GdzOffline.isBookOffline(meta.file);
      if (!offline) missing.push(meta);
    }
    if (!missing.length) return;

    await window.GdzOffline.queueAutoBooks(missing);

    if ('serviceWorker' in navigator && 'SyncManager' in window) {
      const reg = await navigator.serviceWorker.ready;
      if (reg.sync && reg.sync.register) {
        await reg.sync.register('gdz-auto-offline');
        return;
      }
    }

    // Safari/старые браузеры: качаем в фоне, пока страница открыта.
    const connection = navigator.connection || {};
    if (connection.saveData) return;
    const done = storeGet('gdz-nel-auto-offline-day', '');
    if (done === todayKey()) return;
    storeSet('gdz-nel-auto-offline-day', todayKey());
    const run = async () => {
      for (const meta of missing.slice(0, 5)) {
        try {
          await window.GdzOffline.downloadBook(meta);
          await window.GdzOffline.removeAutoBook(meta.file);
        } catch (err) { /* попробуем в следующий раз */ }
      }
    };
    if ('requestIdleCallback' in window) requestIdleCallback(run, { timeout: 15000 });
    else setTimeout(run, 4000);
  } catch (err) {
    // фоновое скачивание не должно ломать страницу
  }
}

/* =========================================================
   запуск
   ========================================================= */

window.GdzV4 = { shareTask, evaluateMath };

if (screen) {
  new MutationObserver(scheduleEnhance).observe(screen, { childList: true, subtree: true });
}
window.addEventListener('hashchange', scheduleEnhance);
window.addEventListener('load', scheduleEnhance);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') scheduleEnhance();
});
scheduleEnhance();
