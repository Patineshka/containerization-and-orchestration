import json
import subprocess
from pathlib import Path

root = Path.home() / "lab5"


def pod(app):
    return {"podSelector": {"matchLabels": {"app": app}}}


def namespace(name, labels):
    return {
        "namespaceSelector": {
            "matchLabels": {"kubernetes.io/metadata.name": name}
        },
        "podSelector": {"matchLabels": labels},
    }


def ports(*numbers):
    return [{"protocol": "TCP", "port": n} for n in numbers]


def rule(direction, peers, numbers):
    return {direction: peers, "ports": ports(*numbers)}


def policy(selector, **directions):
    return {
        "podSelector": selector,
        "policyTypes": [key.capitalize() for key in directions],
        **directions,
    }


prometheus = namespace(
    "monitoring", {"app.kubernetes.io/name": "prometheus"}
)
jaeger = namespace(
    "monitoring", {"app.kubernetes.io/instance": "jaeger"}
)
operator = namespace(
    "cnpg-system", {"app.kubernetes.io/name": "cloudnative-pg"}
)
dns = namespace("kube-system", {"k8s-app": "kube-dns"})

app_selector = lambda name: {"matchLabels": {"app": name}}

policies = {
    "default-deny": policy({}, ingress=[], egress=[]),

    "allow-dns": policy(
        {"matchExpressions": [{
            "key": "app",
            "operator": "In",
            "values": [
                "shop-api", "shop-worker", "shop-postgres", "shop-client"
            ],
        }]},
        egress=[{
            "to": [dns],
            "ports": [
                {"protocol": "UDP", "port": 53},
                {"protocol": "TCP", "port": 53},
            ],
        }],
    ),

    "allow-api-ingress": policy(
        app_selector("shop-api"),
        ingress=[rule(
            "from",
            [
                pod("shop-client"),
                prometheus,
                {"ipBlock": {"cidr": "192.168.49.1/32"}},
            ],
            [8080],
        )],
    ),

    "allow-worker-metrics": policy(
        app_selector("shop-worker"),
        ingress=[rule("from", [prometheus], [8080])],
    ),

    "allow-postgres-ingress": policy(
        app_selector("shop-postgres"),
        ingress=[
            rule("from", [pod("shop-api"), pod("shop-worker")], [5432]),
            rule("from", [operator], [8000]),
        ],
    ),

    "allow-api-egress": policy(
        app_selector("shop-api"),
        egress=[
            rule("to", [pod("shop-postgres")], [5432]),
            rule("to", [jaeger], [4317]),
        ],
    ),

    "allow-worker-egress": policy(
        app_selector("shop-worker"),
        egress=[
            rule("to", [pod("shop-postgres")], [5432]),
            rule("to", [jaeger], [4317]),
        ],
    ),

    "allow-client-egress": policy(
        app_selector("shop-client"),
        egress=[rule("to", [pod("shop-api")], [8080])],
    ),
}

kube_service = subprocess.check_output([
    "minikube", "-p", "lab2", "kubectl", "--",
    "get", "svc", "kubernetes", "-n", "default",
    "-o", "jsonpath={.spec.clusterIP}",
], text=True).strip()


def cilium_ports(*numbers):
    return [{"ports": [
        {"port": str(n), "protocol": "TCP"} for n in numbers
    ]}]


cilium_policies = {
    "postgres-to-apiserver": {
        "endpointSelector": app_selector("shop-postgres"),
        "egress": [
            {
                "toEntities": ["kube-apiserver"],
                "toPorts": cilium_ports(443, 8443),
            },
            {
                "toCIDR": [kube_service + "/32"],
                "toPorts": cilium_ports(443),
            },
        ],
    },

    "client-to-nodeport": {
        "endpointSelector": app_selector("shop-client"),
        "egress": [{
            "toEntities": ["host", "remote-node"],
            "toPorts": cilium_ports(30080),
        }],
    },

    "nodeport-to-api": {
        "endpointSelector": app_selector("shop-api"),
        "ingress": [{
            "fromEntities": ["remote-node"],
            "toPorts": cilium_ports(8080),
        }],
    },
}


probe_sources = [
    {"ipBlock": {"cidr": "10.244.0.1/32"}},
    {"ipBlock": {"cidr": "10.244.1.1/32"}},
]

policies["allow-node-health"] = policy(
    {"matchExpressions": [{
        "key": "app",
        "operator": "In",
        "values": ["shop-api", "shop-worker"],
    }]},
    ingress=[rule("from", probe_sources, [8080])],
)

policies["allow-node-postgres-health"] = policy(
    app_selector("shop-postgres"),
    ingress=[rule("from", probe_sources, [8000])],
)

values = {
    "networkPolicy": {
        "enabled": True,
        "policies": policies,
        "ciliumPolicies": cilium_policies,
    }
}

output = root / "charts/shop/values-networkpolicy.yaml"
output.write_text(json.dumps(values, indent=2) + "\n")
print("Создан:", output)
