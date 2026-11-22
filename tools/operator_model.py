"""Recalculate planning scenarios from declared assumptions; standard library only."""
import argparse
import json
import math
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from statistics import NormalDist


def number(x, cap=None):
    if isinstance(x, bool) or not isinstance(x, (int, float, Decimal)):
        raise ValueError("A numeric assumption is required")
    value = Decimal(str(x))
    if not value.is_finite() or value < 0 or (cap is not None and value > cap):
        raise ValueError("An assumption is outside its allowed range")
    return value


def rounded(x):
    return int(x.to_integral_value(rounding=ROUND_HALF_UP))


def count(x):
    value = number(x)
    if value != value.to_integral_value():
        raise ValueError("Counts and roubles must be integers")
    return int(value)


def series(seq, size):
    if len(seq) != size:
        raise ValueError(f"Expected {size} periods")
    return [count(x) for x in seq]


def trial_size(control, treatment, alpha, power):
    """Normal approximation: 1 eligible number per independently assigned family."""
    if not 0 < treatment < control < 1 or not 0 < alpha < 1 or not 0.5 < power < 1:
        raise ValueError("Invalid trial assumptions")
    mid = (control + treatment) / 2
    q = NormalDist().inv_cdf
    return math.ceil(((q(1 - alpha / 2) * math.sqrt(2 * mid * (1-mid)) +
                       q(power) * math.sqrt(control * (1-control) + treatment * (1-treatment)))
                      / (control-treatment)) ** 2)


def model(data):
    base, goal = data["without_change"], data["targets"]
    keys = ("profit_rub", "active_families", "connected_families", "multi_number_owners")
    base = {k: count(base[k]) for k in keys} | {"activation_14d": number(base["activation_14d"], 1)}
    goal = {k: count(goal[k]) for k in keys} | {"activation_14d": number(goal["activation_14d"], 1)}
    reachable_families = count(data["reachable_families"])
    reachable_owners = count(data["reachable_owners"])
    rate = count(data["profit_per_paid_number_month_rub"])
    if not rate or not reachable_families or not reachable_owners:
        raise ValueError("Rates and eligible bases must be positive")
    trial = data["pilot_assumptions"]
    required = trial_size(*(float(number(trial[k], 1)) for k in ("control", "treatment", "alpha", "power")))
    weeks = count(trial["recruitment_weeks"])
    if not weeks:
        raise ValueError("Recruitment weeks must be positive")
    output = {
        "kind": "illustrative_assumptions_not_observed",
        "pilot": {"families_per_arm": required, "total_families": 2 * required,
                  "required_unique_families_per_week": math.ceil(2 * required / weeks),
                  "observation_days_after_last_inclusion": 7},
        "scenarios": {},
    }
    for name, s in data["scenarios"].items():
        channels = {}
        reach = 0
        for k, c in s["channels"].items():
            seen = count(c["unique_reached"])
            reach += seen
            rates = [number(c[field], 1) for field in ("control_creation", "treatment_creation")]
            channels[k] = Decimal(seen) * (rates[1] - rates[0])
        if reach > reachable_families:
            raise ValueError("Total unique reach exceeds the family base")
        if any(x < 0 for x in channels.values()):
            raise ValueError("Negative acquisition lift is not supported; model it as attrition")
        created = sum(channels.values(), Decimal(0))
        accepted = created * number(s["invitation_acceptance"], 1)
        new_end = rounded(accepted * number(s["new_connections_retained_to_year_end"], 1))
        retained = count(s["retained_existing_families"])
        if retained > count(data["starting_families"]):
            raise ValueError("Existing family uplift exceeds starting stock")
        connected = base["connected_families"] + new_end + retained
        owners = base["multi_number_owners"]  # Second audience deferred in this plan.
        if connected > reachable_families or owners > reachable_owners:
            raise ValueError("Connections exceed accessible base")
        months = series(s["incremental_paid_number_months_by_month"], 12)
        cost = series(s["direct_cost_by_quarter_rub"], 4)
        investments = s.get("investment_by_quarter_rub")
        if investments is not None:
            investments = series(investments, 4)
        quarters = [rate * sum(months[i:i+3]) - cost[i//3] for i in range(0, 12, 3)]
        net, cumulative_investment = 0, 0
        payback = None
        for i, profit in enumerate(quarters):
            net += profit
            if investments is not None:
                cumulative_investment += investments[i]
                if (payback is None and cumulative_investment > 0 and
                        i >= max(j for j, x in enumerate(investments) if x) and net >= cumulative_investment):
                    payback = i + 1
        predicted = {
            "profit_rub": base["profit_rub"] + net,
            "active_families": rounded(Decimal(connected) * number(s["december_active_share"], 1)),
            "connected_families": connected,
            "multi_number_owners": owners,
            "activation_14d": number(s["q4_invitation_accepted_in_14d"], 1) *
            number(s["q4_qualifying_action_among_accepted"], 1),
        }
        target_months = max(0, int((Decimal(goal["profit_rub"] - base["profit_rub"] + sum(cost)) /
                                   rate).to_integral_value(rounding=ROUND_CEILING)))
        output["scenarios"][name] = {
            "prediction": predicted,
            "gap_to_target": {k: max(0, goal[k]-v) for k, v in predicted.items()},
            "increment_vs_without_change": {k: v-base[k] for k, v in predicted.items()},
            "unique_family_reach": reach, "incremental_creations_by_channel": channels,
            "incremental_accepted_invitations": accepted, "incremental_new_connected_at_year_end": new_end,
            "additional_existing_families_retained": retained,
            "family_coverage": Decimal(connected)/reachable_families,
            "owner_coverage": Decimal(owners)/reachable_owners,
            "incremental_paid_number_months": sum(months),
            "new_direct_cost_rub": sum(cost), "net_increment_by_quarter_rub": quarters,
            "max_total_development_repayable_this_year_rub": max(0, net),
            "paid_number_months_to_reach_profit_target": target_months,
            "missing_paid_number_months_for_target": max(0, target_months-sum(months)),
            "payback_quarter_after_last_positive_investment": payback,
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assumptions", type=Path)
    args = parser.parse_args()
    try:
        result = model(json.loads(args.assumptions.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as error:
        parser.exit(2, f"Invalid scenario: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
