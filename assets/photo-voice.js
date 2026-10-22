/* ГДЗ НЭЛ 4.0 — голосовой ввод условия на странице «Решить по фото». */
import { supabase, getSession } from './supabase.js';

const $ = (id) => document.getElementById(id);
const area = $('voice-text');
const mic = $('voice-mic');
const micLabel = $('voice-mic-label');
const solve = $('voice-solve');
const hint = $('voice-hint');
const out = $('voice-output');
let recognition = null;
let listening = false;

function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function say(text) {
  hint.textContent = text;
}

function stopRecognition() {
  listening = false;
  mic.classList.remove('is-listening');
  mic.setAttribute('aria-pressed', 'false');
  micLabel.textContent = 'Говорить';
  if (recognition) {
    try { recognition.stop(); } catch (err) { /* ignore */ }
  }
}

function buildRecognition() {
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Speech) {
    mic.disabled = true;
    say('Голосовой ввод не поддерживается этим браузером. Надиктуй текстом.');
    return null;
  }
  const rec = new Speech();
  rec.lang = 'ru-RU';
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;

  rec.onstart = () => {
    listening = true;
    mic.classList.add('is-listening');
    mic.setAttribute('aria-pressed', 'true');
    micLabel.textContent = 'Слушаю…';
    say('Говори условие. Нажми «Стоп», когда закончишь.');
  };
  rec.onresult = (event) => {
    let finalText = '';
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const item = event.results[i];
      if (item.isFinal) finalText += item[0].transcript + ' ';
      else interim += item[0].transcript;
    }
    if (finalText) {
      area.value = (area.value + ' ' + finalText).replace(/\s+/g, ' ').trim();
    }
    if (interim) say('Слышу: ' + interim);
  };
  rec.onerror = (event) => {
    if (event.error === 'not-allowed') say('Микрофон запрещён. Разреши доступ в настройках браузера.');
    else if (event.error === 'no-speech') say('Ничего не услышал. Попробуй ещё раз поближе к микрофону.');
    else say('Не получилось распознать голос. Можно ввести текст вручную.');
    stopRecognition();
  };
  rec.onend = () => stopRecognition();
  return rec;
}

async function solveText() {
  const condition = area.value.trim();
  if (condition.length < 5) {
    say('Надиктуй или напиши условие задачи.');
    area.focus();
    return;
  }
  const session = await getSession();
  if (!session) {
    location.href = 'auth.html?next=' + encodeURIComponent('photo.html');
    return;
  }
  solve.disabled = true;
  out.hidden = false;
  out.className = 'ai-output is-loading';
  out.innerHTML = '<p>Решаю задачу…</p>';
  try {
    const { data, error } = await supabase.functions.invoke('ai-tutor', {
      body: { action: 'solve', task: { condition, solution: '', answer: '', subject: 'text' }, question: '' }
    });
    if (error) {
      let message = 'ИИ временно недоступен.';
      try {
        if (error.context && error.context.json) {
          const body = await error.context.json();
          if (body && body.error) message = body.error;
        }
      } catch (err) { /* ignore */ }
      throw new Error(message);
    }
    if (!data || data.error) throw new Error((data && data.error) || 'пустой ответ');
    out.className = 'ai-output';
    out.innerHTML = '<p>' + esc(data.answer).replace(/\n/g, '<br>') + '</p>';
  } catch (err) {
    out.className = 'ai-output is-error';
    out.innerHTML = '<p>' + esc(err.message || 'Ошибка ИИ') + '</p>';
  } finally {
    solve.disabled = false;
  }
}

mic.addEventListener('click', () => {
  if (listening) { stopRecognition(); return; }
  if (!recognition) recognition = buildRecognition();
  if (!recognition) return;
  try { recognition.start(); } catch (err) {
    try { recognition.stop(); } catch (e) { /* ignore */ }
    setTimeout(() => { try { recognition.start(); } catch (e) { /* ignore */ } }, 120);
  }
});

solve.addEventListener('click', solveText);
area.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') solveText();
});
