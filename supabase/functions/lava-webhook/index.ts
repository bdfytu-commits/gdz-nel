/* =========================================================
   ГДЗ НЭЛ — вебхук оплаты Lava.top (подписка «ГДЗ+»).

   Lava.top отправляет сюда POST при событиях оплаты. Функция:
     1) при включённом секрете проверяет подпись тела запроса;
     2) мягко разбирает событие: email покупателя, id платежа,
        сумма, статус (структура у Lava может отличаться от события
        к событию, поэтому поля ищутся по списку кандидатов);
     3) вызывает RPC grant_premium — запись в payments и выдача
        подписки на 30 дней (продление складывается, повторный
        вебхук с тем же payment_id ничего не дублирует).

   Деплой:
     supabase functions deploy lava-webhook --no-verify-jwt
     supabase secrets set LAVA_WEBHOOK_SECRET=...   # секрет подписи (необязательно)
     supabase secrets set PREMIUM_DAYS=30           # срок подписки (необязательно)

   URL функции (вставить в личный кабинет Lava):
     https://<project-ref>.supabase.co/functions/v1/lava-webhook
   ========================================================= */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-lava-signature, x-signature',
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

/* ---------- подпись ---------- */

async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
  return [...new Uint8Array(signature)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function signatureValid(req: Request, rawBody: string, secret: string): Promise<boolean | 'absent'> {
  const header =
    req.headers.get('x-lava-signature') ||
    req.headers.get('x-signature') ||
    req.headers.get('x-hook-signature') ||
    '';
  if (!header) return 'absent';
  const expected = await hmacHex(secret, rawBody);
  const given = header.replace(/^sha256=/i, '').trim().toLowerCase();
  if (given.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ given.charCodeAt(i);
  return diff === 0;
}

/* ---------- разбор события ---------- */

type Json = Record<string, unknown>;

function deepFind(obj: unknown, pick: (value: unknown) => string | null, depth = 0): string | null {
  if (depth > 6 || obj === null || typeof obj !== 'object') return null;
  const direct = pick(obj);
  if (direct) return direct;
  for (const value of Object.values(obj as Json)) {
    if (value && typeof value === 'object') {
      const found = deepFind(value, pick, depth + 1);
      if (found) return found;
    }
  }
  return null;
}

function pickString(root: Json, keys: string[]): string {
  for (const key of keys) {
    const value = root[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (typeof value === 'number') return String(value);
  }
  return '';
}

function pickNumber(root: Json, keys: string[]): number | null {
  for (const key of keys) {
    const value = root[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string') {
      const parsed = Number(value.replace(',', '.'));
      if (Number.isFinite(parsed)) return parsed;
    }
    if (value && typeof value === 'object') {
      const inner = pickNumber(value as Json, ['value', 'amount', 'total', 'price']);
      if (inner !== null) return inner;
    }
  }
  return null;
}

function pickEmail(payload: Json): string {
  const direct = pickString(payload, [
    'email', 'buyer_email', 'buyerEmail', 'customer_email', 'payer_email',
  ]);
  if (direct.includes('@')) return direct;

  const nested = deepFind(payload, (value) => {
    if (!value || typeof value !== 'object') return null;
    const candidate = pickString(value as Json, ['email', 'buyerEmail', 'customerEmail']);
    return candidate.includes('@') ? candidate : null;
  });
  if (nested) return nested;

  const anyMail = deepFind(payload, (value) =>
    typeof value === 'string' && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim()) ? value.trim() : null);
  return anyMail || '';
}

const SUCCESS = ['success', 'successful', 'succeeded', 'paid', 'completed', 'active', 'approved'];
const FAILED = ['fail', 'error', 'cancel', 'refund', 'reject', 'expire', 'decline', 'unpaid'];

function normalizeStatus(payload: Json): string {
  const raw = (pickString(payload, ['status', 'event', 'type', 'state', 'payment_status']) || '').toLowerCase();
  if (!raw) return 'unknown';
  if (FAILED.some((word) => raw.includes(word))) return 'failed';
  if (SUCCESS.some((word) => raw.includes(word))) return 'success';
  return 'other';
}

/* ---------- сервер ---------- */

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  if (req.method === 'GET') {
    return json({ ok: true, service: 'gdz-nel lava-webhook', hint: 'сюда шлёт события Lava.top (POST)' });
  }
  if (req.method !== 'POST') return json({ error: 'только POST' }, 405);

  const url = Deno.env.get('SUPABASE_URL');
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') || Deno.env.get('SUPABASE_SECRET_KEY');
  if (!url || !serviceKey) return json({ error: 'нет service-ключа Supabase' }, 500);

  const rawBody = await req.text();
  const secret = Deno.env.get('LAVA_WEBHOOK_SECRET') || '';

  if (secret) {
    const check = await signatureValid(req, rawBody, secret);
    if (check === false) {
      console.warn('lava-webhook: подпись не совпала');
      return json({ error: 'неверная подпись' }, 401);
    }
    if (check === 'absent') console.warn('lava-webhook: подпись не передана (LAVA_WEBHOOK_SECRET включён)');
  }

  let payload: Json;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return json({ error: 'тело не JSON' }, 400);
  }

  const status = normalizeStatus(payload);
  const email = pickEmail(payload);
  const paymentId = pickString(payload, [
    'id', 'payment_id', 'paymentId', 'transaction_id', 'transactionId',
    'contractId', 'contract_id', 'invoice_id', 'invoiceId',
  ]) || deepFind(payload, (value) => {
    if (!value || typeof value !== 'object') return null;
    const candidate = pickString(value as Json, ['id', 'paymentId', 'transactionId']);
    return /^[0-9a-f-]{8,}$/i.test(candidate) ? candidate : null;
  }) || '';
  const amount = pickNumber(payload, ['amount', 'price', 'total', 'sum', 'value']);
  const days = Number(Deno.env.get('PREMIUM_DAYS') || '30') || 30;

  console.log('lava-webhook:', JSON.stringify({ status, email, paymentId, amount, days }));

  if (!email) {
    // сохраняем событие без email — разберёт админ по логам
    const { error } = await createClient(url, serviceKey, { auth: { persistSession: false } })
      .from('payments')
      .insert({ status, payment_id: paymentId || null, amount, raw: payload });
    if (error) console.error('payments insert:', error.message);
    return json({ ok: true, note: 'нет email в событии — записан платёж без пользователя' });
  }

  const db = createClient(url, serviceKey, { auth: { persistSession: false } });
  const { data: uid, error } = await db.rpc('grant_premium', {
    target_email: email,
    days,
    payment: paymentId || null,
    amount_value: amount,
    pay_status: status,
    payload,
  });

  if (error) {
    console.error('grant_premium:', error.message);
    return json({ error: 'не удалось обработать платёж' }, 500);
  }

  if (status === 'success' && !uid) {
    console.warn('lava-webhook: оплата есть, аккаунта с таким email нет:', email);
    return json({ ok: true, note: 'оплата записана, аккаунт с таким email не найден' });
  }

  return json({ ok: true, status, user: uid || null });
});
