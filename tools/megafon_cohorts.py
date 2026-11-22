"""Illustrative cohort sensitivity, separate from historical v1/v2 runs."""
import argparse
import csv
import json
from collections import defaultdict
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

BASE_PROFIT = 279000000
TARGET_PROFIT = 285000000
RATE = 500


def estimate(cohorts, costs):
    scenarios = defaultdict(lambda: {"paid_number_months": Decimal(0), "direct_cost_rub": 0})
    seen = set()
    entries = {}
    for row in cohorts:
        name, cohort = row["scenario"], row["cohort_id"]
        launch, observed, size = map(int, (row["launch_month"], row["paid_month"], row["eligible_numbers"]))
        control, treatment = map(Decimal, (row["p_paid_control"], row["p_paid_treatment"]))
        key = name, cohort, observed
        if (not name or not cohort or not 1 <= launch <= observed <= 12 or size < 1
                or not all(x.is_finite() and 0 <= x <= 1 for x in (control, treatment)) or key in seen):
            raise ValueError("Invalid or duplicated cohort-month")
        seen.add(key)
        group = name, cohort
        if entries.setdefault(group, (launch, size)) != (launch, size):
            raise ValueError("Cohort entry and size must stay constant")
        scenarios[name]["paid_number_months"] += size * (treatment - control)
    if not scenarios:
        raise ValueError("No cohort rows")
    if any((name, cohort, m) not in seen for (name, cohort), (launch, _) in entries.items()
           for m in range(launch, 13)):
        raise ValueError("A cohort has missing in-year months")
    cost_items = set()
    for row in costs:
        name, item = row["scenario"], row["cost_item"]
        volume, unit, periods = map(int, (row["volume_per_period"], row["unit_cost_rub"], row["periods"]))
        if name not in scenarios or not item or (name, item) in cost_items or min(volume, unit, periods) < 0:
            raise ValueError("Invalid or duplicated cost row")
        cost_items.add((name, item))
        scenarios[name]["direct_cost_rub"] += volume * unit * periods
    if set(scenarios) != {key[0] for key in cost_items}:
        raise ValueError("Provide explicit direct cost rows for each scenario")
    for s in scenarios.values():
        s["incremental_margin_rub"] = s["paid_number_months"] * RATE - s["direct_cost_rub"]
        s["scenario_profit_rub"] = BASE_PROFIT + s["incremental_margin_rub"]
        s["remaining_gap_rub"] = max(Decimal(0), TARGET_PROFIT - s["scenario_profit_rub"])
        s["months_required_for_target"] = (Decimal(TARGET_PROFIT - BASE_PROFIT + s["direct_cost_rub"]) / RATE).to_integral_value(rounding=ROUND_CEILING)
    return {"kind": "sensitivity_on_synthetic_inputs_not_forecast", "rate_rub": RATE, "scenarios": dict(scenarios)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cohorts", type=Path)
    p.add_argument("costs", type=Path)
    args = p.parse_args()
    with args.cohorts.open(encoding="utf-8-sig", newline="") as c, args.costs.open(encoding="utf-8-sig", newline="") as d:
        ans = estimate(csv.DictReader(c), csv.DictReader(d))
    print(json.dumps(ans, ensure_ascii=False, indent=2,
                     default=lambda x: int(x) if x == int(x) else float(x)))


if __name__ == "__main__":
    main()
