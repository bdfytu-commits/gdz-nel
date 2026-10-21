-- Лайки доски почёта меняются только через security definer RPC honor_like.
-- Прямые insert/update/delete закрываем и для anon, и для authenticated:
-- RLS-политик на запись нет, но явные REVOKE убирают лишние гранты.

revoke insert, update, delete on public.honor_likes from anon, authenticated;
revoke execute on function public.honor_like(bigint) from anon;
