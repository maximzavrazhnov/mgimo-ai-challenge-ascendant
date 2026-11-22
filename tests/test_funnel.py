import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("funnel", ROOT / "tools/funnel.py")
funnel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(funnel)
DATA = ROOT / "demo/funnel.csv"
UPDATE = ROOT / "demo/update/definitions.json"
MOBILE = ROOT / "demo/alternative-update/definitions.json"
HISTORY = ROOT / "demo/history.csv"


class FunnelChecks(unittest.TestCase):
    def test_same_goal_label_does_not_make_rates_comparable(self):
        result = funnel.analyze(DATA)
        self.assertEqual(result["periods"]["before"]["reported_goal_visits"], 50)
        self.assertEqual(result["periods"]["after"]["reported_goal_visits"], 30)
        self.assertEqual(result["goal_comparability"], "unknown")
        self.assertIsNone(result["accepted_application_comparison"])

    def test_new_evidence_reveals_stable_verified_outcome(self):
        result = funnel.analyze(DATA, UPDATE)
        self.assertEqual(result["goal_comparability"], "different_definitions")
        after = result["accepted_application_comparison"]["after"]
        self.assertEqual(after, result["accepted_application_comparison"]["before"])
        self.assertEqual(after["accepted_visits"], 30)
        self.assertAlmostEqual(after["cr_pct"], 100 * 30 / 650, places=4)

    def test_duplicate_segment_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "duplicate.csv"
            text = DATA.read_text()
            path.write_text(text.rstrip() + "\n" + text.splitlines()[1] + "\n")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                funnel.analyze(path)

    def test_conflicting_measurements_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "update.json"
            data = json.loads(UPDATE.read_text())
            data["accepted_by_period"]["after"]["mobile"] = 15
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "conflict"):
                funnel.analyze(DATA, path)

    def test_identical_start_can_hide_a_real_drop_after_reconciliation(self):
        measurement_only = funnel.analyze(DATA, UPDATE)
        mobile_drop = funnel.analyze(DATA, MOBILE)
        self.assertEqual(measurement_only["periods"], mobile_drop["periods"])
        self.assertEqual(measurement_only["goal_comparability"], mobile_drop["goal_comparability"])
        comparison = mobile_drop["accepted_application_comparison"]
        self.assertEqual([comparison[p]["accepted_visits"] for p in ("before", "after")], [42, 30])
        self.assertEqual(mobile_drop["accepted_application_by_device"]["desktop"]["accepted_delta"], 0)
        mobile = mobile_drop["accepted_application_by_device"]["mobile"]
        self.assertEqual(mobile["accepted_delta"], -12)
        self.assertAlmostEqual(mobile["cr_delta_pp"], -1200 / 380, places=4)

    def test_rephrased_live_measure_is_not_novel(self):
        found = funnel.history(HISTORY, "fewer-fields")
        self.assertEqual(found["matches"][0]["status"], "live")
        self.assertEqual(found["matches"][0]["id"], "short-form")
        self.assertEqual(funnel.history(HISTORY, "support-hours-copy")["status"], "not_found_in_available_history")


if __name__ == "__main__":
    unittest.main()
