import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

root = Path.home() / "lab5"


def read_jsonl(path):
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def timestamp(row):
    return datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))


requests = [
    row for row in read_jsonl(root / "reports/continuity-chaos.jsonl")
    if not row.get("summary")
]
events = read_jsonl(root / "reports/chaos-events.jsonl")
if not requests:
    raise SystemExit("Нет данных запросов")

start = min(map(timestamp, requests))
finish = max(map(timestamp, requests))
deletions = [
    row for row in events
    if row.get("event") == "delete"
    and start <= timestamp(row) <= finish
]
if not deletions:
    raise SystemExit("Внутри окна запросов нет подтвержденных удалений Pod")

fig, axes = plt.subplots(
    3, 1, figsize=(14, 9), sharex=True,
    gridspec_kw={"height_ratios": [2, 1, 1]},
)

colors = {"dns-service": "#2563eb", "nodeport": "#16a34a"}
for target, color in colors.items():
    rows = sorted(
        (r for r in requests if r["target"] == target),
        key=timestamp,
    )
    axes[0].plot(
        [timestamp(r) for r in rows],
        [r["latency_ms"] for r in rows],
        label=target, color=color, linewidth=1,
    )

failed = 0
cumulative = []
ordered = sorted(requests, key=timestamp)
for row in ordered:
    failed += int(not row["success"])
    cumulative.append(failed)

axes[1].plot(
    [timestamp(r) for r in ordered], cumulative,
    color="#dc2626", linewidth=2, label="Failed requests",
)
axes[1].set_ylim(-0.1, max(1, failed + 0.5))

for name, y, color in [
    ("shop-api-", 1, "#9333ea"),
    ("shop-worker-", 0, "#ea580c"),
]:
    rows = [e for e in deletions if e["pod"].startswith(name)]
    axes[2].scatter(
        [timestamp(r) for r in rows],
        [y] * len(rows),
        marker="x", s=45, color=color,
        label="API deleted" if y else "Worker deleted",
    )

axes[0].set_ylabel("Latency, ms")
axes[1].set_ylabel("Failed, cumulative")
axes[2].set_yticks([0, 1], ["worker", "api"])
axes[2].set_ylim(-0.5, 1.5)
axes[2].set_xlabel("Time, UTC")
axes[2].xaxis.set_major_formatter(
    mdates.DateFormatter("%H:%M:%S", tz=timezone.utc)
)

for ax in axes:
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left")

fig.suptitle(
    f"Shop continuity: {len(requests)} requests, "
    f"{failed} failures, {len(deletions)} pod deletions"
)
fig.tight_layout()
output = root / "reports/continuity-chaos.png"
fig.savefig(output, dpi=160)
plt.close(fig)

summary = {
    "requests": len(requests),
    "failed": failed,
    "deletions_during_requests": len(deletions),
    "requests_by_target": dict(Counter(r["target"] for r in requests)),
    "start_utc": start.isoformat(),
    "finish_utc": finish.isoformat(),
}
(root / "reports/continuity-summary.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
print(json.dumps(summary, indent=2))
print("График:", output)
