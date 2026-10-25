import json
import sys

for line in sys.stdin:
    try:
        notification = json.loads(line)
    except ValueError:
        continue

    for alert in notification.get("alerts", []):
        labels = alert.get("labels", {})
        if not labels.get("alertname", "").startswith("Shop"):
            continue

        result = {
            "Алерт": labels.get("alertname"),
            "Статус": alert.get("status"),
            "Важность": labels.get("severity"),
            "Namespace": labels.get("namespace"),
            "Сервис": labels.get("service"),
            "Описание": alert.get("annotations", {}).get("summary"),
            "Начало (UTC)": alert.get("startsAt"),
            "Получатель": notification.get("receiver"),
        }

        if alert.get("status") == "resolved":
            result["Завершение (UTC)"] = alert.get("endsAt")

        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()