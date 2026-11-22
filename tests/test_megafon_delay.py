import json
from pathlib import Path
import sys
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from megafon_delay import model


class DelayStressTest(TestCase):
    def test_late_benefits_stay_outside_the_plan_year(self):
        fixture = json.loads((ROOT / "demo/megafon/assumptions.json").read_text())
        early = model(fixture, 0)["main"]
        late = model(fixture, 6)["main"]
        self.assertEqual(early["in_year_gross_profit_rub"], 280770000)
        self.assertEqual(late["in_year_added_paid_number_months"], 600)
        self.assertEqual(late["added_paid_number_months_outside_year"], 3900)
        self.assertEqual(late["in_year_gross_profit_increment_rub"], -180000)
        self.assertEqual(late["maximum_development_repayable_in_year_rub"], 0)
        with self.assertRaises(ValueError):
            model(fixture, -1)
