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
Процесс был помещен в namespace с помощью команды unshare:
```
patineshka@p33:~/lab1/api$ unshare --user --map-root-user --pid --fork \
  --mount --mount-proc --net --uts --ipc \
  sh -c 'hostname lab1; ip link set lo up; exec python3 server.py'
```
Однако при первом запуске команды возникла ошибка: ```unshare: write failed /proc/self/uid_map: Operation not permitted```
Она возникла из-за того, что ```unshare``` является ```unprivileged_userns```:
![img3](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img3.png)
После выполнения лабораторной было временно разрешены непривилегированные user namespace и процесс заново был помещен в namespace:
![img4](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img4.png)

![img5](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img5.png)
Внутри namespace:
- Сервис с PID 1
- Имя хоста: и своя сеть:
- root внутри
![img6](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img6.png)

## Часть 3 — Cgroups
### 3.1 Память
Был создан `/sys/fs/cgroup/lab1`, в котором заданы:
- Ограничение памяти memory.max = 134217728 — 128 МиБ 
- memory.swap.max = 0
- cgroup.procs = PID процесса
![img7](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img7.png)

После запуска `http://127.0.0.1:8080/eat?mb=256` процесс был остановлен OOM_Kill:
![img8](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img8.png)

### 3.2 CPU
После повторного запуска API был задан cpu.max = 50000 100000. То есть использование примерно половины одного ядра (50 мс процессорного времени на период 100 мс)
Был запущен `http://127.0.0.1:8080/burn` и подтвержден throttling. Процесс остался жив, но после исчерпания квоты ждал ее пополнения:
![img9](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img9.png)

### 3.3 Память
Был задан pids.max = 16 

## Часть 4 — Права

## Часть 5 — Сборка Docker
## Часть 6 — Образы
## Часть 7 — gVisor
## Часть 8 - Мониторинг
## Заключение
