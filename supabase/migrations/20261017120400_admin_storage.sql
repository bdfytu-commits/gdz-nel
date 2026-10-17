-- ГДЗ НЭЛ: админская политика удаления фото
-- Пользовательская photos_storage_delete разрешает удалять только свою папку.
-- Админке нужно сносить и чужие нарушения — добавляем отдельную политику.

drop policy if exists photos_storage_admin_delete on storage.objects;
create policy photos_storage_admin_delete on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'photos'
    and public.is_admin()
  );

-- фото-логи: админ может удалять записи (обычные пользователи — нет)
drop policy if exists photo_requests_delete on public.photo_requests;
create policy photo_requests_delete on public.photo_requests
  for delete to authenticated
  using (public.is_admin());
