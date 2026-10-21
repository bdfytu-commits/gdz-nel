/* =========================================================
   ГДЗ НЭЛ — ИИ-модерация отзывов.

   Триггер: вебхук pg_net при INSERT в public.reviews
   (миграция 20261017120300_webhook.sql). Тело запроса вебхука не
   считается доверенным: функция перечитывает отзыв из базы по id.

   Ответ Groq: 'APPROVE' — публикуем, 'REJECT' — отклоняем.
   В ТЗ была llama-3.1-8b-instant, но Groq отключил её для self-serve
   16.08.2026. Актуальная замена — openai/gpt-oss-20b, запасные —
   openai/gpt-oss-120b и openai/gpt-oss-safeguard-20b.
   Переопределение — секрет GROQ_MODEL.

   verify_jwt = false: вызов идёт из базы, без JWT.
   ========================================================= */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const SYSTEM_PROMPT = "Ты модератор школьного сайта ГДЗ. Если текст содержит мат, оскорбления, рекламу, спам или бред — ответь строго 'REJECT'. Если это адекватная критика или похвала по теме — ответь строго 'APPROVE'.";

const MODELS = [
  Deno.env.get('GROQ_MODEL') || 'openai/gpt-oss-20b',
  'openai/gpt-oss-120b',
  'openai/gpt-oss-safeguard-20b',
];

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

async function askGroq(apiKey: string, text: string): Promise<{ verdict: string; model: string }> {
  let lastError = '';

  for (const model of MODELS) {
    const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        temperature: 0,
        max_tokens: 80,
        reasoning_effort: 'low',
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: text },
        ],
      }),
      signal: AbortSignal.timeout(20000),
    });

    if (res.ok) {
      const data = await res.json();
      const content = String(data?.choices?.[0]?.message?.content || '').trim().toUpperCase();
      // Модель может вернуть пустой content (reasoning-модель) или мусор.
      // Тогда не отклоняем отзыв молча, а пробуем следующую модель / fail-safe.
      if (content.includes('APPROVE')) return { verdict: 'APPROVE', model };
      if (content.includes('REJECT')) return { verdict: 'REJECT', model };
      lastError = `${model}: пустой или непонятный ответ ${JSON.stringify(content.slice(0, 80))}`;
      continue;
    }

    lastError = `${model}: HTTP ${res.status} ${(await res.text().catch(() => '')).slice(0, 300)}`;
    if (res.status >= 500) break; // Groq лежит — перебор моделей не поможет
  }

  throw new Error(`Groq недоступен: ${lastError}`);
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  if (req.method !== 'POST') return json({ error: 'только POST' }, 405);

  const url = Deno.env.get('SUPABASE_URL');
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') || Deno.env.get('SUPABASE_SECRET_KEY');
  const groqKey = Deno.env.get('GROQ_API_KEY');

  let payload: any;
  try {
    payload = await req.json();
  } catch {
    return json({ error: 'тело запроса не JSON' }, 400);
  }

  const id = payload?.record?.id ?? payload?.id;
  if (!id) return json({ error: 'в запросе нет id отзыва' }, 400);

  if (!url || !serviceKey) {
    return json({ error: 'нет service-ключа Supabase (SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SECRET_KEY)' }, 500);
  }

  const db = createClient(url, serviceKey, { auth: { persistSession: false } });

  // fail-safe: если модератор недоступен, отзыв не должен зависнуть навсегда
  async function approveFallback(reason: string) {
    await db.from('reviews')
      .update({ is_approved: true, ai_status: 'approved', ai_reason: reason })
      .eq('id', id)
      .eq('ai_status', 'pending');
    return json({ ok: true, skipped: true, failSafe: true, reason });
  }

  if (!groqKey) return approveFallback('GROQ_API_KEY не задан');

  const { data: review, error } = await db
    .from('reviews')
    .select('id, text, ai_status')
    .eq('id', id)
    .single();

  if (error || !review) return json({ error: 'отзыв не найден' }, 404);
  if (review.ai_status !== 'pending') return json({ ok: true, skipped: review.ai_status });

  try {
    const { verdict, model } = await askGroq(groqKey, review.text);
    const approved = verdict === 'APPROVE';

    const { error: updErr } = await db
      .from('reviews')
      .update({
        is_approved: approved,
        ai_status: approved ? 'approved' : 'rejected',
        ai_reason: approved ? `Groq: ${model}` : `Groq: ${model} отклонил`,
      })
      .eq('id', id)
      .eq('ai_status', 'pending');

    if (updErr) return json({ error: 'не получилось обновить отзыв: ' + updErr.message }, 500);

    console.log(`отзыв ${id}: ${verdict} (${model})`);
    return json({ ok: true, verdict, model });
  } catch (err) {
    console.error('модерация не удалась:', (err as Error).message);
    return approveFallback('Groq недоступен: ' + (err as Error).message);
  }
});
