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
patineshka@p33:~$ 
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

Deployment создает под с контейнером `lab2-api:v1` и поддерживает нужное число экземпляров (в моем случае один)
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

Observability (почти) настроен, остался мониторинг ;)

## Часть 1 — Метрики (Prometheus + Grafana)
### Prometheus
Для настройки Prometheus был добавлен Helm-репозиторий:
```
patineshka@p33:~/lab2/setup$ helm repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts

helm repo update
mkdir -p ~/lab2/monitoring
"prometheus-community" has been added to your repositories
Hang tight while we grab the latest from your chart repositories...
...Successfully got an update from the "prometheus-community" chart repository
Update Complete. ⎈Happy Helming!⎈
```

Также были созданы следующие файлы:
- monitoring/values.yaml - для сохранения метрик и настройки графаны в постоянный томах. Также отключила стандартный набор правил и сбор части метрик, которые сейчас не нужны для мониторинга
- templates/servicemonitor.yaml - в нем описано, какой Service найти, какой порт и путь опрашивать для сбора метрик Prometheus оператором

Затем был установлен стек:
```
helm upgrade --install monitoring \
  prometheus-community/kube-prometheus-stack \
  --version 92.10.1 \
  --namespace monitoring --create-namespace \
  --kube-context lab2 \
  -f ~/lab2/monitoring/values.yaml \
  --wait --timeout 10m
```
Работает :)

<img src="images/img6.png" alt="img6" width="600">

Также была обновлена установка API:

<img src="images/img7.png" alt="img7" width="600">

Запустила Prometheus и теперь он собирает метрики: 

<img src="images/img8.png" alt="img8" width="600">

### Grafana
В графане были построены три графика:
- Интенсивность запросов, RPS - `sum(rate(api_requests_total{namespace="lab2", service="lab2-api"}[1m]))`
- Доля ошибок 5xx, % - `100 * (sum(rate(api_requests_total{namespace="lab2", service="lab2-api", status=~"5.."}[1m])) or vector(0)) / clamp_min(sum(rate(api_requests_total{
namespace="lab2", service="lab2-api"}[1m])),0.000001)`
- p95 времени ответа - `histogram_quantile(0.95, sum by (le) (rate(api_request_duration_seconds_bucket{namespace="lab2", service="lab2-api"}[1m])))`

С помощью эндпоинта /load были инициировано 20 запросов к /health и график "Интенсивность запросов" вырос до 5 req/s. 
Вызов 20 раз эндпоинта /fail увеличил долю ошибок на соответствующем графике до ~80% 
Эндпоинт /slow позволил проверить график "p95 времени ответа"

<img src="images/img9.png" alt="img9" width="600">

