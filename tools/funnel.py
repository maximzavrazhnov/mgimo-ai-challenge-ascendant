"""Reproducible calculations for the demo CSV and a local actions ledger."""
import argparse
import csv
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sys


PERIODS = ("before", "after")
COUNTS = (
    "impressions", "clicks", "visits", "bounces",
    "form_start_visits", "reported_goal_visits",
)
FIELDS = {"period", "start", "end", "device", "spend_rub", "goal_label", *COUNTS}


def rows(path, required):
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)) or required - set(columns):
            raise ValueError(f"{path}: missing or duplicate headers")
        for line, row in enumerate(reader, 2):
            if None in row or any(row.get(key) in (None, "") for key in required):
                raise ValueError(f"{path}:{line}: missing value or extra cell")
            yield line, row


def ratio(numerator, denominator, scale=100):
    if not denominator:
        return None
    return round(float(numerator * scale / denominator), 4)


def analyze(path, update_path=None):
    grouped = {period: {} for period in PERIODS}
    windows, labels = {}, {}
    for line, row in rows(path, FIELDS):
        period, segment = row["period"], row["device"]
        if period not in grouped or segment in grouped[period]:
            raise ValueError(f"{path}:{line}: unknown period or duplicate period/device")
        start, end = date.fromisoformat(row["start"]), date.fromisoformat(row["end"])
        if end < start or windows.get(period, (start, end)) != (start, end):
            raise ValueError(f"{path}:{line}: invalid or inconsistent dates")
        windows[period] = start, end
        if labels.get(period, row["goal_label"]) != row["goal_label"]:
            raise ValueError(f"{path}:{line}: multiple goal labels in one period")
        labels[period] = row["goal_label"]
        values = {key: int(row[key]) for key in COUNTS}
        spend = Decimal(row["spend_rub"])
        if any(v < 0 for v in values.values()) or not spend.is_finite() or spend < 0:
            raise ValueError(f"{path}:{line}: negative count or invalid spend")
        if (
            values["bounces"] > values["visits"]
            or values["form_start_visits"] > values["visits"]
            or values["reported_goal_visits"] > values["visits"]
        ):
            raise ValueError(f"{path}:{line}: visit subset exceeds visits")
        grouped[period][segment] = {**values, "spend_rub": spend, "source_line": line}
    if not all(grouped.values()) or grouped["before"].keys() != grouped["after"].keys():
        raise ValueError("Both periods must have the same non-empty device segments")
    if windows["before"][1] >= windows["after"][0]:
        raise ValueError("Periods overlap or are out of order")
    days = {p: (end - start).days + 1 for p, (start, end) in windows.items()}
    totals = {}
    for period, segments in grouped.items():
        t = {key: sum(r[key] for r in segments.values()) for key in COUNTS}
        spend = sum(r["spend_rub"] for r in segments.values())
        totals[period] = {
            **t, "spend_rub": str(spend), "days": days[period],
            "goal_label": labels[period], "source_lines": [r["source_line"] for r in segments.values()],
            "ctr_pct": ratio(t["clicks"], t["impressions"]),
            "cpc_rub": ratio(spend, t["clicks"], 1),
            "bounce_pct": ratio(t["bounces"], t["visits"]),
            "form_start_per_visit_pct": ratio(t["form_start_visits"], t["visits"]),
            "reported_goal_per_visit_pct": ratio(t["reported_goal_visits"], t["visits"]),
        }
    output = {
        "periods": totals,
        "same_duration": days["before"] == days["after"],
        "goal_comparability": "unknown",
        "accepted_application_comparison": None,
        "accepted_application_by_device": None,
        "warnings": [
            "Goal label alone does not establish equivalent event definitions.",
            "Visits and ad clicks are from different measurement systems, not necessarily a nested cohort.",
        ],
    }
    if days["before"] != days["after"]:
        output["warnings"].append("Periods have unequal durations; raw counts are not directly comparable.")
    if not update_path:
        return output
    updated = json.loads(Path(update_path).read_text(encoding="utf-8"))
    goals, accepted = updated["goals"], updated["accepted_by_period"]
    if set(goals) != set(PERIODS) or set(accepted) != set(PERIODS) or not updated.get("source"):
        raise ValueError("Update must document both periods and its source")
    if any(not isinstance(goal, str) or not goal.strip() for goal in goals.values()):
        raise ValueError("Update goal definitions must be non-empty strings")
    for period, counts in accepted.items():
        if set(counts) != grouped[period].keys():
            raise ValueError(f"{period}: acceptance counts do not cover the same device segments")
        if any(type(n) is not int or not 0 <= n <= grouped[period][d]["form_start_visits"]
               for d, n in counts.items()):
            raise ValueError(f"{period}: invalid acceptance counts")
        if goals[period] == "server_accepted_application" and any(
            n != grouped[period][d]["reported_goal_visits"] for d, n in counts.items()
        ):
            raise ValueError(f"{period}: reported and reconstructed accepted counts conflict")
        if goals[period] == "form_submit_attempt" and any(
            n > grouped[period][d]["reported_goal_visits"] for d, n in counts.items()
        ):
            raise ValueError(f"{period}: accepted applications exceed visits with submission attempts")
    output["goal_comparability"] = "documented_same_definition" if goals["before"] == goals["after"] else "different_definitions"
    output["goal_definitions"] = goals
    output["accepted_application_comparison"] = {
        period: {
            "accepted_visits": sum(counts.values()),
            "cr_pct": ratio(sum(counts.values()), totals[period]["visits"]),
            "accepted_per_form_start_pct": ratio(sum(counts.values()), totals[period]["form_start_visits"]),
        }
        for period, counts in accepted.items()
    }
    output["accepted_application_by_device"] = {}
    for device in sorted(grouped["before"]):
        details = {}
        for period in PERIODS:
            row = grouped[period][device]
            count = accepted[period][device]
            details[period] = {
                "accepted_visits": count,
                "visits": row["visits"],
                "form_start_visits": row["form_start_visits"],
                "cr_pct": ratio(count, row["visits"]),
                "source_line": row["source_line"],
            }
        before, after = details["before"], details["after"]
        if before["visits"] and after["visits"]:
            delta_pp = round(100 * (after["accepted_visits"] / after["visits"]
                                   - before["accepted_visits"] / before["visits"]), 4)
        else:
            delta_pp = None
        output["accepted_application_by_device"][device] = {
            **details,
            "accepted_delta": after["accepted_visits"] - before["accepted_visits"],
            "cr_delta_pp": delta_pp,
        }
    output["update_source"] = updated["source"]
    return output


def history(path, query):
    required = {"id", "action", "stage", "scope", "status", "evidence", "result"}
    statuses = {"live", "tested", "rejected"}
    key = query.strip().casefold()
    if not key:
        raise ValueError("Action query must not be empty")
    matches = []
    for line, row in rows(path, required):
        if row["status"] not in statuses:
            raise ValueError(f"{path}:{line}: unknown history status")
        alternatives = (row.get("aliases") or "").split("|")
        keys = {text.strip().casefold() for text in (row["id"], *alternatives) if text.strip()}
        if key in keys:
            matches.append({**row, "line": line})
    return {
        "query": query,
        "status": "matched" if matches else "not_found_in_available_history",
        "matches": matches,
        "limits": "Exact IDs and declared aliases only; assess semantic matches and differences separately.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    a = commands.add_parser("analyze")
    a.add_argument("csv")
    a.add_argument("--update")
    h = commands.add_parser("history")
    h.add_argument("csv")
    h.add_argument("action_id")
    args = parser.parse_args()
    try:
        result = analyze(args.csv, args.update) if args.command == "analyze" else history(args.csv, args.action_id)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, csv.Error) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
