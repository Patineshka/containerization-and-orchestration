# Лаба 4 — SLA критического пути под перегрузкой

## Часть 0 — Batch и подготовка стенда

Продолжила работать с `shop` из третьей лабы. Критический путь здесь — оформление заказа: `api → postgres`. Batch будет создавать фоновую нагрузку, которой можно пожертвовать, если ресурсов не хватает

Использовала ту же Ubuntu Server ARM64 в UTM и профиль Minikube `lab2`. Файлы перенесла в `~/lab4`, но релиз оставила `shop`, а namespace — `lab3`. Так сохранились база и мониторинг из предыдущих лабораторных

Вместо kind/k3d из задания продолжила на Minikube с двумя нодами. Новый стек мониторинга не устанавливала

### Добавление второй ноды

Перед началом проверила ресурсы VM: 4 CPU, около 11 ГиБ RAM и 25 ГБ свободного места на диске

Добавила worker:

```bash
minikube node add -p lab2
```

С первого раза не получилось. Containerd не смог запустить CRI и написал `failed to create fsnotify watcher: too many open files`. Увеличила лимиты inotify на Ubuntu и перезапустила containerd:

```bash
sudo sysctl -w fs.inotify.max_user_instances=8192
sudo sysctl -w fs.inotify.max_user_watches=1048576

docker exec lab2-m02 systemctl restart containerd
```

Потом попробовала запустить профиль через `minikube start -p lab2 --nodes=2`. Контейнеры запустились, но worker в Kubernetes еще не появился:

<img src="images/img1.png" alt="img1" width="850">

Оказалось, что первое добавление оборвалось до настройки kubelet: не было ни `/var/lib/kubelet/config.yaml`, ни kubeconfig-файлов. Подключение завершила через `kubeadm join`

В PATH добавила каталог `/var/lib/minikube/binaries/v1.37.0`, иначе kubeadm не находил kubelet. Проверку `SystemVerification` пропустила отдельно: внутри Docker-ноды не загружался модуль ядра `configs`. Все проверки целиком не отключала

После этого дождалась готовности:

```bash
minikube -p lab2 kubectl -- wait \
  --for=condition=Ready node/lab2-m02 --timeout=3m

minikube -p lab2 kubectl -- get nodes -o wide
```

Обе ноды Ready. Ура! 🙂

<img src="images/img2.png" alt="img2" width="900">

| Нода | IP | Лимит памяти Docker |
|---|---|---:|
| `lab2` | `192.168.49.2` | 8 GiB |
| `lab2-m02` | `192.168.49.3` | 3 GiB |

При этом Kubernetes показывал на каждой ноде по 4 CPU и примерно 11 ГиБ памяти. Виртуалка от этого не получила восемь физических ядер и 22 ГиБ RAM — ресурсы у нод общие. Это дальше пригодилось при проверке давления по памяти

### Сервис batch

Для batch подготовила `main.py`, Dockerfile и `.dockerignore`. Образ — на `python:3.13-slim`, запуск от пользователя `10001:10001`, дополнительных библиотек нет

| Параметр | Что делает |
|---|---|
| `CPU_WORKERS` | Задает количество процессов с непрерывными вычислениями; при `0` вычисления отключены |
| `MEMORY_MIB` | Задает размер выделенного массива в MiB |

Программа касается каждой страницы массива и удерживает его в памяти. Сам массив не растет бесконечно, его размер меняется через параметр. CPU-процессы работают постоянно, основной процесс раз в 10 секунд пишет состояние в JSON. При SIGTERM приложение завершает дочерние процессы

Собрала образ внутри Minikube:

```bash
minikube -p lab2 image build \
  -t docker.io/library/lab4-batch:v1 ~/lab4/batch
```

Так как стоит `imagePullPolicy: Never`, перенесла образ на вторую ноду:

```bash
docker exec lab2 ctr -n k8s.io images export - \
  docker.io/library/lab4-batch:v1 \
  > ~/lab4/images/batch-image.tar

docker exec -i lab2-m02 ctr -n k8s.io images import - \
  < ~/lab4/images/batch-image.tar
```

Проверила наличие образа на обеих нодах:

<img src="images/img3.png" alt="img3" width="850">

Так же перенесла `shop-api:v2` и `shop-worker:v1`, иначе Pod мог попасть на ноду без нужного образа

В политику `allowed-images.yaml` добавила префикс `docker.io/library/lab4-batch:` для обычных и init-контейнеров. Исключать batch из политик не стала

Для первой проверки запустила одну реплику:

<img src="images/img4.png" alt="img4" width="800">

В логах один CPU-процесс и массив на 64 MiB. Pod запущен на `lab2-m02`, QoS — Burstable:

<img src="images/img5.png" alt="img5" width="900">

Начальные ресурсы batch:

```yaml
requests:
  cpu: 100m
  memory: 64Mi
limits:
  cpu: 500m
  memory: 128Mi
```

Через Prometheus проверила реальное потребление:

<img src="images/img6.png" alt="img6" width="800">

Получилось примерно **500m CPU и 87 MiB памяти**. CPU уперся в limit, а память выше 64 MiB из-за расходов Python и процессов

Здесь разобралась с requests: `100m` не ограничивает CPU сверху. Batch мог потреблять почти `500m`, потому что именно такое значение задано в limits

После проверки временный Deployment удалила. Дальше запускала batch через Helm

## Часть 1 — Механизм разнесения

В `values.yaml` добавила выбор:

```yaml
scheduling:
  mode: spread  # spread или antiAffinity
```

| Режим | Настройка |
|---|---|
| `spread` | `topologySpreadConstraints`, `maxSkew: 1`, `DoNotSchedule` |
| `antiAffinity` | Мягкая `podAntiAffinity`, вес 100 |

В обоих случаях использовала `kubernetes.io/hostname`, чтобы учитывать разные ноды

Выбрала **spread**: у меня четыре реплики API и две ноды, поэтому хочу получить 2 + 2. `maxSkew: 1` ограничивает разницу количества подходящих Pod между нодами

Мягкая anti-affinity только предпочитает размещение на разных нодах, но не гарантирует равномерность. Жесткая anti-affinity «не больше одного API Pod на ноду» оставила бы две реплики Pending

Добавила `matchLabelKeys: [pod-template-hash]`, чтобы при обновлении реплики каждой версии Deployment считались отдельно. Оба режима проверила через `helm template`

## Часть 2 — Batch в Helm-чарте

В `charts/shop/templates/` добавила `batch-deployment.yaml`. Образы, число реплик, параметры нагрузки и ресурсы вынесла в values

В обычной конфигурации `batch.replicas: 0`, чтобы нагрузка не продолжала работать между экспериментами

У Pod есть `app` и `owner`, requests и limits, разрешенный образ. Privileged и host namespaces не включены. Политики третьей лабы продолжают действовать в `lab3`, новых исключений для batch не добавляла

Для экспериментов подготовила отдельные файлы:

| Файл | Назначение |
|---|---|
| `values.yaml` | Основные настройки, spread, приоритеты и PDB |
| `values-resources.yaml` | Ресурсы API, worker и PostgreSQL, выбор ноды для БД |
| `values-scheduling.yaml` | Большие requests batch для Pending и preemption |
| `values-eviction.yaml` | Увеличение потребления памяти |
| `values-overload.yaml` | CPU-нагрузка для проверки SLA |

При обновлении сначала передавала `values-resources.yaml`, затем нужный профиль эксперимента. Последний файл переопределяет предыдущие значения

## Часть 3 — Подбор ресурсов по метрикам

### Нагрузка на оформление заказа

Для k6 создала `tests/orders.js`. Тест отправляет `POST /order` с товаром и количеством и проверяет HTTP 201

Задала следующие условия:

- 5 заказов в секунду через `constant-arrival-rate`
- Продолжительность основного прогона — 10 минут
- 5 заранее выделенных VU, максимум 20
- p95 времени ответа меньше 300 мс
- Ошибок меньше 1%, успешных проверок HTTP 201 больше 99%
- Пропущенных итераций нет

Скачала Docker-образ k6 и сохранила digest в `reports/k6-image.txt`:

<img src="images/img8.png" alt="img8" width="850">

Запускала тест из Docker в сети основной ноды. Обращалась к ClusterIP Service, чтобы запросы распределялись между API, а не шли через port-forward к одному Pod:

```bash
LAB4_API_IP=$(minikube -p lab2 kubectl -- get svc shop-api \
  -n lab3 -o jsonpath='{.spec.clusterIP}')

set -o pipefail

docker run --rm -i \
  --network container:lab2 \
  -e BASE_URL="http://${LAB4_API_IP}:8080" \
  -e DURATION=10m \
  grafana/k6:latest run - \
  < ~/lab4/tests/orders.js \
  2>&1 | tee ~/lab4/reports/orders-baseline.txt
```

Сначала короткая проверка на 30 секунд: 150 заказов, ошибок нет, p95 — 11,33 мс

Потом основной baseline: **3001 заказ, 0 ошибок, p95 — 16,06 мс**

### Запуск KRR

С установкой тоже не сразу получилось. Скачала Ubuntu-архив KRR `v1.31.1`, а бинарник оказался x86-64. У меня ARM64, поэтому собрала KRR из исходников в Docker с Python 3.12

<img src="images/img9.png" alt="img9" width="750">

Для анализа передала kubeconfig, сертификаты Minikube и адрес существующего Prometheus:

```bash
docker run --rm \
  --network host \
  -v "$HOME/.kube/config:/root/.kube/config:ro" \
  -v "$HOME/.minikube:$HOME/.minikube:ro" \
  lab4-krr:v1.31.1 simple \
  --kubeconfig /root/.kube/config \
  --context lab2 \
  --namespace lab3 \
  --prometheus-url http://127.0.0.1:9091 \
  --history_duration 1 \
  --timeframe-duration 0.25 \
  --points_required 20 \
  --width 160 \
  2>&1 | tee ~/lab4/reports/krr-baseline.txt
```

Окно анализа — один час, включая нагрузку, шаг — 15 секунд, минимум — 20 точек. Сначала пыталась указать 10 минут истории, но KRR требует хотя бы час

Получила рекомендации:

<img src="images/img10.png" alt="img10" width="1000">

| Компонент | Изначальный CPU request | KRR CPU request | Изначальная память request / limit | KRR память request / limit |
|---|---:|---:|---|---|
| API | 100m | 13m | 128Mi / 256Mi | 100Mi / 100Mi |
| Worker | 50m | 10m | 64Mi / 128Mi | 100Mi / 100Mi |
| Batch | 100m | 501m | 64Mi / 128Mi | 101Mi / 101Mi |

Это значения на контейнер. У batch в момент анализа уже не было работающих Pod, но KRR использовал данные старого Pod

CPU requests у API и worker изначально были выше измеренного потребления. Для worker, наоборот, предложено увеличить request памяти. При этом 100Mi — минимум рекомендации KRR, а не обязательно измеренный расход процесса

Стратегия Simple берет p95 CPU и не предлагает CPU limit, для памяти — максимум плюс 15%. Замер короткий, поэтому все возможные пики приложения за сутки он не покрывает

### PostgreSQL

PostgreSQL в таблицу KRR не попала: ее Pod напрямую управляется CloudNativePG. Для нее отдельно получила показатели из Prometheus за тот же час

CPU, p95 в millicores:

```promql
1000 * quantile_over_time(
  0.95,
  (sum(rate(container_cpu_usage_seconds_total{
    namespace="lab3", pod="shop-postgres-1", container="postgres"
  }[1m])))[1h:15s]
)
```

Пиковая память с запасом 15%, в MiB:

```promql
1.15 * max_over_time(
  (sum(container_memory_working_set_bytes{
    namespace="lab3", pod="shop-postgres-1", container="postgres"
  }))[1h:15s]
) / 1024 / 1024
```

Получила **46,55m CPU и 132,59 MiB памяти**. Это мой расчет по метрикам, а не результат KRR для PostgreSQL

### Изменение ресурсов

По результатам выбрала значения с дополнительным запасом:

| Компонент | CPU request / limit | Memory request / limit |
|---|---|---|
| API | 50m / 50m | 128Mi / 128Mi |
| Worker | 20m / без CPU limit | 128Mi / 128Mi |
| PostgreSQL | 100m / 100m | 256Mi / 256Mi |

Записала их в `values-resources.yaml` и применила через Helm. Значения выбраны по измерениям, но не скопированы из KRR дословно. Для API и PostgreSQL вернула CPU limits, чтобы получить Guaranteed в следующей части

```bash
helm upgrade shop ~/lab4/charts/shop \
  --namespace lab3 \
  --kube-context lab2 \
  -f ~/lab4/charts/shop/values-resources.yaml \
  --wait --timeout 5m
```

И тут PostgreSQL ушла в CrashLoopBackOff, а Helm ждал готовности и завершился по таймауту

В логах нашла:

```text
stat /var/lib/postgresql/data/pgdata: no such file or directory
```

Pod переехал на worker, а данные остались на `lab2`. Стандартный hostPath-том Minikube не переносится на другую ноду вместе с Pod

Проверила исходную директорию `/tmp/hostpath-provisioner/lab3/shop-postgres-1` на основной ноде — файл `pgdata/PG_VERSION` на месте. Вернула Pod на `lab2`, а затем закрепила выбор в чарте:

```yaml
postgresNodeSelector:
  kubernetes.io/hostname: lab2
```

В шаблоне PostgreSQL это значение передается в `spec.affinity.nodeSelector`. После пересоздания Pod кластер снова healthy, PVC не удаляла

После изменения ресурсов повторила тот же десятиминутный k6-тест. Результат: **3000 заказов, ошибок нет, p95 — 117,96 мс**. Порог 300 мс выполнен, но задержка выше baseline. Причину отдельно по throttling не проверяла

## Часть 4 — Разнесение API

Применила выбранный spread и проверила реальное размещение:

```bash
minikube -p lab2 kubectl -- get pods \
  -n lab3 -l app=shop-api -o wide
```

Получилось две реплики на `lab2` и две на `lab2-m02`:

<img src="images/img7.png" alt="img7" width="850">

Так API меньше зависит от одной ноды. Но обе ноды работают внутри одной VM, поэтому ее выключение они не переживут. У PostgreSQL одна реплика с локальным томом — разнесение API само по себе не делает весь путь заказа отказоустойчивым

Отдельное отключение ноды в этой проверке не проводила

## Часть 5 — Приоритеты и гарантии

### QoS

После обновления проверила фактический QoS Pod:

<img src="images/img11.png" alt="img11" width="850">

API и PostgreSQL получили Guaranteed, worker — Burstable

Для Guaranteed у каждого обычного и init-контейнера должны быть заданы CPU и memory requests/limits, причем request равен limit для каждого ресурса. У PostgreSQL это касается и `bootstrap-controller`

У worker нет CPU limit, а у batch requests ниже limits — они Burstable

### PriorityClass

Добавила `priorityclasses.yaml`, значения приоритетов — в `values.yaml`:

| Класс | Значение | Preemption policy | Для кого |
|---|---:|---|---|
| `shop-critical` | 100000 | `PreemptLowerPriority` | API и PostgreSQL |
| `shop-batch` | -1000 | `Never` | Batch |

Worker остался с приоритетом 0. `Never` у batch запрещает ему самому вытеснять другие Pod, но не защищает его от вытеснения

### PodDisruptionBudget

Для API создала `api-pdb.yaml` с `minAvailable: 3`. У четырех готовых реплик разрешено одно добровольное выселение

Для PostgreSQL оставила PDB, которым управляет CloudNativePG. Включение вынесла в values и передала в `spec.enablePDB`. Второй PDB с пересекающимся selector не создавала

Проверила классы и бюджеты:

<img src="images/img12.png" alt="img12" width="950">

На этом снимке обновление еще шло: видны старые Pod API и PostgreSQL с приоритетом 0. В Cluster уже было `shop-critical`, но существующий Pod БД сохранил старое значение. После пересоздания проверка показала:

```text
NAME              PRIORITY   CLASS           QOS          NODE
shop-postgres-1   100000     shop-critical   Guaranteed   lab2
```

| PDB | Min available | Allowed disruptions |
|---|---:|---:|
| `shop-api` | 3 | 1 |
| `shop-postgres-primary` | 1 | 0 |

PDB ограничивает добровольные выселения через Eviction API. Он не защищает от падения ноды и memory eviction, а при preemption учитывается без абсолютной гарантии. Rolling update Deployment регулируется отдельно через `maxUnavailable` и `maxSurge`

При выборе жертв preemption scheduler учитывает приоритет, а не QoS. При memory eviction kubelet учитывает превышение requests, приоритет и величину превышения. Поэтому Guaranteed — не абсолютная защита, но batch в нашем сценарии менее защищен

## Часть 6 — Pending и preemption

### Нехватка CPU

В `values-scheduling.yaml` подняла batch до шести реплик. У каждой CPU request 2, limit 2500m, память request 64Mi, limit 128Mi

При этом вычисления отключила: `cpuWorkers: 0`, память — 16 MiB. Так можно увидеть разницу между requests и реальной нагрузкой

```bash
helm upgrade shop ~/lab4/charts/shop \
  --namespace lab3 \
  --kube-context lab2 \
  -f ~/lab4/charts/shop/values-resources.yaml \
  -f ~/lab4/charts/shop/values-scheduling.yaml
```

Запускала без `--wait`, потому что часть Pod должна остаться Pending

Одна реплика запустилась, пять не поместились:

<img src="images/img13.png" alt="img13" width="1000">

В событиях:

```text
0/2 nodes are available: 2 Insufficient cpu.
preemption: not eligible due to preemptionPolicy=Never.
```

Шесть реплик запросили 12 CPU, тогда как Kubernetes видит суммарно 8 CPU, часть которых уже занята requests других приложений. Даже почти не работающий batch занимает место при планировании: scheduler считает requests, а не текущую загрузку

### Вытеснение batch

Для проверки создала отдельный Pod `preemption-api` из образа API. Задала `shop-critical`, CPU request/limit 2, memory request/limit 128Mi и nodeSelector на `lab2-m02`, где работал batch

У него отдельная метка `app: preemption-api`, поэтому основной Service не направляет к нему заказы. Это тестовый Pod из файла, а не новая реплика рабочего Deployment

Включила наблюдение и применила файл:

```bash
minikube -p lab2 kubectl -- get pods -n lab3 --watch

minikube -p lab2 kubectl -- apply \
  -f ~/lab4/tests/preemption-api.yaml
```

Batch начал завершаться, а тестовый API перешел из Pending в Running:

<img src="images/img15.png" alt="img15" width="700">

В событиях подтвердилось вытеснение:

```text
Preempted  pod/shop-batch-f9c85dbf9-bqvqs
Preempted by pod ... on node lab2-m02

FailedScheduling  pod/preemption-api
found a potential placement for pod on node lab2-m02, preempting 1 victims

Scheduled  pod/preemption-api
Successfully assigned lab3/preemption-api to lab2-m02
```

API занял освободившееся место и стал `1/1 Running`. ReplicaSet создал замену batch, но она тоже осталась Pending:

<img src="images/img14.png" alt="img14" width="950">

Сохранила события в `reports/preemption-events.txt`, затем остановила batch и удалила тестовый Pod

## Часть 7 — Давление по памяти

### Настройка kubelet

Перед нагрузкой проверила, какую память видит kubelet. У worker Docker-лимит 3 GiB, но stats summary показывал около 10843 MiB доступной памяти. В `evictionHard` вообще не было порога памяти

Если просто выделять все больше памяти, можно получить OOM всей Docker-ноды раньше eviction. Поэтому для проверки временно подняла soft-порог kubelet: примерно на 192 MiB ниже свежего значения доступной памяти

В этом запуске получилось:

```yaml
evictionSoft:
  memory.available: "10670Mi"
evictionSoftGracePeriod:
  memory.available: "10s"
evictionMaxPodGracePeriod: 15
```

Это искусственно повышенный лабораторный порог, а не реальное исчерпание памяти всей VM. Исходный конфиг сохранила, настройку меняла только на worker, вне Helm

Перезапустила kubelet. Он работает, нода Ready, давления пока нет:

<img src="images/img16.png" alt="img16" width="850">

### Запуск нагрузки

В `values-eviction.yaml` задала одну batch-реплику на `lab2-m02`, отключила вычисления и увеличила массив до 256 MiB. Memory request — 64Mi, limit — 512Mi, CPU request/limit — 100m/500m

Собственный memory limit выше потребления, чтобы проверить eviction, а не OOM по лимиту контейнера

Применила профиль через Helm:

<img src="images/img17.png" alt="img17" width="850">

Первый вывод еще показывает Running, а в наблюдении нода уже перешла в MemoryPressure:

<img src="images/img18.png" alt="img18" width="900">

Затем получила событие:

```text
Warning Evicted pod/shop-batch-6d7b695994-s49fd
The node was low on resource: memory.
Threshold quantity: 10670Mi, available: 10838604Ki.
Container batch was using 274840Ki, request is 64Mi,
has larger consumption of memory.
```

Batch использовал около 268 MiB — больше request, но меньше limit. Kubelet выселил именно его, API и PostgreSQL продолжали работать. Новый batch не смог разместиться из-за taint worker

| Причина | Что произошло |
|---|---|
| `Evicted` | Kubelet завершил Pod из-за давления ресурса на ноде |
| `OOMKilled` по собственному лимиту | Контейнер превысил свой memory limit и его процесс был убит |

У меня получился первый случай. События сохранила в `reports/eviction-events.txt`

После проверки остановила batch и восстановила исходный конфиг:

```bash
docker cp ~/lab4/setup/backups/kubelet-worker-original.yaml \
  lab2-m02:/var/lib/kubelet/config.yaml

docker exec lab2-m02 systemctl restart kubelet
```

Нода снова Ready, MemoryPressure=False, сервисы работают:

<img src="images/img19.png" alt="img19" width="850">

Старый batch остался в Error — это уже завершенный Pod после eviction, а не работающая нагрузка

## Часть 8 — SLA под перегрузкой

Для проверки задала SLA теста: **при 5 заказах/с p95 времени создания заказа меньше 300 мс, ошибок меньше 1%, пропущенных итераций нет**

В `values-overload.yaml` запустила четыре batch-реплики на worker. У каждой один CPU-процесс, массив 64 MiB, CPU request 100m и limit 1 CPU, память request 64Mi и limit 128Mi

Все четыре новые реплики запустились:

<img src="images/img20.png" alt="img20" width="950">

В Prometheus проверила суммарное потребление CPU:

```promql
sum(rate(container_cpu_usage_seconds_total{
  namespace="lab3", pod=~"shop-batch-.*", container="batch"
}[1m]))
```

Получила **3,472 CPU** во время теста — существенная нагрузка для VM с четырьмя ядрами. Это отдельный замер, а не среднее за все десять минут

Одновременно запустила тот же `orders.js` на 10 минут:

<img src="images/img21.png" alt="img21" width="750">

Все пороги выполнены 🙂

| Показатель | Исходные ресурсы | После изменения ресурсов | Под CPU-нагрузкой |
|---|---:|---:|---:|
| Длительность | 10 минут | 10 минут | 10 минут |
| Заказы с HTTP 201 | 3001 | 3000 | 3001 |
| Ошибки | 0% | 0% | 0% |
| Среднее время | 12,30 мс | 83,55 мс | 28,32 мс |
| p95 | 16,06 мс | 117,96 мс | 83,95 мс |
| Максимум | 111,14 мс | 955,73 мс | 392,44 мс |
| Пропущенные итерации | 0 | 0 | 0 |

Под нагрузкой p95 остался ниже 300 мс. Максимальный запрос занял 392,44 мс, но условие задано для p95, а не для каждого запроса

Результат под нагрузкой оказался лучше предыдущего прогона с измененными ресурсами. Отсюда не делаю вывод, что batch ускоряет API: это отдельные запуски, состояние VM и фоновые процессы между ними не одинаковые

SLA проверила отдельно под CPU-нагрузкой. Непрерывный k6 одновременно с preemption и memory eviction не записывала, поэтому в эти моменты SLA отдельно не подтвержден. На скриншоте — итог k6; временные графики задержки и ошибок и новый дашборд этого прогона не сохраняла

После теста остановила batch:

```bash
helm upgrade shop ~/lab4/charts/shop \
  --namespace lab3 \
  --kube-context lab2 \
  -f ~/lab4/charts/shop/values-resources.yaml \
  --set batch.replicas=0 \
  --wait --timeout 5m
```

## Часть 9 — Мониторинг

ServiceMonitor для API и worker и PrometheusRule уже находятся в чарте shop. Сохранила метку `release: monitoring`, чтобы их выбирал существующий Prometheus

Использовала три алерта:

| Алерт | Условие | Почему важно и что делать |
|---|---|---|
| `ShopAPIDown` | Все API scrape-цели имеют up=0 или цели отсутствуют; `for: 1m` | Проверить Pod, readiness, Service и доступность API |
| `ShopHighErrorRate` | Доля HTTP 5xx выше 20% в окне 1m; `for: 1m` | Пользователи получают ошибки. Проверить API, PostgreSQL и последние изменения |
| `ShopWorkerStalled` | Нет свежего успешного опроса БД доступными worker больше 60 секунд или метрики отсутствуют; `for: 1m` | Может остановиться обработка заказов. Проверить worker и подключение к БД |

Все имеют `severity: critical`. `ShopAPIDown` проверяет сбор метрик, а не весь пользовательский сценарий. У worker даже успешный опрос пустой очереди обновляет временную метку

Проверила правила — ошибок вычисления нет:

<img src="images/img22.png" alt="img22" width="850">

На этом снимке уже inactive. Хотя файл называется `alerts-firing.txt`, это не снимок самого срабатывания

### Проверка алерта

Для `ShopHighErrorRate` создала `tests/trigger-error-alert.js`: 10 запросов/с к `/fail` в течение трех минут. В этом тесте HTTP 500 намеренный, его же проверяла в check

Alertmanager отправил уведомление прежнему receiver `lab2-webhook`. Название осталось от второй лабы, но он принимает и алерты shop

Для вывода переиспользовала форматтер из третьей лабы:

```bash
python3 ~/lab4/tests/format-alerts.py \
  < ~/lab4/reports/alert-delivery.txt | \
  tee ~/lab4/reports/alert-delivery-pretty.txt
```

Подтвердила firing и resolved:

<img src="images/img23.png" alt="img23" width="750">

| Событие | Время UTC |
|---|---|
| Начало | `2026-10-25T23:28:41.742Z` |
| Завершение | `2026-10-25T23:31:11.742Z` |

Получилась цепочка Prometheus → Alertmanager → webhook receiver. Остальные два правила загружены, но отдельно их срабатывание в этой лабе не проверяла

## Что получилось

- Две ноды Minikube и образы приложения на обеих
- Batch с настраиваемыми CPU-процессами и объемом памяти
- Переключатель spread/anti-affinity в values, размещение API 2 + 2
- Рекомендации KRR для API и worker, отдельный расчет PostgreSQL по метрикам
- Guaranteed и высокий приоритет у API/PostgreSQL, Burstable и низкий приоритет у batch
- PDB для API и PostgreSQL
- Pending по requests и вытеснение batch высокоприоритетным тестовым API Pod
- MemoryPressure и eviction batch, восстановление kubelet после проверки
- 3001 успешный заказ под CPU-нагрузкой, p95 83,95 мс при пороге 300 мс
- Три алерта и доставка firing/resolved одного из них

В конце batch выключен, тестовый Pod удален, конфигурация kubelet восстановлена. У API четыре реплики, worker — две, PostgreSQL — одна, закрепленная на `lab2`

В работе есть отличия от задания: Minikube вместо kind/k3d, отдельный расчет PostgreSQL вместо рекомендации KRR, выбранные ресурсы с дополнительным запасом. Preemption проверяла отдельным тестовым Pod, eviction — с повышенным порогом. Совмещенный SLA-тест для preemption/eviction и временные графики еще не сделаны

## Топ ошибок

Мое любимое 🥰

1. **Worker есть в Minikube, но нет в Kubernetes.** Контейнер создался, а настройка kubelet оборвалась. Сообщение «Готово» оказалось не последней проверкой — дальше смотрела `kubectl get nodes`

2. **Ubuntu не означает ARM64.** Скачала KRR для Ubuntu, а внутри x86-64. Пришлось собирать из исходников в Docker

3. **Helm завис, а база потеряла свою директорию.** Данные не пропали, просто Pod переехал на другую ноду. HostPath за ним не переехал. Вернула PostgreSQL на `lab2` и закрепила это в чарте

4. **Сделала резервную копию и сломала lint.** Файл `.yaml.bak` внутри `templates/` Helm тоже решил проверить. Перенесла backup за пределы чарта

5. **Свободный CPU не помог Pod запуститься.** Batch почти ничего не делал, но запросил по два ядра. Scheduler посчитал requests и оставил остальные реплики Pending — тут как раз все работает правильно)

6. **MemoryPressure и OOM — не одно и то же.** У worker Docker-лимит 3 GiB, а kubelet видел память всей VM. Вместо заполнения памяти до падения ноды настроила лабораторный soft-порог и получила именно Evicted

7. **Посмотрела слишком рано.** В выводе Pod еще Running, а чуть позже в событиях уже Evicted. Пришлось сравнивать время и смотреть не только одну строку статуса

8. **Форматтер уже был.** Сначала получила длинный JSON алерта и собралась писать новый скрипт. Потом вспомнила про третью лабу и просто переиспользовала старый :)

В этой лабе наконец получилось увидеть разницу между «Pod не помещается», «Pod вытеснили ради другого» и «Pod выселили из-за памяти». Симптом похожий — batch не работает, а причины и действия совсем разные ;)
