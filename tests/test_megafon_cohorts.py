import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from megafon_cohorts import estimate


def sample(s, m, treatment):
    return {"scenario": s, "cohort_id": "A", "launch_month": 11, "paid_month": m,
            "eligible_numbers": 200, "p_paid_control": "0.8", "p_paid_treatment": treatment}


def cost():
    return {"scenario": "main", "cost_item": "handling", "volume_per_period": 10,
            "unit_cost_rub": 30, "periods": 2}


class CohortModelChecks(unittest.TestCase):
    def test_uses_separate_cohort_month_lifts_and_cost_periods(self):
        result = estimate([sample("main", 11, "0.9"), sample("main", 12, "0.77")], [cost()])["scenarios"]["main"]
        self.assertEqual(result["paid_number_months"], 14)
        self.assertEqual(result["direct_cost_rub"], 600)
        self.assertEqual(result["incremental_margin_rub"], 6400)

    def test_missing_or_duplicate_months_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            estimate([sample("main", 11, "0.9")], [cost()])
        with self.assertRaisesRegex(ValueError, "duplicated"):
            estimate([sample("main", 11, "0.9")] * 2, [cost()])
