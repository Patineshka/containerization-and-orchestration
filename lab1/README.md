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

[img1](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img1.png)

PID процесса на хосте: 289524
[img2](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img2.png)

## Часть 2 — Namespaces
Процесс был помещен в namespace с помощью команды unshare:
```
patineshka@p33:~/lab1/api$ unshare --user --map-root-user --pid --fork \
  --mount --mount-proc --net --uts --ipc \
  sh -c 'hostname lab1; ip link set lo up; exec python3 server.py'
```
Однако при первом запуске команды возникла ошибка: ```unshare: write failed /proc/self/uid_map: Operation not permitted```
Она возникла из-за того, что ```unshare``` является ```unprivileged_userns```:
[img3](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img3.png)
После выполнения лабораторной было временно разрешены непривилегированные user namespace и процесс заново был помещен в namespace:
[img4](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img4.png)

[img5](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img5.png)
Внутри namespace:
- Сервис с PID 1
- Имя хоста: и своя сеть:
- root внутри
[img6](https://github.com/Patineshka/containerization-and-orchestration/blob/main/lab1/images/img6.png)

## Часть 3 — Cgroups
## Часть 4 — Права
## Часть 5 — Сборка Docker
## Часть 6 — Образы
## Часть 7 — gVisor
## Часть 8 - Мониторинг
## Заключение
