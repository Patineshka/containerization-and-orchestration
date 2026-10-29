import json
from urllib.parse import urlencode
from urllib.request import urlopen

queries = {
    "Отбрасывания Hubble — метки и значения":
        "hubble_drop_total",
    "TCP-флаги":
        "sum by (flag) (hubble_tcp_flags_total)",
    "Доступные DNS-метрики CoreDNS":
        'count by (__name__) ({__name__=~"coredns_dns_.*"})',
    "Доступность CoreDNS для сбора метрик":
        'up{namespace="kube-system",service=~".*dns.*"}',
}

for title, query in queries.items():
    url = "http://127.0.0.1:9092/api/v1/query?" + urlencode({"query": query})
    with urlopen(url, timeout=10) as response:
        data = json.load(response)
    print("\n=== " + title + " ===")
    print(json.dumps(data, ensure_ascii=False, indent=2))
