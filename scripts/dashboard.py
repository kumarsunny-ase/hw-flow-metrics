#!/usr/bin/env python3
"""
dashboard.py - turn metrics.db into a simple HTML dashboard (reports/dashboard.html).

Shows: cell count and flip-flops per run, runtime per step, and a table of recent runs.
Usage:  python3 scripts/dashboard.py
"""
import base64
import io
import os
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("METRICS_DB", ROOT / "metrics.db"))
OUT = ROOT / "reports" / "dashboard.html"


def load():
    con = sqlite3.connect(DB_PATH)
    runs = con.execute(
        "SELECT id, started_at, git_commit, sim_status, synth_status, yosys_version "
        "FROM runs ORDER BY id").fetchall()
    metrics = {}
    for run_id, name, value in con.execute("SELECT run_id, name, value FROM run_metrics"):
        metrics.setdefault(run_id, {})[name] = value
    con.close()
    return runs, metrics


def chart(ids, series, title, ylabel):
    fig, ax = plt.subplots(figsize=(7, 3))
    for label, values in series.items():
        ax.plot(ids, values, marker="o", label=label)
    ax.set_title(title, loc="left", fontsize=11)
    ax.set_xlabel("run id")
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    if len(series) > 1:
        ax.legend(frameon=False)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return f'<img alt="{title}" src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


def main():
    runs, metrics = load()
    if not runs:
        raise SystemExit("No runs in metrics.db yet - run scripts/run_flow.py first.")
    ids = [r[0] for r in runs]
    get = lambda name: [metrics.get(i, {}).get(name) for i in ids]

    charts = [
        chart(ids, {"cells": get("cells"), "flip-flops": get("flip_flops")},
              "Design size per run", "count"),
        chart(ids, {"simulation": get("sim_seconds"), "synthesis": get("synth_seconds")},
              "Runtime per step", "seconds"),
    ]
    rows = "".join(
        f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2] or '-'}</td>"
        f"<td class='{r[3]}'>{r[3]}</td><td class='{r[4]}'>{r[4]}</td>"
        f"<td>{metrics.get(r[0], {}).get('cells', '-')}</td><td>{r[5] or '-'}</td></tr>"
        for r in reversed(runs[-20:]))

    passed = sum(1 for r in runs if r[3] in ("pass", "skipped") and r[4] == "pass")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Design Flow Metrics</title>
<style>
 body {{font-family: system-ui, sans-serif; max-width: 900px; margin: 24px auto; padding: 0 16px; color:#222}}
 .kpis {{display:flex; gap:16px}} .kpi {{border:1px solid #ddd; border-radius:8px; padding:12px 16px}}
 .kpi b {{display:block; font-size:24px}}
 table {{border-collapse: collapse; width:100%; font-size:14px}}
 td, th {{border-bottom:1px solid #eee; padding:6px; text-align:left}}
 .pass {{color:#1a7f37}} .fail, .build_error {{color:#cf222e}} .skipped {{color:#888}}
 img {{max-width:100%}}
</style></head><body>
<h1>Design Flow Metrics - counter</h1>
<div class="kpis">
 <div class="kpi">Total runs<b>{len(runs)}</b></div>
 <div class="kpi">Successful runs<b>{passed}</b></div>
 <div class="kpi">Latest cell count<b>{metrics.get(ids[-1], {}).get('cells', '-')}</b></div>
</div>
{''.join(charts)}
<h2>Recent runs</h2>
<table><tr><th>Run</th><th>Started (UTC)</th><th>Commit</th><th>Simulation</th>
<th>Synthesis</th><th>Cells</th><th>Yosys</th></tr>{rows}</table>
</body></html>""")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
