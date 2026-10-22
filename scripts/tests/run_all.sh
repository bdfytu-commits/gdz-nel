#!/usr/bin/env bash
# Все смоуки подряд. Сервер :8000 должен быть поднят.
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=scripts/venv-shots/bin/python
rc=0
for t in test_seo smoke_app test_offline smoke_lit smoke_premium2 smoke_kontur smoke_review smoke_admin test_admin_premium smoke_visual test_mobile_375; do
  echo
  echo "== $t"
  "$PY" "scripts/tests/$t.py" || rc=1
done
echo
if [ "$rc" -eq 0 ]; then
  echo "все смоуки зелёные"
else
  echo "есть падения — см. вывод выше"
fi
exit "$rc"
