"""Stress-test in-year paid number-months using the original v1 assumptions."""
import argparse
import json
from pathlib import Path

from operator_model import count, series


def model(data, d):
    if not 0 <= d <= 12:
        raise ValueError("Calendar shift must be between 0 and 12 months")
    baseline = count(data["without_change"]["profit_rub"])
    rate = count(data["profit_per_paid_number_month_rub"])
    if not rate:
        raise ValueError("Amount per paid number-month must be positive")
    results = {}
    for name, scenario in data["scenarios"].items():
        months = series(scenario["incremental_paid_number_months_by_month"], 12)
        direct = sum(series(scenario["direct_cost_by_quarter_rub"], 4))
        inside = sum(months[:12-d])
        contribution = inside * rate - direct
        results[name] = {
            "in_year_added_paid_number_months": inside,
            "added_paid_number_months_outside_year": sum(months) - inside,
            "assumed_in_year_direct_cost_rub": direct,
            "in_year_gross_profit_increment_rub": contribution,
            "in_year_gross_profit_rub": baseline + contribution,
            "maximum_development_repayable_in_year_rub": max(0, contribution),
        }
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("assumptions", type=Path)
    p.add_argument("--delays", type=int, nargs="+", default=[0, 1, 3, 6])
    args = p.parse_args()
    try:
        data = json.loads(args.assumptions.read_text(encoding="utf-8-sig"))
        output = {
            "kind": "calendar_sensitivity_synthetic_not_forecast",
            "direct_cost_assumption": "same annual direct costs as v1; deployment dates are unknown",
            "results_by_delay_months": {d: model(data, d) for d in args.delays},
        }
    except (OSError, ValueError, TypeError, KeyError) as e:
        p.exit(2, f"Invalid calendar assumptions: {e}\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
