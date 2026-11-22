"""Summarize comparable synthetic funnel segments; never authorize a change."""
import argparse
from datetime import date
from decimal import Decimal
import json
import sys

from funnel import PERIODS, ratio, rows


DIMENSIONS = ("device", "os", "channel", "landing")
FIELDS = {"period", "week_start", "visits", "accepted_visits", "spend_rub", *DIMENSIONS}


def summarize(records):
    visits = accepted = spend = 0
    for count, leads, amount in records:
        visits += count
        accepted += leads
        spend += amount
    return {
        "visits": visits, "accepted_visits": accepted, "spend_rub": str(spend),
        "cr_pct": ratio(accepted, visits),
        "cpa_rub": ratio(spend, accepted, 1),
    }


def describe(weeks):
    return {
        "totals": summarize(weeks.values()),
        "weeks": {day.isoformat(): summarize([value]) for day, value in sorted(weeks.items())},
    }


def analyze(path):
    data = {}
    windows = {period: set() for period in PERIODS}
    for line, row in rows(path, FIELDS):
        period, week = row["period"], date.fromisoformat(row["week_start"])
        key = tuple(row[d] for d in DIMENSIONS)
        if period not in PERIODS or week.weekday() != 0:
            raise ValueError(f"Line {line}: unknown period or non-Monday start")
        visits, accepted = int(row["visits"]), int(row["accepted_visits"])
        spend = Decimal(row["spend_rub"])
        if not 0 <= accepted <= visits or not spend.is_finite() or spend < 0:
            raise ValueError(f"Line {line}: invalid visits, accepted visits or spend")
        bucket = data.setdefault(key, {p: {} for p in PERIODS})[period]
        if week in bucket:
            raise ValueError(f"Line {line}: duplicate segment/week")
        windows[period].add(week)
        bucket[week] = (visits, accepted, spend)
    if not all(windows.values()) or max(windows["before"]) >= min(windows["after"]):
        raise ValueError("Missing, overlapping or reversed comparison windows")
    if any(set(group[p]) != windows[p] for group in data.values() for p in PERIODS):
        raise ValueError("Missing segment/week: missing observations are not zeros")
    devices = sorted({key[0] for key in data})
    device_totals = {
        d: {p: summarize(row for key, group in data.items() if key[0] == d
                         for row in group[p].values()) for p in PERIODS}
        for d in devices
    }
    segment_totals = {key: {p: describe(group[p]) for p in PERIODS} for key, group in data.items()}
    decomposition = {}
    for device, totals in device_totals.items():
        segments = [group for key, group in segment_totals.items() if key[0] == device]
        if any(not group[p]["totals"]["visits"] for group in segments for p in PERIODS):
            continue
        fixed_mix = 100 * sum(
            group["before"]["totals"]["visits"] / totals["before"]["visits"]
            * group["after"]["totals"]["accepted_visits"] / group["after"]["totals"]["visits"]
            for group in segments
        )
        before, after = (
            100 * totals[p]["accepted_visits"] / totals[p]["visits"] for p in PERIODS
        )
        decomposition[device] = {
            "after_cr_at_before_mix_pct": round(fixed_mix, 4),
            "within_segment_change_at_before_mix_pp": round(fixed_mix - before, 4),
            "mix_change_at_after_rates_pp": round(after - fixed_mix, 4),
            "total_change_pp": round(after - before, 4),
        }
    return {
        "weeks_per_period": {p: len(value) for p, value in windows.items()},
        "same_window_length": len(windows["before"]) == len(windows["after"]),
        "devices": device_totals,
        "segments": [{**dict(zip(DIMENSIONS, key)), **segment_totals[key]}
                     for key in sorted(segment_totals)],
        "descriptive_decomposition": decomposition,
        "limits": [
            "Descriptive standardization; not a causal or seasonality estimate.",
            "Comparable goal, attribution, traffic definitions and coverage must be checked in the source brief.",
            "Matched segment trends and economics inform a decision. These numbers do not authorize a pause.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv")
    args = parser.parse_args()
    try:
        output = analyze(args.csv)
    except (ValueError, OSError, ArithmeticError) as error:
        parser.exit(2, str(error) + "\n")
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()
