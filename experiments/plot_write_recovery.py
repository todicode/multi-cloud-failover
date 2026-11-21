import csv
import json
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

runs_dir = Path("experiments/runs")
aws_runs = [
    "stage9-a01-20261120T202632Z",
    "stage9-a02-20261121T110016Z",
    "stage9-a03-20261121T115954Z",
]
multi_runs = [
    "stage9-b01-20261120T190829Z",
    "stage9-b02-20261121T101841Z",
    "stage9-b03-20261121T113203Z",
]


def read_measurements(run_id, recovery_site):
    fault_lines = (runs_dir / f"{run_id}.fault.log").read_text(encoding="utf-8").splitlines()
    markers = dict(line.split("=", 1) for line in fault_lines if "_at_utc=" in line)
    stop_at = datetime.fromisoformat(markers["stop_requested_at_utc"])
    start_marker = markers.get("start_requested_at_utc", markers["stop_requested_at_utc"])
    earliest_recovery = datetime.fromisoformat(start_marker)

    with (runs_dir / f"{run_id}.csv").open(encoding="utf-8", newline="") as log:
        for row in csv.DictReader(log):
            at = datetime.fromisoformat(row["at"])
            if (
                at >= earliest_recovery
                and row["write_status"] == "200"
                and row["served_by"] == recovery_site
            ):
                recovery_seconds = (at - stop_at).total_seconds()
                break
        else:
            raise ValueError(f"No successful write after recovery in {run_id}.")

    summary = json.loads((runs_dir / f"{run_id}.summary.json").read_text(encoding="utf-8"))
    outages = summary["write"]["outages"]
    initial = outages[0]["seconds"]
    later = sum(outage["seconds"] for outage in outages[1:])
    return recovery_seconds, initial, later


aws_recovery, aws_initial, _ = zip(*(read_measurements(run, "aws") for run in aws_runs))
multi_recovery, multi_initial, multi_failback = zip(
    *(read_measurements(run, "azure") for run in multi_runs)
)

fig, (recovery, downtime) = plt.subplots(
    1, 2, figsize=(11, 4.8), sharey=True, layout="constrained"
)
positions = range(3)
width = 0.34
aws_x = [x - width / 2 for x in positions]
multi_x = [x + width / 2 for x in positions]
aws_color, multi_color, failback_color = "#3B5C79", "#1D877E", "#EAA448"

recovery.bar_label(recovery.bar(aws_x, aws_recovery, width, color=aws_color), fmt="%.1f", padding=3)
recovery.bar_label(recovery.bar(multi_x, multi_recovery, width, color=multi_color), fmt="%.1f", padding=3)
recovery.set_title("Time to first successful write")

aws_bars = downtime.bar(aws_x, aws_initial, width, color=aws_color, label="AWS-only")
multi_bars = downtime.bar(multi_x, multi_initial, width, color=multi_color, label="AWS + Azure standby")
failback_bars = downtime.bar(
    multi_x, multi_failback, width, bottom=multi_initial,
    color=failback_color, label="Failback downtime"
)
downtime.bar_label(aws_bars, fmt="%.1f", padding=3)
multi_totals = [
    initial + failback
    for initial, failback in zip(multi_initial, multi_failback)
]
downtime.bar_label(
    failback_bars,
    labels=[f"{total:.1f}" for total in multi_totals],
    label_type="edge",
    padding=3,
)
downtime.set_title("Total write downtime")

for axis in (recovery, downtime):
    axis.set_xticks(positions, ["Pair 01", "Pair 02", "Pair 03"])
    axis.set_ylim(0, 400)
    axis.set_axisbelow(True)
    axis.grid(axis="y", alpha=0.24)

recovery.set_ylabel("Seconds")
fig.legend(handles=[aws_bars, multi_bars, failback_bars],
           loc="outside upper center", ncols=3, frameon=False)

output = runs_dir / "write_recovery_comparison.png"
fig.savefig(output, dpi=200)
print(f"Saved: {output}")