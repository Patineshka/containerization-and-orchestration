Сводка дежурного
Время: 2026-10-30T17:08:32.581863+00:00

Состояние сервисов:
- shop-api: healthy (последняя проверка: 2026-10-30T17:09:47.997864+00:00)
- shop-worker: healthy
- shop-postgres: healthy

Проблемы: Отсутствуют.

Следующие действия:
- Проверить /health, readiness и подключение к PostgreSQL для shop-api.
- Проверить время последнего успешного опроса БД и очередь заказов для shop-worker.
- Проверить готовность БД, свободное место и подключения для shop-postgres.

Ответственные роли:
- Application on-call: API/worker
- Database on-call: PostgreSQL