# Same environment as the CI job, for running the flow anywhere with Docker:
#   docker build -t hw-flow .
#   docker run --rm -v "$PWD:/work" hw-flow
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
        verilator yosys python3 python3-matplotlib git build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
CMD ["sh", "-c", "python3 scripts/run_flow.py; python3 scripts/dashboard.py"]
