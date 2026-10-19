/* =========================================================
   ГДЗ НЭЛ — «решить по фото» (Groq Vision).

   Вызывает photo.html после загрузки фото в bucket photos.
   Порядок: проверка JWT -> бан -> лимит 5 фото/сутки (для «ГДЗ+»
   лимита нет) -> скачивание фото -> задержка 5 с для бесплатных ->
   Groq Vision -> запись в photo_requests -> ответ.

   Модель по умолчанию — meta-llama/qwen/qwen3.8-27b (как в ТЗ),
   запасные — qwen/qwen3.8-27b, meta-llama/llama-4-maverick-17b-128e-instruct.
   Переопределение — секрет GROQ_VISION_MODEL.

   «ГДЗ+»: выбор модели (payload.model: standard | smart | deep) и
   отсутствие задержки. Бесплатным задержка 5 секунд: фича показывает
   ценность подписки, обойти её из клиента нельзя.

   verify_jwt = true: только для залогиненных.
   ========================================================= */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const SYSTEM_PROMPT = `Ты — умный и вежливый помощник по учебе для школьников 6-9 классов. Твоя задача — решать задачи по фотографиям и объяснять их понятным языком.

ПРАВИЛА ОТВЕТА:
1. Пиши на русском языке, грамотно, с большой буквы. Без мата, грубости и оскорблений.
2. Не используй смайлики, эмодзи и лишние украшения. Только текст и математические символы.
3. Обращайся к пользователю нейтрально: «ты» или безлично.
4. Если в условии задачи есть ошибка или опечатка, вежливо укажи на это и реши в исправленном виде.
5. Если на фото не задача, а что-то другое, вежливо скажи, что не можешь это решить, и попроси загрузить фото учебного задания.

СТРУКТУРА РЕШЕНИЯ:
1. В начале выпиши краткое условие (что дано) в одну-две строки.
2. Разбей решение на нумерованные шаги. Каждый шаг с новой строки.
3. Внутри шагов обязательно поясняй, почему ты делаешь именно так.
4. В конце выдели финальный ответ отдельной строкой с пометкой «**Ответ:**».

ОФОРМЛЕНИЕ ФОРМУЛ И МАТЕМАТИКИ:
- Дроби пиши вертикально, если получается: (a+b)/2.
- Степени пиши через знак ^ (например, x^2).
- Корни пиши через sqrt() или словами «корень из...».
- Векторы и углы обозначай как в учебнике (например, ∠A = 30°, AB→).
- Уравнения и вычисления оформляй в отдельные строки, чтобы их было легко читать.
- ВАЖНО: Если задача на арифметические вычисления (сложение, вычитание, умножение, деление), после обычного решения выведи вычисление в столбик (используй отступы, чтобы цифры были ровно друг под другом):
    123
  +  45
  -----
    168

РАБОТА С КОДОМ (если на фото код):
- Укажи, на каком языке написан код.
- Найди ошибки и объясни, почему они возникли.
- Предложи исправленный вариант с комментариями.
- Не переписывай код, если он уже правильный, просто скажи, что он верный.
`;

const DEFAULT_MODEL = Deno.env.get('GROQ_VISION_MODEL') || 'meta-llama/qwen/qwen3.8-27b';

const VISION_FALLBACKS = [
  'qwen/qwen3.8-27b',
  'meta-llama/llama-4-maverick-17b-128e-instruct',
];

// «ГДЗ+»: ключи приходят из photo.html; сервер принимает только эти значения
const MODEL_CHOICES: Record<string, string> = {
  standard: DEFAULT_MODEL,
  smart: 'qwen/qwen3.8-27b',
  deep: 'meta-llama/llama-4-maverick-17b-128e-instruct',
};

function modelChain(choice: unknown): string[] {
  const picked = typeof choice === 'string' ? MODEL_CHOICES[choice] : undefined;
  if (!picked) return [DEFAULT_MODEL, ...VISION_FALLBACKS.filter((model) => model !== DEFAULT_MODEL)];
  return [picked, ...VISION_FALLBACKS.filter((model) => model !== picked)];
}

// задержка для бесплатных (Ф35: «ГДЗ+» — мгновенно)
const FREE_DELAY_MS = 5000;

const DAILY_LIMIT = 5;
const MAX_BYTES = 6 * 1024 * 1024;

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

function toBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function mimeFrom(url: string, contentType: string | null): string {
  if (contentType && contentType.startsWith('image/')) return contentType.split(';')[0];
  const ext = url.split('?')[0].split('.').pop()?.toLowerCase();
  if (ext === 'png') return 'image/png';
  if (ext === 'webp') return 'image/webp';
  return 'image/jpeg';
}

async function askGroq(apiKey: string, dataUrl: string, models: string[]): Promise<{ answer: string; model: string }> {
  let lastError = '';

  for (const model of models) {
    const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        temperature: 0.2,
        max_tokens: 2048,
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          {
            role: 'user',
            content: [
              { type: 'text', text: 'Это фото задания. Помоги его решить.' },
              { type: 'image_url', image_url: { url: dataUrl } },
            ],
          },
        ],
      }),
      signal: AbortSignal.timeout(60000),
    });

    if (res.ok) {
      const data = await res.json();
      const answer = String(data?.choices?.[0]?.message?.content || '').trim();
      if (answer) return { answer, model };
      lastError = `${model}: пустой ответ`;
      continue;
    }

    lastError = `${model}: HTTP ${res.status} ${(await res.text().catch(() => '')).slice(0, 300)}`;
    if (res.status >= 500) break; // Groq лежит — перебор моделей не поможет
  }

  throw new Error(`Groq Vision недоступен: ${lastError}`);
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  if (req.method !== 'POST') return json({ error: 'только POST' }, 405);

  const url = Deno.env.get('SUPABASE_URL');
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') || Deno.env.get('SUPABASE_SECRET_KEY');
  const groqKey = Deno.env.get('GROQ_API_KEY');

  if (!url || !serviceKey) {
    return json({ error: 'нет service-ключа Supabase (SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SECRET_KEY)' }, 500);
  }
  if (!groqKey) {
    return json({ error: 'нет GROQ_API_KEY (supabase secrets set GROQ_API_KEY=...)' }, 500);
  }

  const jwt = (req.headers.get('Authorization') || '').replace(/^Bearer\s+/i, '');
  if (!jwt) return json({ error: 'нужен вход в аккаунт' }, 401);

  const db = createClient(url, serviceKey, { auth: { persistSession: false } });

  const { data: userData, error: userErr } = await db.auth.getUser(jwt);
  const user = userData?.user;
  if (userErr || !user) return json({ error: 'сессия недействительна, войди заново' }, 401);

  const { data: profile } = await db.from('profiles')
    .select('ban, is_premium, premium_until').eq('id', user.id).single();
  if (profile?.ban) return json({ error: 'аккаунт заблокирован' }, 403);

  // «ГДЗ+»: активная подписка снимает лимит фото (Ф35.4)
  const isPremium = !!profile?.is_premium &&
    !!profile?.premium_until && new Date(profile.premium_until) > new Date();

  let payload: any;
  try {
    payload = await req.json();
  } catch {
    return json({ error: 'тело запроса не JSON' }, 400);
  }

  const imageUrl = String(payload?.image_url || '').trim();
  // выбор модели доступен только «ГДЗ+», остальным — дефолтная цепочка
  const chain = modelChain(isPremium ? payload?.model : undefined);
  const prefix = `${url}/storage/v1/object/public/photos/${user.id}/`;
  if (!imageUrl.startsWith(prefix)) {
    return json({ error: 'можно отправлять только свои фото' }, 403);
  }

  // лимит 5 фото в сутки на аккаунт; у «ГДЗ+» лимита нет
  if (!isPremium) {
    const dayAgo = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
    const { count } = await db
      .from('photo_requests')
      .select('id', { count: 'exact', head: true })
      .eq('user_id', user.id)
      .gte('created_at', dayAgo);

    if ((count || 0) >= DAILY_LIMIT) {
      return json({
        error: 'Лимит 5 фото в день исчерпан. В «ГДЗ+» фото без ограничений.',
        premium_url: 'premium.html',
      }, 429);
    }
  }

  // скачиваем фото и готовим data-url
  const imgRes = await fetch(imageUrl);
  if (!imgRes.ok) return json({ error: 'фото не открывается — попробуй загрузить ещё раз' }, 400);

  const bytes = new Uint8Array(await imgRes.arrayBuffer());
  if (bytes.length > MAX_BYTES) return json({ error: 'фото слишком большое (максимум 6 МБ)' }, 413);

  const dataUrl = `data:${mimeFrom(imageUrl, imgRes.headers.get('content-type'))};base64,${toBase64(bytes)}`;

  // бесплатные ждут 5 секунд, «ГДЗ+» — без задержки
  if (!isPremium) await new Promise((resolve) => setTimeout(resolve, FREE_DELAY_MS));

  try {
    const { answer, model } = await askGroq(groqKey, dataUrl, chain);

    // запись только после успешного ответа — неудачные попытки лимит не съедают
    const { error: insErr } = await db.from('photo_requests').insert({
      user_id: user.id,
      image_url: imageUrl,
      ai_response: answer,
    });
    if (insErr) console.error('не записал photo_requests:', insErr.message);

    console.log(`фото ${user.id}: ответ получен (${model}, ${bytes.length} байт, premium: ${isPremium})`);
    return json({ answer, model });
  } catch (err) {
    console.error('vision не сработал:', (err as Error).message);
    return json({ error: (err as Error).message }, 502);
  }
});
