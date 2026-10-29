# Проверка целевой матрицы из всех реплик

| Namespace | Pod-источник | Назначение | Ожидаемо | Фактически | Результат |
|---|---|---|---|---|---|
| lab3 | shop-api-6c56f79b5c-44hnb | shop-postgres-rw:5432 | allow | allow | PASS |
| lab3 | shop-api-6c56f79b5c-44hnb | shop-worker:8080 | deny | timeout | PASS |
| lab3 | shop-api-6c56f79b5c-gdrcw | shop-postgres-rw:5432 | allow | allow | PASS |
| lab3 | shop-api-6c56f79b5c-gdrcw | shop-worker:8080 | deny | timeout | PASS |
| lab3 | shop-api-6c56f79b5c-n5bxm | shop-postgres-rw:5432 | allow | allow | PASS |
| lab3 | shop-api-6c56f79b5c-n5bxm | shop-worker:8080 | deny | timeout | PASS |
| lab3 | shop-api-6c56f79b5c-w5mn4 | shop-postgres-rw:5432 | allow | allow | PASS |
| lab3 | shop-api-6c56f79b5c-w5mn4 | shop-worker:8080 | deny | timeout | PASS |
| lab3 | shop-client | shop-api:8080 | allow | allow | PASS |
| lab3 | shop-client | shop-worker:8080 | deny | timeout | PASS |
| lab3 | shop-client | shop-postgres-rw:5432 | deny | timeout | PASS |
| lab3 | shop-postgres-1 | shop-api:8080 | deny | timeout | PASS |
| lab3 | shop-postgres-1 | shop-worker:8080 | deny | timeout | PASS |
| lab3 | shop-worker-57d444454f-s7tvj | shop-postgres-rw:5432 | allow | allow | PASS |
| lab3 | shop-worker-57d444454f-s7tvj | shop-api:8080 | deny | timeout | PASS |
| lab3 | shop-worker-57d444454f-x6ccp | shop-postgres-rw:5432 | allow | allow | PASS |
| lab3 | shop-worker-57d444454f-x6ccp | shop-api:8080 | deny | timeout | PASS |
| lab5-outsider | outsider | shop-api:8080 | deny | timeout | PASS |
| lab5-outsider | outsider | shop-worker:8080 | deny | timeout | PASS |
| lab5-outsider | outsider | shop-postgres-rw:5432 | deny | timeout | PASS |

Проверяются связи целевой матрицы между ролями. Соединения с собственным сервисом не включены.
Назначения проверяются по ClusterIP; DNS проверен отдельно. Тайм-ауты запретов нужно сопоставить с Hubble.

Итого: 9 Pod, 20 проверок, ошибок: 0.
