/* =========================================================
   ГДЗ НЭЛ 4.0 — лог запросов и простой rate limit.

   Клиент вызывает функцию при загрузке страницы. Функция:
     1) достаёт IP из заголовков Cloudflare/Supabase;
     2) проверяет активный бан;
     3) пишет запрос в request_logs;
     4) если за минуту было >= 50 запросов — банит IP на 15 минут
        и помечает событие как DDoS.

   Это прикладной слой. Настоящую защиту от объёмных атак нужно
   включать в Cloudflare WAF / Rate Limiting; клиентский вызов можно
   обойти, поэтому Edge Function не заменяет CDN-защиту.
   ========================================================= */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const LIMIT = 50;
const WINDOW_SECONDS = 60;
const BAN_MINUTES = 15;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

function clientIp(req: Request): string {
  const cf = req.headers.get('cf-connecting-ip');
  if (cf) return cf.trim().slice(0, 64);
  const real = req.headers.get('x-real-ip');
  if (real) return real.trim().slice(0, 64);
  const forwarded = (req.headers.get('x-forwarded-for') || '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
  // последний адрес добавлен доверенным прокси, первый может быть подделан
  return (forwarded[forwarded.length - 1] || 'unknown').slice(0, 64);
}

function cleanPath(value: unknown): string {
  const raw = String(value || '/').split('?')[0].split('#')[0];
  const path = raw.startsWith('/') ? raw : '/' + raw;
  return path.slice(0, 300);
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  if (req.method !== 'POST') return json({ error: 'только POST' }, 405);

  const url = Deno.env.get('SUPABASE_URL');
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') || Deno.env.get('SUPABASE_SECRET_KEY');
  if (!url || !serviceKey) return json({ error: 'нет service-ключа Supabase' }, 500);

  let payload: Record<string, unknown> = {};
  try {
    payload = await req.json();
  } catch {
    // путь необязателен: лог всё равно нужен
  }

  const db = createClient(url, serviceKey, { auth: { persistSession: false } });
  const ip = clientIp(req);
  const now = new Date();
  const path = cleanPath(payload.path);

  const ban = await db.from('ip_bans')
    .select('banned_until, reason')
    .eq('ip', ip)
    .gt('banned_until', now.toISOString())
    .maybeSingle();

  if (ban.data) {
    return json({
      error: 'слишком много запросов, временный бан',
      retry_after: Math.max(1, Math.ceil((new Date(ban.data.banned_until).getTime() - now.getTime()) / 1000)),
    }, 429);
  }

  const since = new Date(now.getTime() - WINDOW_SECONDS * 1000).toISOString();
  const counted = await db
    .from('request_logs')
    .select('id', { count: 'exact', head: true })
    .eq('ip', ip)
    .gte('created_at', since);

  const recent = counted.count || 0;
  const ddos = recent >= LIMIT;
  const bannedUntil = new Date(now.getTime() + BAN_MINUTES * 60 * 1000).toISOString();

  const inserted = await db.from('request_logs').insert({
    ip,
    path,
    method: req.method,
    user_agent: String(req.headers.get('user-agent') || '').slice(0, 400),
    status: ddos ? 429 : 200,
    is_ddos: ddos,
  });

  if (inserted.error) {
    console.error('request_logs insert:', inserted.error.message);
    return json({ error: 'лог недоступен' }, 500);
  }

  if (ddos) {
    const banRes = await db.from('ip_bans').upsert({
      ip,
      banned_until: bannedUntil,
      reason: `>${LIMIT} запросов за ${WINDOW_SECONDS} с`,
      is_ddos: true,
    }, { onConflict: 'ip' });
    if (banRes.error) console.error('ip_bans upsert:', banRes.error.message);
    return json({
      error: 'превышен лимит запросов',
      banned_until: bannedUntil,
      retry_after: BAN_MINUTES * 60,
    }, 429);
  }

  return json({ ok: true, count: recent + 1, limit: LIMIT });
});
