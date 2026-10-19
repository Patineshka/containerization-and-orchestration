# Лаба 2 - Мониторинг сервиса: метрики, логи, трейсы
## Часть 0 — Свой сервис + настройка k8s

### Подготовка кластера
Для подготовки кластера и определения его размера необходимо понять, какие доступные ресурсы имеются на ВМ (у меня это Ubuntu Server ARM64 в UTM):

<img src="images/img1.png" alt="img1" width="600">

На этом этапе обнаружились две проблемы: 
- Виртуалка снова живет в прошлом (мой затык в прошлой лабе)
- У VM 7,2 ГиБ RAM и 17 ГБ свободного места - в целом окей, но на всякий случай добавлю

Было сделано несколько простых махинаций:
- для исправления времени
```
patineshka@p33:~$ sudo timedatectl set-ntp false
patineshka@p33:~$ sudo hwclock --hctosys --utc
patineshka@p33:~$ sudo timedatectl set-ntp true
patineshka@p33:~$ date -u
пн 19 окт 2026 18:27:18 UTC
```
- для увеличения памяти

<img src="images/img2.png" alt="img2" width="600">

Осталось установить необходимые инструменты: 
1. Minikube - для создания локального кластера 
```
curl -fLO https://github.com/kubernetes/minikube/releases/latest/download/minikube-linux-arm64
sudo install -m 0755 minikube-linux-arm64 /usr/local/bin/minikube
```
2. Helm - для разворачивания сервиса и компонентов мониторинга
```
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4
```

Проверка установки: 

<img src="images/img3.png" alt="img3" width="600">

### Разворачивание сервиса 

Для сервиса были подготовлены файлы server.py, requirements.txt, Dockerfile и собран образ в minikube:
```
minikube -p lab2 image build -t lab2-api:v1 ~/lab2/api

patineshka@p33:~/lab2/setup$ minikube -p lab2 image ls | grep lab2-api
docker.io/library/lab2-api:v1
```

Далее был создан Helm Chart - файлы для запуска API в k8s:
- Chart.yaml - описывает пакет: название, версию chart и версию приложения
- values.yaml	- хранит изменяемые настройки, такие как имя образа, тег и ресурсы
- templates/deployment.yaml	- описывает запуск и поддержание одного экземпляра API
- templates/service.yaml - создает постоянный сетевой адрес для обращения к API внутри кластера

Deployment создаёт под с контейнером `lab2-api:v1` и поддерживает нужное число экземпляров (в моем случае один)
Service дает постоянное имя `lab2-api` и направляет трафик к подходящим подам по метке `app: lab2-api`

Для запуска проверяем chart на ошибки и затем устанавливаем:

<img src="images/img4.png" alt="img4" width="600">

Ура! API развернут) Теперь проверим все endpoint:

<img src="images/img5.png" alt="img5" width="600">

Также описание эндпоинтов:
 | Эндпоинт | Описание |
|---|---|
| `/health` | Возвращает `200 OK` и `ok` - для проверки работоспособности сервиса и Kubernetes-проб |
| `/fail` | Намеренно возвращает `500 Internal Server Error` - для проверки счетчик ошибок, логи, ошибочный спан и алерты |
| `/slow` | Выполняет операцию с задержкой 2 секунды - для проверки графика времени ответа и вложенный спан `slow-op` |
| `/load` | Делает 20 запросов к собственному `/health` - для проверки роста интенсивности запросов RPS |
| `/metrics` | Отдает метрики в формате Prometheus - количество запросов, ошибок и гистограмму времени ответа |

Observability (почти) настроена, остался мониторинг ;)

## Часть 0 — Метрики (Prometheus + Grafana)
