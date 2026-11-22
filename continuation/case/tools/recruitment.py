"""Derive the feasible sample and timeline from version 1 and the new packet."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def calculate():
    pilot = read("baseline/model-result.json")["pilot"]
    params = read("demo/megafon/assumptions.json")["pilot_assumptions"]
    update = read("update/recruitment.json")
    target = pilot["total_families"]
    weekly = update["eligible_families_per_week"]
    weeks = params["recruitment_weeks"]
    followup = pilot["observation_days_after_last_inclusion"]
    if any(type(value) is not int or value <= 0 for value in (target, weekly, weeks, followup)):
        raise ValueError("Recruitment inputs must be positive integers")
    return {
        "packet_id": update["id"],
        "kind": update["kind"],
        "target_families": target,
        "old_weekly_plan": pilot["required_unique_families_per_week"],
        "eligible_families_per_week": weekly,
        "planned_recruitment_weeks": weeks,
        "families_in_planned_window": weekly * weeks,
        "shortfall_families": max(0, target - weekly * weeks),
        "recruitment_weeks_needed": (target + weekly - 1) // weekly,
        "followup_days_after_last_family": followup,
        "effect_observed": update["effect_observed"],
    }


if __name__ == "__main__":
    import sys
    filename = Path(sys.argv[1]) if len(sys.argv) == 2 else None
    result = json.dumps(calculate(), ensure_ascii=False, indent=2) + "\n"
    if filename:
        filename.write_text(result, encoding="utf-8")
    else:
        print(result, end="")
