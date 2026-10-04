#!/usr/bin/env python3
"""
run_flow.py - run the mini hardware flow and record metrics for every run.

Steps:
  1. Simulation with Verilator  (tb/tb_counter.v + rtl/counter.v)
  2. Synthesis with Yosys       (scripts/synth.ys)
  3. Parse logs/reports -> one "run" record with metadata + metrics
  4. Store it in SQLite (metrics.db) and as JSON (build/run_metrics.json)

Usage:
  python3 scripts/run_flow.py
  YOSYS=yowasp-yosys python3 scripts/run_flow.py   # if Yosys came from pip
"""
import datetime as dt
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DB_PATH = Path(os.environ.get("METRICS_DB", ROOT / "metrics.db"))
YOSYS = os.environ.get("YOSYS", "yosys")
VERILATOR = os.environ.get("VERILATOR", "verilator")


# ---------- helpers ----------
def run(cmd, log_file):
    """Run a command, save its output to log_file, return (exit_code, seconds, text)."""
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    seconds = round(time.perf_counter() - start, 3)
    text = proc.stdout + proc.stderr
    log_file.write_text(text)
    return proc.returncode, seconds, text


def tool_version(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except (FileNotFoundError, IndexError, subprocess.TimeoutExpired):
        return None


def git_commit():
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"][:12]
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                             cwd=ROOT, capture_output=True, text=True)
        return out.stdout.strip() or None
    except FileNotFoundError:
        return None


# ---------- flow steps ----------
def simulate():
    if shutil.which(VERILATOR) is None:
        return {"sim_status": "skipped", "sim_seconds": None, "sim_warnings": None}
    obj_dir = BUILD / "obj_dir"
    # C++ testbench (tb/tb_counter.cpp): works with older compilers too,
    # because it does not need Verilator's C++20 "timing" mode.
    cmd = [VERILATOR, "--cc", "--exe", "--build", "-j", "0", "-Wall", "-Wno-fatal",
           "--Mdir", str(obj_dir), "rtl/counter.v", str(ROOT / "tb" / "tb_counter.cpp")]
    code, build_s, build_log = run(cmd, BUILD / "sim_build.log")
    if code != 0:
        return {"sim_status": "build_error", "sim_seconds": build_s,
                "sim_warnings": build_log.count("%Warning")}
    code, run_s, run_log = run([str(obj_dir / "Vcounter")], BUILD / "sim_run.log")
    passed = code == 0 and "TEST PASSED" in run_log
    return {"sim_status": "pass" if passed else "fail",
            "sim_seconds": round(build_s + run_s, 3),
            "sim_warnings": build_log.count("%Warning")}


def synthesize():
    if shutil.which(YOSYS) is None:
        return {"synth_status": "skipped"}
    code, seconds, log = run([YOSYS, "-s", "scripts/synth.ys"], BUILD / "synth.log")
    result = {"synth_status": "pass" if code == 0 else "fail",
              "synth_seconds": seconds,
              "synth_warnings": len(re.findall(r"^Warning:", log, re.MULTILINE))}
    stat_file = BUILD / "synth_stat.json"
    if code == 0 and stat_file.exists():
        stat = json.loads(stat_file.read_text())
        design = stat.get("design") or next(iter(stat["modules"].values()))
        by_type = design.get("num_cells_by_type", {})
        result["cells"] = design.get("num_cells")
        result["flip_flops"] = sum(n for t, n in by_type.items() if "DFF" in t.upper())
        result["cell_types"] = by_type
    return result


# ---------- storage ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TEXT NOT NULL,
    design         TEXT NOT NULL,
    git_commit     TEXT,
    host           TEXT,
    user_name      TEXT,
    yosys_version  TEXT,
    verilator_version TEXT,
    sim_status     TEXT,
    synth_status   TEXT
);
CREATE TABLE IF NOT EXISTS run_metrics (
    run_id  INTEGER NOT NULL REFERENCES runs(id),
    name    TEXT NOT NULL,
    value   REAL,
    PRIMARY KEY (run_id, name)
);
"""

METRIC_KEYS = ["sim_seconds", "sim_warnings", "synth_seconds",
               "synth_warnings", "cells", "flip_flops"]


def store(record):
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    cur = con.execute(
        "INSERT INTO runs (started_at, design, git_commit, host, user_name, "
        "yosys_version, verilator_version, sim_status, synth_status) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (record["started_at"], record["design"], record["git_commit"],
         record["host"], record["user"], record["yosys_version"],
         record["verilator_version"], record["sim_status"], record["synth_status"]))
    run_id = cur.lastrowid
    for key in METRIC_KEYS:
        if record.get(key) is not None:
            con.execute("INSERT INTO run_metrics VALUES (?,?,?)", (run_id, key, record[key]))
    con.commit()
    con.close()
    return run_id


def main():
    BUILD.mkdir(exist_ok=True)
    record = {
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "design": "counter",
        "git_commit": git_commit(),
        "host": socket.gethostname(),
        "user": os.environ.get("USER") or os.environ.get("GITHUB_ACTOR"),
        "yosys_version": tool_version([YOSYS, "-V"]),
        "verilator_version": tool_version([VERILATOR, "--version"]),
    }
    record.update(simulate())
    record.update(synthesize())
    record["run_id"] = store(record)
    (BUILD / "run_metrics.json").write_text(json.dumps(record, indent=2))

    print(json.dumps({k: v for k, v in record.items() if k != "cell_types"}, indent=2))
    # Fail the CI job if a step that ran did not pass
    failed = [s for s in ("sim_status", "synth_status")
              if record.get(s) not in ("pass", "skipped")]
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
