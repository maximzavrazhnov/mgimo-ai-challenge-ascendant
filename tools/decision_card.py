"""Record a human decision linked to a specific version of analysis."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from run_comparison import atomic_json

# Watch known inputs as well as outputs so a changed input invalidates old approval
# even before the agent generates a new answer.
WATCHED_INPUTS = (
    "demo/megafon/brief.md", "demo/megafon/assumptions.json",
    "demo/megafon/public-source.md", "demo/megafon/cohorts-example.csv",
    "demo/megafon/costs-example.csv", "update/recruitment.json",
    "baseline/state.json", "runs/source-receipt.json",
)



def signature(workspace):
    runs = workspace / "runs"
    state_file = runs / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8-sig"))
    if not isinstance(state, dict) or not state:
        raise ValueError("Expected a non-empty analysis state")
    answer = runs / "update.md" if (runs / "update.md").is_file() else runs / "decision.md"
    if not answer.read_text(encoding="utf-8-sig").strip():
        raise ValueError("The decision document is empty")
    artifacts = [answer, state_file]
    artifacts.extend(workspace / name for name in WATCHED_INPUTS if (workspace / name).is_file())
    return {p.relative_to(workspace).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in artifacts}


def status(workspace, card):
    try:
        return "current" if card["analysis_sha256"] == signature(workspace) else "needs_review"
    except (OSError, ValueError):
        return "needs_review"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("workspace", type=Path, help="Case directory containing runs/")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("show", help="Check the recorded choice against the current analysis")
    save = commands.add_parser("record", help="Record a choice made by the human operator")
    save.add_argument("--gate", required=True, choices=("Q1", "Q2"))
    save.add_argument("--choice", required=True, choices=("pilot", "expand", "revise", "observe", "stop"))
    for field in ("owner", "rationale", "metric", "review-on", "stop-if"):
        save.add_argument("--" + field, required=True)
    args = p.parse_args()
    path = args.workspace / "runs/decision-card.json"
    try:
        if args.command == "show":
            previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            result = {"status": status(args.workspace, previous), "decision": previous} if previous else {"status": "pending"}
        else:
            allowed = {"Q1": {"pilot", "revise", "observe", "stop"}, "Q2": {"expand", "revise", "observe", "stop"}}
            if args.choice not in allowed[args.gate]:
                raise ValueError("Choice does not apply to this quarter")
            review = date.fromisoformat(args.review_on).isoformat()
            record = {k: getattr(args, k).strip() for k in ("owner", "rationale", "metric", "stop_if")}
            if not all(record.values()):
                raise ValueError("Owner, rationale, metric and stop condition cannot be empty")
            hashes = signature(args.workspace)
            if path.exists():
                versions = path.parent / "decision-card-versions"
                versions.mkdir(exist_ok=True)
                previous = path.read_bytes()
                key = hashlib.sha256(previous).hexdigest()[:16]
                (versions / (key + ".json")).write_bytes(previous)
            record.update(gate=args.gate, choice=args.choice, review_on=review,
                          recorded_at=datetime.now(timezone.utc).isoformat(), analysis_sha256=hashes)
            atomic_json(path, record)
            result = {"status": "current", "decision": record}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        p.exit(2, f"Decision card unavailable: {error}\n")


if __name__ == "__main__":
    main()
