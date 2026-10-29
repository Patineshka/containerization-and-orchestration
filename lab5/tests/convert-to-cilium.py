import copy
import json
from pathlib import Path

path = Path.home() / "lab5/charts/shop/values-networkpolicy.yaml"
data = json.loads(path.read_text())
config = data["networkPolicy"]
policies = config.get("policies")

if not policies:
    raise SystemExit("Обычных NetworkPolicy для преобразования нет")

backup = path.with_name("values-networkpolicy-before-cilium.json")
if not backup.exists():
    backup.write_text(path.read_text())

def selector(source):
    result = copy.deepcopy(source)
    result["matchLabels"] = {
        "k8s:" + key: value
        for key, value in result.get("matchLabels", {}).items()
    }
    for expression in result.get("matchExpressions", []):
        expression["key"] = "k8s:" + expression["key"]
    return result

converted = copy.deepcopy(config.get("ciliumPolicies", {}))

for name, policy in policies.items():
    spec = {
        "endpointSelector": selector(policy["podSelector"]),
        "enableDefaultDeny": {
            direction.lower(): True
            for direction in policy["policyTypes"]
        },
    }

    for direction, peer_key, endpoint_key, cidr_key in (
        ("ingress", "from", "fromEndpoints", "fromCIDRSet"),
        ("egress", "to", "toEndpoints", "toCIDRSet"),
    ):
        if direction not in policy:
            continue

        spec[direction] = []
        for rule in policy[direction]:
            for peer in rule[peer_key]:
                item = {}
                if "ipBlock" in peer:
                    item[cidr_key] = [copy.deepcopy(peer["ipBlock"])]
                else:
                    endpoint = selector(peer.get("podSelector", {}))
                    if "namespaceSelector" in peer:
                        ns = peer["namespaceSelector"]
                        labels = ns.get("matchLabels", {})
                        assert not ns.get("matchExpressions"), ns
                        assert set(labels) == {
                            "kubernetes.io/metadata.name"
                        }, ns
                        endpoint["matchLabels"][
                            "k8s:io.kubernetes.pod.namespace"
                        ] = labels["kubernetes.io/metadata.name"]
                    item[endpoint_key] = [endpoint]

                if rule.get("ports"):
                    assert all(
                        "endPort" not in port for port in rule["ports"]
                    )
                    item["toPorts"] = [{
                        "ports": [
                            {
                                "port": str(port["port"]),
                                "protocol": port.get("protocol", "TCP"),
                            }
                            for port in rule["ports"]
                        ]
                    }]
                spec[direction].append(item)

    converted["converted-" + name] = spec

config["policies"] = None
config["ciliumPolicies"] = converted
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print("Правила преобразованы. Резервная копия:", backup)
