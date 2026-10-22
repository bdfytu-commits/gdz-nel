/* =========================================================
   ГДЗ НЭЛ 4.0 — ИИ-репетитор.

   Действия:
     explain — переписать готовое решение простым языком;
     ask     — ответить на вопрос по конкретному шагу;
     similar — придумать 3 похожие задачи;
     solve   — решить задачу, надиктованную голосом.

   Ключ Groq остаётся только на сервере (GROQ_API_KEY).
   Вызывать может только залогиненный пользователь с валидным JWT.
   ========================================================= */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const DEFAULT_MODEL = Deno.env.get('GROQ_TEXT_MODEL') || 'openai/gpt-oss-20b';
const FALLBACKS = ['openai/gpt-oss-120b', 'llama-3.3-70b-versatile'];
const MAX_INPUT = 8000;
const MAX_QUESTION = 1200;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

function clip(value: unknown, limit: number): string {
  return String(value ?? '').replace(/\u0000/g, '').trim().slice(0, limit);
}

function extractJson(text: string): unknown {
  const cleaned = text.replace(/```(?:json)?/gi, '').replace(/```/g, '').trim();
  try { return JSON.parse(cleaned); } catch { /* ниже ищем массив */ }
  const start = cleaned.indexOf('[');
  const end = cleaned.lastIndexOf(']');
  if (start !== -1 && end > start) {
    try { return JSON.parse(cleaned.slice(start, end + 1)); } catch { /* ignore */ }
  }
  return null;
}

function systemPrompt(action: string): string {
  const base = `Ты — терпеливый репетитор для школьников 1–11 классов. Пиши по-русски, без мата, смайликов и воды. Не выдумывай факты. Если данных не хватает — скажи об этом. Оформляй шаги списком, формулы — обычным текстом.`;
  if (action === 'explain') {
    return `${base} Перепиши готовое решение так, чтобы понял ученик младше: короткие предложения, простые слова, каждый шаг с объяснением «почему». Не меняй ответ. В конце одна строка «Запомни: …».`;
  }
  if (action === 'ask') {
    return `${base} Отвечай только на заданный вопрос по решению. Объясни именно этот шаг, не пересказывай всё решение. Максимум 8 предложений.`;
  }
  if (action === 'similar') {
    return `${base} Придумай ровно 3 похожие задачи с теми же правилами, но другими числами/условиями. Верни СТРОГО JSON-массив без пояснений: [{"condition":"…","answer":"…","hint":"…"}]. В condition — полное условие, в answer — краткий ответ, в hint — одна подсказка.`;
  }
  return `${base} Реши задачу пошагово, объясняя каждое действие. В конце строка «Ответ: …».`;
}

function userPrompt(action: string, task: Record<string, unknown>, question: string): string {
  const condition = clip(task.condition, 5000);
  const solution = clip(task.solution, 5000);
  const answer = clip(task.answer, 2000);
  const subject = clip(task.subject, 100);
  if (action === 'explain') {
    return `Предмет: ${subject}\nУсловие: ${condition}\nГотовое решение: ${solution || '(нет текста, только ответ)'}\nОтвет: ${answer || '(нет)'}\n\nОбъясни проще.`;
  }
  if (action === 'ask') {
    return `Предмет: ${subject}\nУсловие: ${condition}\nРешение: ${solution}\nОтвет: ${answer}\nВопрос ученика: ${question}`;
  }
  if (action === 'similar') {
    return `Предмет: ${subject}\nИсходное условие: ${condition}\nРешение: ${solution}\nОтвет: ${answer}\n\nСделай 3 похожие задачи в JSON.`;
  }
  return `Предмет: ${subject}\nЗадача: ${condition}\n\nРеши её.`;
}

async function askGroq(key: string, action: string, task: Record<string, unknown>, question: string) {
  const models = [DEFAULT_MODEL, ...FALLBACKS.filter((model) => model !== DEFAULT_MODEL)];
  let lastError = '';

  for (const model of models) {
    const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${key}`,
      },
      body: JSON.stringify({
        model,
        temperature: action === 'similar' ? 0.8 : 0.25,
        max_tokens: action === 'similar' ? 1800 : 2200,
        messages: [
          { role: 'system', content: systemPrompt(action) },
          { role: 'user', content: userPrompt(action, task, question) },
        ],
      }),
      signal: AbortSignal.timeout(60000),
    });

    if (res.ok) {
      const data = await res.json();
      const text = String(data?.choices?.[0]?.message?.content || '').trim();
      if (text) return { text, model };
      lastError = `${model}: пустой ответ`;
      continue;
    }

    lastError = `${model}: HTTP ${res.status}`;
    if (res.status === 401 || res.status === 403) break;
  }
  throw new Error(`Groq недоступен: ${lastError}`);
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  if (req.method !== 'POST') return json({ error: 'только POST' }, 405);

  const url = Deno.env.get('SUPABASE_URL');
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') || Deno.env.get('SUPABASE_SECRET_KEY');
  const groqKey = Deno.env.get('GROQ_API_KEY');
  if (!url || !serviceKey) return json({ error: 'на сервере не настроен Supabase service key' }, 500);
  if (!groqKey) return json({ error: 'на сервере не настроен GROQ_API_KEY' }, 500);

  const jwt = (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
  if (!jwt) return json({ error: 'нужен вход в аккаунт' }, 401);

  const db = createClient(url, serviceKey, { auth: { persistSession: false } });
  const { data: userData, error: userErr } = await db.auth.getUser(jwt);
  const user = userData?.user;
  if (userErr || !user) return json({ error: 'сессия недействительна, войди заново' }, 401);

  const { data: profile } = await db.from('profiles')
    .select('ban, is_premium, premium_until').eq('id', user.id).single();
  if (profile?.ban) return json({ error: 'аккаунт заблокирован' }, 403);

  let payload: Record<string, unknown>;
  try {
    payload = await req.json();
  } catch {
    return json({ error: 'тело запроса не JSON' }, 400);
  }

  const action = clip(payload.action, 20);
  if (!['explain', 'ask', 'similar', 'solve'].includes(action)) {
    return json({ error: 'неизвестное действие' }, 400);
  }

  const rawTask = payload.task && typeof payload.task === 'object' ? payload.task : {};
  const task = {
    condition: clip((rawTask as Record<string, unknown>).condition, MAX_INPUT),
    solution: clip((rawTask as Record<string, unknown>).solution, MAX_INPUT),
    answer: clip((rawTask as Record<string, unknown>).answer, 3000),
    subject: clip((rawTask as Record<string, unknown>).subject, 100),
  };
  const question = clip(payload.question, MAX_QUESTION);

  if (action !== 'solve' && !task.condition && !task.solution) {
    return json({ error: 'нет условия или решения' }, 400);
  }
  if (action === 'ask' && !question) return json({ error: 'напиши вопрос' }, 400);
  if (action === 'solve' && !task.condition) return json({ error: 'нет текста задачи' }, 400);

  try {
    const { text, model } = await askGroq(groqKey, action, task, question);
    if (action === 'similar') {
      const parsed = extractJson(text);
      const tasks = Array.isArray(parsed)
        ? parsed.filter((item) => item && typeof item === 'object').slice(0, 3).map((item) => ({
            condition: clip((item as Record<string, unknown>).condition, 3000),
            answer: clip((item as Record<string, unknown>).answer, 1000),
            hint: clip((item as Record<string, unknown>).hint, 1000),
          })).filter((item) => item.condition)
        : [];
      return json({ tasks, raw: tasks.length ? undefined : text, model });
    }
    return json({ answer: text, model });
  } catch (err) {
    console.error('ai-tutor:', err);
    return json({ error: 'ИИ временно недоступен — попробуй ещё раз' }, 502);
  }
});
