-- ===========================================================================
-- ГДЗ НЭЛ 2.0 — отзывы: пост-модерация вместо пред-модерации.
--
-- Причина: ИИ-модерация (edge-функция moderate-review) в проде не развёрнута
-- (вебхук отвечает 404/502), поэтому is_approved навсегда оставался false
-- и отзывы не появлялись. Теперь отзыв публикуется сразу, а ИИ-модерация,
-- когда развернута, работает постфактум: APPROVE — оставляет, REJECT —
-- скрывает (is_approved = false).
-- ===========================================================================

-- 1. новые отзывы публикуются сразу
alter table public.reviews alter column is_approved set default true;

-- 2. вставка: достаточно своей сессии и отсутствия бана; публикацию
--    больше не требуются is_approved=false / ai_status='pending'
drop policy if exists reviews_insert on public.reviews;
create policy reviews_insert on public.reviews
  for insert to authenticated
  with check (user_id = auth.uid() and not public.is_banned());

-- 3. бэкфилл: отзывы, зависшие в pending из-за мёртвой модерации, публикуем
update public.reviews
   set is_approved = true
 where ai_status = 'pending'
   and is_approved = false;
