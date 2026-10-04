# hw-flow-metrics

A small open-source hardware design flow that **records metrics from every run**.

Each run simulates an 8-bit counter with **Verilator**, synthesizes it with **Yosys**, extracts metrics (pass/fail, cell count, flip-flops, warnings, runtime) plus metadata (git commit, tool versions, host, user), stores them in a database, and shows them on a dashboard. GitHub Actions runs the whole flow on every push.

The idea: treat the design flow itself as a data source, so the team can see trends, catch regressions and plan resources.

```
rtl/counter.v ──► Verilator simulation ──┐
                                          ├──► run_flow.py ──► metrics.db ──► dashboard.html
scripts/synth.ys ──► Yosys synthesis ────┘     (parse + metadata)   (SQLite)
```

## Project layout

| Path | What it is |
| --- | --- |
| `rtl/counter.v` | The design: a parameterized up-counter |
| `tb/tb_counter.cpp` | Self-checking C++ testbench for Verilator (prints `TEST PASSED` / `TEST FAILED`) |
| `scripts/synth.ys` | Yosys synthesis script, writes text + JSON reports |
| `scripts/run_flow.py` | Runs simulation and synthesis, parses results, stores one row per run |
| `scripts/dashboard.py` | Builds `reports/dashboard.html` from the database |
| `.github/workflows/flow.yml` | CI: runs the flow on every push, uploads reports |
| `Dockerfile` | Same tool environment as CI, for running anywhere |

## Step-by-step: run it yourself

### 1. Get a Linux environment
- **Linux / Ubuntu:** nothing to do.
- **Windows:** install WSL with `wsl --install` in PowerShell (as admin), restart, then open "Ubuntu".
- **macOS:** use Homebrew (`brew install verilator yosys`).

### 2. Install the tools (Ubuntu 24.04 / WSL)
```bash
sudo apt update
sudo apt install -y verilator yosys python3-pip build-essential git
pip install -r requirements.txt      # add --break-system-packages if pip refuses
verilator --version                  # needs 5.x for --binary
yosys -V
```
No sudo or old Ubuntu? `pip install yowasp-yosys` gives you Yosys; run the flow with `YOSYS=yowasp-yosys`.

### 3. Try each tool by hand (understand what the script automates)
```bash
# Simulation: Verilator turns the Verilog into C++, compiles it together
# with the C++ testbench into one program, then we run it
verilator --cc --exe --build -Wall -Wno-fatal rtl/counter.v tb/tb_counter.cpp
./obj_dir/Vcounter                   # expect: TEST PASSED

# Synthesis: turn RTL into logic gates and print statistics
mkdir -p build
yosys -s scripts/synth.ys
cat build/synth_stat.txt             # cells, flip-flops by type
```

### 4. Run the full pipeline
```bash
python3 scripts/run_flow.py          # prints the run record as JSON
python3 scripts/dashboard.py         # writes reports/dashboard.html
```
Open `reports/dashboard.html` in a browser.

### 5. Create history (so the charts show something)
Change `WIDTH = 8` to `16` in `rtl/counter.v`, commit, run the flow again, then switch back and run once more. The dashboard shows the cell count jump from about 22 to 46 and back: exactly the kind of change a team wants to see per commit.

You can also query the database directly:
```bash
sqlite3 metrics.db "SELECT r.id, r.git_commit, m.value AS cells
                    FROM runs r JOIN run_metrics m ON m.run_id = r.id
                    WHERE m.name = 'cells' ORDER BY r.id;"
```

### 6. Put it on GitHub with CI
```bash
git init && git add . && git commit -m "Mini hardware flow with metrics pipeline"
git branch -M main
git remote add origin https://github.com/<your-user>/hw-flow-metrics.git
git push -u origin main
```
Open the **Actions** tab: the `hw-flow` job runs simulation and synthesis. Download the `flow-reports` artifact to see the logs and the dashboard.

### 7. Optional: run in Docker
```bash
docker build -t hw-flow .
docker run --rm -v "$PWD:/work" hw-flow
```

## Why a C++ testbench?

Verilator is a cycle-based simulator: it compiles the design into a C++ model. The classic way to test it is a small C++ program that toggles the clock and checks the outputs. A Verilog testbench with delays (`#5`) would need Verilator's timing mode, which requires a C++20 compiler with coroutine support; older macOS Command Line Tools do not have that.

## Database design

- `runs`: one row per run: time, design, git commit, host, user, tool versions, step status.
- `run_metrics`: one row per (run, metric name, value). New metrics need no schema change.

## What I would add next

- **PostgreSQL + Grafana** instead of SQLite + static HTML, for live dashboards and alerts.
- **Persist CI history:** each CI run currently starts with an empty database; push results to a central database instead.
- **License usage:** collect FlexLM `lmstat` snapshots into the same database.
- **Cluster data:** import Slurm `sacct` job data (runtime, memory, GPUs per user).
- **Real PDK:** synthesize against a real standard-cell library, e.g. the IHP SG13G2 open PDK, to get area and timing instead of generic gate counts.
- **More flow steps:** place and route with OpenROAD, timing slack as a metric.

## Tutorials used

- Verilator: <https://verilator.org/guide/latest/> and a counter + testbench walkthrough: <https://chipverify.com/rtl-synthesis/verilator-simulation>
- Yosys getting started: <https://yosyshq.readthedocs.io/projects/yosys/en/latest/getting_started/index.html>
- Verilog basics (counter + testbench): <https://www.asic-world.com/verilog/first1.html>
- IHP open PDK: <https://github.com/IHP-GmbH/IHP-Open-PDK>
