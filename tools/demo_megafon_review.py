"""Demonstrate recording and invalidation of a simulated human decision."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--choice", choices=("pilot", "revise", "observe", "stop"), required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        runs = work / "runs"
        runs.mkdir()
        for name in ("state.json", "decision.md"):
            shutil.copyfile(ROOT / "continuation/case/baseline" / name, runs / name)
        destination = work / "update/recruitment.json"
        destination.parent.mkdir()
        # An isolated demonstration; the person running the command supplies the choice.
        destination.write_text('{"kind":"synthetic_initial_plan","eligible_families_per_week":546}', encoding="utf-8")
        command = [sys.executable, str(ROOT / "tools/decision_card.py"), str(work)]
        print("1. Учебный выбор для исходного сценария", flush=True)
        subprocess.run(command + [
            "record", "--gate", "Q1", "--choice", args.choice, "--owner", "Демонстрация: роль руководителя",
            "--rationale", "Учебный выбор для иллюстрации пересмотра", "--metric", "Темп набора семей",
            "--review-on", "2027-06-30", "--stop-if", "Не хватает данных, согласий или QA",
        ], check=True)
        shutil.copyfile(ROOT / "continuation/case/update/recruitment.json", destination)
        print("2. Новый вход: 150 семей в неделю. Прежний текст решения не менялся.", flush=True)
        subprocess.run(command + ["show"], check=True)
        print("Исходные материалы не изменены. Учебная карточка существует только при этой проверке.")


if __name__ == "__main__":
    main()
