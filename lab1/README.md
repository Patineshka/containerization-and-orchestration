# Лаба 1 — Свой Docker
## Часть 0 — Свой сервис
Был создан небольшой [service]() на Python c тремя эндпоинтами:
| Эндпоинт | Что делает |
|---|---|
| `/health` | Возвращает `ok` |
| `/eat?mb=N` | Выделяет N МиБ памяти и удерживает её; повторные запросы добавляют память |
| `/burn` | Запускает бесконечную нагрузку на одно ядро CPU |

## Часть 1 — Запуск напрямую
После запуска, сервис отдает `ok` при открытии в браузере:

![img1](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img1.png)

PID процесса на хосте: 289524
![img2](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img2.png)

## Часть 2 — Namespaces
Процесс был помещен в отдельные namespaces с помощью команды unshare:
```
patineshka@p33:~/lab1/api$ unshare --user --map-root-user --pid --fork \
  --mount --mount-proc --net --uts --ipc \
  sh -c 'hostname lab1; ip link set lo up; exec python3 server.py'
```
Однако при первом запуске команды возникла ошибка: ```unshare: write failed /proc/self/uid_map: Operation not permitted```
Она возникла из-за того, что ```unshare``` является ```unprivileged_userns```:
<img src="images/img3.png" alt="Отказ при запуске unshare" width="600">
После выполнения лабораторной было временно разрешены непривилегированные user namespace и процесс заново был помещен в namespace:
<img src="images/img4.png" alt="Запуск сервиса в namespaces" width="600">

При запуске от обычного пользователя UID 0 внутри соответствует UID 1000 снаружи:
```text
Внутри: PID 1, UID 0
Снаружи: PID 290102, UID 1000
uid_map: 0 1000 1
```
<img src="images/img5.png" alt="PID и отображение UID" width="600">

Для проверки был выполнен вход через `nsenter`. Внутри namespace:
- Сервис работает с PID 1, процессы основной Ubuntu не видны
- Имя хоста — `lab1`
- В сети есть только включённый интерфейс `lo`
- Пользователь — root, но снаружи процесс принадлежит обычному пользователю
- `/health` возвращает `ok`
<img src="images/img6.png" alt="Проверка изоляции изнутри" width="600">

## Часть 3 — Cgroups
### 3.1 Память
Был создан `/sys/fs/cgroup/lab1`, в котором заданы:
- `memory.max = 134217728` — ограничение памяти 128 МиБ.
- `memory.swap.max = 0` — запрет использования swap.
- В `cgroup.procs` записан PID процесса.
<img src="images/img7.png" alt="Настройка cgroup и лимита памяти" width="600">

После запуска `http://127.0.0.1:8080/eat?mb=256` процесс был остановлен OOM_Kill:
<img src="images/img8.png" alt="OOM: ошибка curl, счётчики memory.events и отсутствие процесса" width="600">

### 3.2 CPU
После повторного запуска API был задан cpu.max = 50000 100000. То есть использование примерно половины одного ядра (50 мс процессорного времени на период 100 мс)
Был запущен `http://127.0.0.1:8080/burn` и подтвержден throttling. 
```text
nr_throttled: 0 → 382
throttled_usec: 0 → 16161693
```
Процесс остался жив, но после исчерпания квоты ждал ее пополнения:
<img src="images/img9.png" alt="Статистика CPU до и после нагрузки" width="600">

### 3.3 Память
Был задан pids.max = 16. Для проверки использовался `stress-ng`:
```bash
stress-ng --fork 1 --fork-max 64 --timeout 10s --metrics-brief
```
При первом запуске появилась ошибка `stress-ng: not found`. Установка пакета до этого не завершилась из-за временной ошибки разрешения имени `pt.archive.ubuntu.com`. Были проверены маршрут, доступ по IP и DNS. После восстановления разрешения имен установка была повторена.

Сначала тест выполнялся в общей cgroup с ограничением памяти. В ней также вырос счетчик OOM, поэтому результат был перепроверен в отдельной группе `lab1-pids` без собственного лимита памяти.

Полученный результат:

```text
pids.max: 16
pids.events: max 59201
memory.events: oom 0, oom_kill 0
```

Лимит процессов сработал без OOM. Уже существующие процессы из-за достижения `pids.max` не убивались.
<img src="images/img10.png" alt="Проверка ограничения задач через stress-ng" width="600">

## Часть 4 — Права

## Часть 5 — Сборка Docker
## Часть 6 — Образы
## Часть 7 — gVisor
## Часть 8 - Мониторинг
## Заключение
