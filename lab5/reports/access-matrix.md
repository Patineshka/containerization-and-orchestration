# Целевая матрица доступа

Все соединения, не перечисленные как разрешенные, запрещены.
Ответный трафик разрешенных соединений допускается автоматически.

| Источник | Назначение | Порт | Результат |
|---|---|---|---|
| shop-client | shop-api | TCP 8080 | Разрешено |
| Тестовый клиент через NodePort | shop-api через ноду | TCP 30080 → 8080 | Разрешено |
| shop-client | shop-worker | TCP 8080 | Запрещено |
| shop-client | PostgreSQL | TCP 5432 | Запрещено |
| shop-api | PostgreSQL | TCP 5432 | Разрешено |
| shop-worker | PostgreSQL | TCP 5432 | Разрешено |
| shop-worker | shop-api | TCP 8080 | Запрещено |
| shop-api | shop-worker | TCP 8080 | Запрещено |
| Посторонний Pod | API, worker, PostgreSQL | Порты приложений | Запрещено |
| Pod приложения и клиента | CoreDNS | UDP/TCP 53 | Разрешено |
| shop-api, shop-worker | Jaeger | TCP 4317 | Разрешено |
| Prometheus | API, worker | TCP 8080 | Разрешено |
| Контроллер CloudNativePG | PostgreSQL instance manager | TCP 8000 | Разрешено |
| PostgreSQL instance manager | Kubernetes API | HTTPS | Разрешено |

Для NetworkPolicy необходимо учитывать адреса и порты после трансляции
Service/NodePort, а также фактический источник трафика.
