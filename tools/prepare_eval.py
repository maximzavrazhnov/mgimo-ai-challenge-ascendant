"""Make physically separate input packages for a fresh-chat evaluation."""
import argparse
from pathlib import Path
from shutil import copy2


ROOT = Path(__file__).resolve().parents[1]
STAGE_A = (
    "AGENTS.md", "workflow.md", "tools/funnel.py",
    "demo/brief.md", "demo/funnel.csv", "demo/history.csv", "demo/landing.html",
    "templates/state.json", "templates/decision.md",
)
PACKETS = {
    "packet-1": ("demo/update/measurement-note.md", "demo/update/definitions.json"),
    "packet-2": (
        "demo/alternative-update/measurement-note.md",
        "demo/alternative-update/definitions.json",
        "demo/alternative-update/qa-traces.csv",
    ),
}


def copy_to(destination, names):
    for name in names:
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        copy2(ROOT / name, output)


def prepare(destination):
    # Never overwrite an earlier evaluation with saved work.
    destination.mkdir()
    initial = destination / "stage-a"
    copy_to(initial, STAGE_A)
    register = (ROOT / "demo/source-register.md").read_text(encoding="utf-8")
    start_register = "\n".join(
        line for line in register.splitlines()
        if not line.startswith(("| S7 |", "| S8 |"))
    )
    (initial / "demo/source-register.md").write_text(start_register + "\n", encoding="utf-8")
    for name, files in PACKETS.items():
        copy_to(destination / name, files)
    copy_to(destination / "traffic-eval", (
        "AGENTS.md", "workflow.md", "demo/traffic-review/brief.md",
        "demo/traffic-review/traffic.csv", "tools/funnel.py", "tools/segments.py",
        "templates/state.json", "templates/decision.md",
    ))
    copy_to(destination / "megafon-eval", (
        "AGENTS.md", "workflow.md", "megafon-workflow.md",
        "demo/megafon/brief.md", "demo/megafon/assumptions.json", "demo/megafon/public-source.md",
        "tools/operator_model.py", "tools/megafon_cohorts.py",
        "demo/megafon/cohorts-example.csv", "demo/megafon/costs-example.csv",
        "templates/state.json", "templates/decision.md",
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="Path to a new directory")
    args = parser.parse_args()
    try:
        prepare(args.destination)
    except OSError as error:
        parser.exit(2, f"{error}\n")
    print(f"Prepared under {args.destination}: stage-a, two update packets, traffic-eval, megafon-eval")


if __name__ == "__main__":
    main()
