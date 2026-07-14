#!/usr/bin/env python3
"""
exporter.py

Runs tcp_trace.bt as a subprocess, parses its stdout line-by-line, and
exposes the results as Prometheus metrics on :9435/metrics.

Cardinality note: destination IP:port is included as a label. On a small
two-service demo this is fine. If you point this at a busier host, drop
`daddr`/`dport` from the labels below (or bucket them, e.g. by /24) to
avoid label explosion in Prometheus.

Requires: bpftrace installed, root privileges (bpftrace needs CAP_BPF /
root to attach kernel probes), prometheus_client (`pip install
prometheus_client --break-system-packages`).

Run:
    sudo python3 exporter.py
"""

import subprocess
import threading
import logging
import signal
import sys

from prometheus_client import start_http_server, Counter, Histogram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ebpf-tcp-exporter")

BPFTRACE_SCRIPT = "./tcp_trace.bt"
METRICS_PORT = 9435

# ---- Prometheus metric definitions -----------------------------------

CONNECT_LATENCY = Histogram(
    "ebpf_tcp_connect_latency_seconds",
    "Kernel-measured SYN->ESTABLISHED latency per outbound connection",
    labelnames=["comm", "daddr", "dport"],
    buckets=(.0005, .001, .0025, .005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5),
)

RETRANSMITS_TOTAL = Counter(
    "ebpf_tcp_retransmits_total",
    "Count of TCP retransmission events observed at the kernel level",
    labelnames=["comm", "daddr", "dport"],
)

CONN_CLOSE_TOTAL = Counter(
    "ebpf_tcp_connections_closed_total",
    "Count of TCP connections transitioning ESTABLISHED -> CLOSE",
    labelnames=["comm", "daddr", "dport"],
)

PARSE_ERRORS = Counter(
    "ebpf_exporter_parse_errors_total",
    "Lines from bpftrace stdout that failed to parse",
)


def handle_line(line: str) -> None:
    line = line.strip()
    if not line:
        return

    parts = line.split("|")
    tag = parts[0]

    try:
        if tag == "READY":
            log.info("bpftrace probes attached and running")

        elif tag == "CONNECT_LATENCY":
            _, pid, comm, latency_ns, daddr, dport = parts
            CONNECT_LATENCY.labels(comm=comm, daddr=daddr, dport=dport).observe(
                int(latency_ns) / 1e9
            )

        elif tag == "RETRANSMIT":
            _, pid, comm, daddr, dport = parts
            RETRANSMITS_TOTAL.labels(comm=comm, daddr=daddr, dport=dport).inc()

        elif tag == "CONN_CLOSE":
            _, pid, comm, daddr, dport = parts
            CONN_CLOSE_TOTAL.labels(comm=comm, daddr=daddr, dport=dport).inc()

        else:
            # Unrecognized line (e.g. bpftrace warnings on stderr merged in,
            # or attach messages) -- ignore rather than fail loudly.
            log.debug("unhandled line: %s", line)

    except ValueError:
        PARSE_ERRORS.inc()
        log.warning("failed to parse line: %s", line)


bpftrace_proc = None  # set by run_bpftrace(), read by shutdown() on the main thread


def run_bpftrace() -> None:
    """Launch bpftrace and stream its stdout into handle_line forever.

    Runs inside a background thread -- do NOT register signal handlers here.
    Python only allows signal.signal() to be called from the main thread of
    the main interpreter; calling it from a worker thread raises ValueError
    and kills the thread silently (the main thread won't see the exception,
    it'll just see the thread end, and the process exits with code 0 --
    which is why systemd reported "Succeeded" even though nothing useful
    ran).
    """
    global bpftrace_proc
    cmd = ["bpftrace", BPFTRACE_SCRIPT]
    log.info("starting bpftrace: %s", " ".join(cmd))

    bpftrace_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    for line in bpftrace_proc.stdout:
        handle_line(line)

    bpftrace_proc.wait()
    log.error("bpftrace process exited with code %s", bpftrace_proc.returncode)


def shutdown(signum, frame):
    log.info("shutting down, terminating bpftrace")
    if bpftrace_proc is not None:
        bpftrace_proc.terminate()
    sys.exit(0)


def main() -> None:
    # Signal handlers MUST be registered here, in the main thread, before
    # the bpftrace worker thread is started.
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    start_http_server(METRICS_PORT)
    log.info("metrics available at :%d/metrics", METRICS_PORT)

    bpftrace_thread = threading.Thread(target=run_bpftrace, daemon=True)
    bpftrace_thread.start()
    bpftrace_thread.join()


if __name__ == "__main__":
    main()