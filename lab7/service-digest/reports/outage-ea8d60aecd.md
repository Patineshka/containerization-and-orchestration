Время: 2026-10-30T17:00:11+00:00

Состояние:
- shop-api: работает
- shop-worker: работает
- shop-postgres: отключён

Проблема: shop-postgres недоступен.

Следующие действия:
1. Проверить готовность БД, свободное место и подключения
2. Передать дежурному по БД (database on-call)
3. Не перезапускать автоматически

Ответственные:
- Application on-call: API/worker
- Database on-call: PostgreSQL

Гипотеза риска: Отключение PostgreSQL может вызвать недоступность API и worker.