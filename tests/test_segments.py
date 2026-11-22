import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from segments import analyze


DATA = ROOT / "demo/traffic-review/traffic.csv"


class TrafficReviewChecks(unittest.TestCase):
    def test_healthy_segments_survive_a_drop_in_total(self):
        result = analyze(DATA)
        mobile = result["devices"]["mobile"]
        self.assertEqual([mobile[p]["accepted_visits"] for p in ("before", "after")], [170, 120])
        self.assertEqual([mobile[p]["spend_rub"] for p in ("before", "after")], ["95000", "95000"])
        segments = {(row["device"], row["os"], row["channel"]): row for row in result["segments"]}
        self.assertEqual(segments["mobile", "android", "search"]["after"]["totals"]["cpa_rub"], 500)
        self.assertEqual(segments["mobile", "ios", "search"]["after"]["totals"]["cpa_rub"], 500)
        self.assertEqual(segments["mobile", "ios", "partner"]["after"]["totals"]["cpa_rub"], 2250)

    def test_mobile_standardization_reconciles_total_change(self):
        d = analyze(DATA)["descriptive_decomposition"]["mobile"]
        self.assertEqual(d["after_cr_at_before_mix_pct"], 8.0)
        self.assertEqual(d["within_segment_change_at_before_mix_pp"], -0.5)
        self.assertEqual(d["mix_change_at_after_rates_pp"], -2.0)
        self.assertEqual(d["total_change_pp"], -2.5)
        self.assertEqual(d["total_change_pp"], d["within_segment_change_at_before_mix_pp"]
                         + d["mix_change_at_after_rates_pp"])

    def test_missing_segment_week_is_not_treated_as_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "incomplete.csv"
            lines = DATA.read_text().splitlines()
            path.write_text("\n".join(lines[:-1]) + "\n")
            with self.assertRaisesRegex(ValueError, "Missing segment/week"):
                analyze(path)
