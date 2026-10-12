"""Selftest for the performance gate: it must pass a healthy run and go red on every failure mode."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from check_thresholds import evaluate, main  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures")
THRESHOLDS = os.path.join(ROOT, "scripts", "thresholds.json")
PLAN = os.path.join(ROOT, "test-plans", "fhir-patient-journey.jmx")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


with open(THRESHOLDS, encoding="utf-8") as f:
    CFG = json.load(f)


class GateTest(unittest.TestCase):
    def test_healthy_run_passes(self):
        failures, rows = evaluate(load("pass.json"), CFG)
        self.assertEqual(failures, [])
        self.assertEqual(len(rows), len(CFG["p95Ms"]))

    def test_slow_transaction_fails(self):
        failures, _ = evaluate(load("slow.json"), CFG)
        self.assertTrue(any("p95" in f for f in failures), failures)

    def test_high_error_rate_fails(self):
        failures, _ = evaluate(load("errors.json"), CFG)
        self.assertTrue(any("error rate" in f for f in failures), failures)

    def test_empty_report_fails(self):
        failures, _ = evaluate({}, CFG)
        self.assertTrue(failures)

    def test_too_few_samples_fails(self):
        failures, _ = evaluate(load("pass.json"), CFG, min_samples=10_000)
        self.assertTrue(any("did not really run" in f for f in failures), failures)

    def test_missing_transaction_fails(self):
        stats = load("pass.json")
        del stats["TX05 Record heart-rate observation"]
        failures, _ = evaluate(stats, CFG)
        self.assertTrue(any("never reached" in f for f in failures), failures)

    def test_missing_report_file_fails(self):
        self.assertEqual(main(["--stats", os.path.join(FIXTURES, "nope.json"), "--thresholds", THRESHOLDS]), 1)

    def test_thresholds_match_plan_transactions(self):
        # A renamed Transaction Controller would otherwise silently drop out of the gate.
        with open(PLAN, encoding="utf-8") as f:
            names = set(re.findall(r'testclass="TransactionController" testname="([^"]+)"', f.read()))
        self.assertEqual(names, set(CFG["p95Ms"]))


if __name__ == "__main__":
    unittest.main()
