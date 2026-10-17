-- ГДЗ НЭЛ: автозапуск ИИ-модерации отзывов
-- После вставки отзыва вызываем edge-функцию moderate-review (её деплой — docs/SUPABASE.md).
-- Альтернатива: Database Webhook в дашборде (Database → Webhooks) с теми же URL/заголовками.

create extension if not exists pg_net with schema extensions;

create or replace function public.notify_moderate_review()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  fn_url text := 'https://qncqeoklwblztbnoktwk.supabase.co/functions/v1/moderate-review';
  anon_key text := 'sb_publishable_uyBIZ2gNPuDqxre3ea989w_WbctezF4';
begin
  perform net.http_post(
    url := fn_url,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || anon_key
    ),
    body := jsonb_build_object(
      'type', 'INSERT',
      'table', 'reviews',
      'schema', 'public',
      'record', to_jsonb(new)
    )
  );
  return new;
end;
$$;

drop trigger if exists reviews_moderate_webhook on public.reviews;
create trigger reviews_moderate_webhook
  after insert on public.reviews
  for each row execute function public.notify_moderate_review();
