"""
Push Vending-Machine Log Generator Output to Elasticsearch (Blind Test)
=========================================================================

Runs your existing log_generator.generate() (novel / rarity / metric /
volume / sequence anomalies, config-driven via config.py) and bulk-indexes
the resulting log lines into Elasticsearch for Grafana Assistant to query.

IMPORTANT - this is a BLIND test setup:
  The ground-truth fields (is_anomaly, anomaly_type) are deliberately NOT
  included in the indexed documents. If they were, Grafana Assistant could
  just read them back instead of actually detecting anything from the raw
  log content/patterns. Ground truth is instead written to two local files
  per run, both timestamped so repeated runs don't overwrite each other:

    answer_key_<run_id>.json   machine-readable, every log line + label,
                                joinable back to ES docs via doc_id
    answer_sheet_<run_id>.txt  human-readable, anomalies only, grouped by
                                type - this is the one to eyeball against
                                whatever Grafana Assistant reports

Usage:
    pip install elasticsearch
    python3 push_logs_to_es.py --host http://localhost:9200 --index vending-machine-logs
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from log_generator import generate  # your existing generator, unchanged


def build_docs_and_answer_key(lines, index_name):
    """
    Split each LogLine into:
      - a "blind" doc for Elasticsearch (no ground truth)
      - an answer-key entry (ground truth, keyed by a synthetic doc id
        so you can join back after Assistant reports findings)
    """
    docs = []
    answer_key = []

    for i, l in enumerate(lines):
        doc_id = f"log-{i:08d}"

        docs.append({
            "_index": index_name,
            "_id": doc_id,
            "_source": {
                "@timestamp": l.ts,
                "session_id": l.session_id,
                "service": l.service,
                "template_id": l.template_id,
                "message": l.message,
                "value": l.value,
                # NOTE: is_anomaly / anomaly_type intentionally omitted
            },
        })

        answer_key.append({
            "doc_id": doc_id,
            "ts": l.ts,
            "session_id": l.session_id,
            "service": l.service,
            "template_id": l.template_id,
            "is_anomaly": l.is_anomaly,
            "anomaly_type": l.anomaly_type,
        })

    return docs, answer_key


def build_answer_sheet_text(answer_key, meta, index_name):
    """
    Human-readable summary of every injected anomaly, grouped by type and
    sorted by timestamp within each group. Meant for eyeballing next to
    whatever Grafana Assistant reports back, not for programmatic scoring
    (that's what the JSON answer key is for).
    """
    anomalies = [a for a in answer_key if a["is_anomaly"]]
    by_type = defaultdict(list)
    for a in anomalies:
        by_type[a["anomaly_type"]].append(a)
    for group in by_type.values():
        group.sort(key=lambda a: a["ts"])

    lines = []
    lines.append("=" * 78)
    lines.append(f"ANSWER SHEET - {index_name}")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append(f"Train window ends: {meta['train_end_ts']}  "
                 f"(anomalies only exist after this timestamp)")
    lines.append(f"Total log lines: {meta.get('total_lines', 'n/a')}")
    lines.append(f"Total ground-truth anomalies: {len(anomalies)}")
    lines.append("=" * 78)

    type_order = ["novel", "rarity", "metric", "volume", "sequence"]
    for atype in type_order:
        group = by_type.get(atype, [])
        lines.append("")
        lines.append(f"--- {atype.upper()} ({len(group)}) ---")
        if not group:
            lines.append("  (none injected this run)")
            continue
        for a in group:
            lines.append(
                f"  {a['ts']}  doc_id={a['doc_id']}  "
                f"session={a['session_id']}  service={a['service']}  "
                f"template={a['template_id']}"
            )

    # catch any anomaly_type not in the expected five (shouldn't happen, but
    # better to surface it than silently drop it)
    other_types = set(by_type) - set(type_order)
    for atype in other_types:
        group = by_type[atype]
        lines.append("")
        lines.append(f"--- {atype.upper()} ({len(group)}) ---")
        for a in group:
            lines.append(f"  {a['ts']}  doc_id={a['doc_id']}  session={a['session_id']}")

    return "\n".join(lines) + "\n"


def ensure_index(es, index_name):
    if es.indices.exists(index=index_name):
        return
    es.indices.create(
        index=index_name,
        mappings={
            "properties": {
                "@timestamp": {"type": "date"},
                "session_id": {"type": "keyword"},
                "service": {"type": "keyword"},
                "template_id": {"type": "keyword"},
                "message": {"type": "text"},
                "value": {"type": "float"},
            }
        },
    )


def main():
    ap = argparse.ArgumentParser(description="Push generator output to ES for a blind Assistant detection test")
    ap.add_argument("--host", type=str, default="http://localhost:9200", help="Elasticsearch URL")
    ap.add_argument("--index", type=str, default="vending-machine-logs", help="target index name")
    ap.add_argument("--outdir", type=str, default=".", help="directory to write answer_key/answer_sheet into")
    ap.add_argument("--run-tag", type=str, default=None,
                     help="tag used in output filenames; defaults to a timestamp so runs don't overwrite each other")
    ap.add_argument("--hours-back", type=float, default=24,
                     help="span the generated timeline over the past N hours, ending now "
                          "(default 24). Pass 0 or a negative value to keep the generator's "
                          "original fixed 2026-08-04 date instead.")
    args = ap.parse_args()

    run_tag = args.run_tag or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    hours_back = args.hours_back if args.hours_back and args.hours_back > 0 else None
    lines, meta = generate(hours_back=hours_back)
    meta["total_lines"] = len(lines)
    print(f"Generated {len(lines)} log lines spanning {meta['start_ts']} -> {meta['end_ts']} "
          f"(train ends {meta['train_end_ts']}, {meta['train_minutes']}/{meta['total_minutes']} min clean)")

    n_anom = sum(1 for l in lines if l.is_anomaly)
    print(f"Ground-truth anomalies: {n_anom} "
          f"({', '.join(f'{k}={v}' for k, v in Counter(l.anomaly_type for l in lines).items())})")

    docs, answer_key = build_docs_and_answer_key(lines, args.index)

    es = Elasticsearch(args.host)
    if not es.ping():
        raise SystemExit(f"Could not reach Elasticsearch at {args.host}")

    ensure_index(es, args.index)

    success, errors = bulk(es, docs, raise_on_error=False)
    print(f"Indexed {success} docs into '{args.index}' on {args.host} (no ground-truth fields included)")
    if errors:
        print(f"{len(errors)} docs failed, first error: {errors[0]}")

    import os
    os.makedirs(args.outdir, exist_ok=True)

    key_path = os.path.join(args.outdir, f"answer_key_{run_tag}.json")
    sheet_path = os.path.join(args.outdir, f"answer_sheet_{run_tag}.txt")

    with open(key_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "index": args.index, "entries": answer_key}, f, indent=2)
    print(f"Wrote full ground truth ({len(answer_key)} docs) to {key_path}")

    sheet_text = build_answer_sheet_text(answer_key, meta, args.index)
    with open(sheet_path, "w", encoding="utf-8") as f:
        f.write(sheet_text)
    print(f"Wrote human-readable answer sheet ({n_anom} anomalies) to {sheet_path}")

    print(f"\nTrain window ends at {meta['train_end_ts']} - anomalies only exist after that timestamp.")
    print("Point Grafana Assistant at logs after that timestamp when asking it to find anomalies.")


if __name__ == "__main__":
    main()