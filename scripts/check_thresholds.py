#!/usr/bin/env python3
"""Fail the build when a JMeter run breaches its thresholds, or never really ran.

Reads the statistics.json written by the JMeter HTML report generator (-e -o).
pct2ResTime is the 95th percentile under JMeter's default report settings
(jmeter.reportgenerator.statistic_window / aggregate_rpt_pct2=95).
"""
import argparse
import json
import sys


def evaluate(stats, cfg, min_samples=None):
    """Return (failures, rows). An empty failures list means the gate passes."""
    failures, rows = [], []

    total = stats.get("Total")
    if not total:
        return ['statistics.json has no "Total" entry: the run produced no results'], rows

    samples = total.get("sampleCount", 0)
    need = cfg.get("minSamples", 1) if min_samples is None else min_samples
    if samples < need:
        failures.append(f"only {samples} samples recorded (need >= {need}): the test did not really run")

    if total.get("errorPct", 100.0) > cfg["maxErrorPct"]:
        failures.append(f"error rate {total['errorPct']:.2f}% exceeds {cfg['maxErrorPct']}%")

    for label, limit in cfg["p95Ms"].items():
        tx = stats.get(label)
        if tx is None or tx.get("sampleCount", 0) == 0:
            failures.append(f'transaction "{label}" has no samples: the flow never reached it')
            continue
        p95 = tx["pct2ResTime"]
        ok = p95 <= limit
        rows.append((label, tx["sampleCount"], tx["errorPct"], p95, limit, ok))
        if not ok:
            failures.append(f'"{label}" p95 {p95:.0f} ms exceeds {limit} ms')

    return failures, rows


def markdown(rows, failures):
    out = ["| Transaction | Samples | Errors % | p95 ms | Limit ms | Result |",
           "|---|---:|---:|---:|---:|---|"]
    for label, n, err, p95, limit, ok in rows:
        out.append(f"| {label} | {n} | {err:.2f} | {p95:.0f} | {limit} | {'pass' if ok else '**FAIL**'} |")
    out.append("")
    out.append("**Gate: PASS**" if not failures else "**Gate: FAIL**\n\n" + "\n".join(f"- {f}" for f in failures))
    return "\n".join(out) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stats", required=True, help="path to report/statistics.json")
    p.add_argument("--thresholds", required=True, help="path to thresholds.json")
    p.add_argument("--min-samples", type=int, help="override minSamples from thresholds.json")
    p.add_argument("--summary", help="append a markdown summary here (e.g. $GITHUB_STEP_SUMMARY)")
    a = p.parse_args(argv)

    try:
        with open(a.stats, encoding="utf-8") as f:
            stats = json.load(f)
    except FileNotFoundError:
        print(f"GATE FAIL: {a.stats} not found: JMeter did not produce a report", file=sys.stderr)
        return 1
    with open(a.thresholds, encoding="utf-8") as f:
        cfg = json.load(f)

    failures, rows = evaluate(stats, cfg, a.min_samples)
    md = markdown(rows, failures)
    print(md)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(md)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
