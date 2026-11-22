"""Run a local Codex comparison on synthetic inputs, optionally preparing only."""
import argparse
import json
import hashlib
from pathlib import Path
from shutil import copytree, ignore_patterns, which
import subprocess
import time

from prepare_eval import prepare


COMMON = (
    "Работай только с файлами текущей рабочей папки; не просматривай родительские "
    "и соседние папки, не обращайся к сети, не меняй входные данные. Если нужен "
    "недоступный источник, отметь это. Используй доступные инструменты по необходимости. "
    "Опиши основания, альтернативы, продуктовые и коммуникационные действия и способ проверки. "
    "Сохрани решение в runs/decision.md и состояние для продолжения в runs/state.json. "
    "Ответ на русском; не более 750 слов."
)
PROMPTS = {
    "a": "Кликов столько же, а в отчёте меньше заявок. Что менять первым? "
         "Может, сократим число обязательных полей и дадим рассчитать цену до отправки? ",
    "update": "Прочитай сохранённое состояние. Используй новый пакет материалов в demo/. "
              "Что из предыдущих выводов сохраняется, а что меняется? "
              "Запиши новое решение дополнительно в runs/update.md и обнови состояние. ",
    "traffic": "Возьми запрос руководителя из demo/traffic-review/brief.md. "
               "На основе файлов скажи, что делать сейчас и какие данные могут изменить решение. ",
    "megafon": (
        "Возьми задачу из demo/megafon/brief.md. Проверь сценарии командой "
        "python tools/operator_model.py demo/megafon/assumptions.json. "
        "Подготовь один документ из пяти частей, как указано в брифе. "
        "Учёт активных групп и активаций веди раздельно. Не выдавай допущения за эффект. "
        "Покажи основной и менее благоприятный прогноз по пяти показателям, "
        "связь целей с охватом, границу окупаемости, условия пилота и решения Q1/Q2. "
        "Публичный источник из пакета уже сохранён как выдержка; укажи, если его не открывал."
    ),
}


def select_cases(scenario):
    return {"all": ["a", "traffic"], "paired": ["a"],
            "traffic": ["traffic"], "megafon": ["megafon"]}[scenario]


def generate(root, scenario, arms=("agent", "baseline")):
    root.mkdir()
    prepare(root / "inputs")
    (root / "logs").mkdir()
    cases = select_cases(scenario)
    for arm in arms:
        excludes = ignore_patterns("AGENTS.md", "workflow.md") if arm == "baseline" else None
        for case in cases:
            source = {"a": "stage-a", "traffic": "traffic-eval", "megafon": "megafon-eval"}[case]
            copytree(root / "inputs" / source, root / f"{arm}-{case}", ignore=excludes)
    return cases


def check_state(path):
    try:
        return isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
    except (OSError, ValueError):
        return False


def launch(root, arm, case, prompt, binary, model, timeout, attempt=None):
    key = f"{arm}-{case}"
    workspace = root / key
    logs = root / "logs" if attempt is None else root / "logs" / key / str(attempt)
    logs.mkdir(parents=True, exist_ok=True)
    events = logs / f"{key}.jsonl"
    command = [
        binary, "exec", "--ephemeral", "--skip-git-repo-check",
        "-s", "workspace-write", "-c", 'approval_policy="never"',
        "-c", "sandbox_workspace_write.network_access=false",
        "--json", "-C", str(workspace),
    ]
    if model:
        command += ["--model", model]
    command += ["-"]
    state = workspace / "runs/state.json"
    previous_state = state.read_bytes() if state.is_file() else None
    (logs / f"{key}.prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    started = time.monotonic()
    with events.open("w", encoding="utf-8") as out, (logs / f"{key}.stderr").open(
        "w", encoding="utf-8"
    ) as err:
        try:
            proc = subprocess.run(command, input=prompt, encoding="utf-8",
                                  stdout=out, stderr=err, timeout=timeout)
            status = proc.returncode
        except subprocess.TimeoutExpired:
            status = "timeout"
        except KeyboardInterrupt:
            status = "interrupted"
        except OSError as error:
            err.write(str(error) + "\n")
            status = "launch_error"
    usage = []
    for line in events.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage.append(event["usage"])
    answer = workspace / "runs" / ("update.md" if case.startswith("update") else "decision.md")
    return {
        "arm": arm, "case": case, "exit_status": status,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "model_arg": model, "usage_reported": usage or None,
        "answer_written": answer.is_file() and answer.stat().st_size > 0,
        "state_written": check_state(state),
        "state_changed": state.is_file() and state.read_bytes() != previous_state,
    }


def run(root, cases, binary, model, timeout):
    results = []
    for case in cases:
        for arm in ("agent", "baseline"):
            record = launch(root, arm, case, PROMPTS[case] + COMMON, binary, model, timeout)
            results.append(record)
            if case != "a" or record["exit_status"] != 0 or not (
                record["answer_written"] and record["state_written"]
            ):
                continue
            for index in (1, 2):
                continuation = f"update-{index}"
                target = root / f"{arm}-{continuation}"
                copytree(root / f"{arm}-a", target, ignore=ignore_patterns("__pycache__"))
                copytree(root / "inputs" / f"packet-{index}", target, dirs_exist_ok=True)
                prompt = PROMPTS["update"] + COMMON.replace("runs/decision.md", "runs/update.md")
                results.append(launch(root, arm, continuation, prompt, binary, model, timeout))
    return results


def atomic_json(path, data):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def output_hashes(workspace, case):
    names = ("update.md" if case.startswith("update") else "decision.md", "state.json")
    return {name: hashlib.sha256((workspace / "runs" / name).read_bytes()).hexdigest()
            for name in names}


def execute(root, cases, arms, binary, model, timeout, progress):
    attempts = progress["attempts"]
    stages = [(arm, case) for case in cases for arm in arms]
    expanded = [(arm, task) for arm, case in stages
                for task in (("a", "update-1", "update-2") if case == "a" else (case,))]
    records = []
    for position, (arm, case) in enumerate(expanded, 1):
        key = f"{arm}-{case}"
        target = root / key
        history = attempts.setdefault(key, [])
        previous = history[-1] if history else {}
        if previous.get("complete"):
            if output_hashes(target, case) != previous["hashes"]:
                raise ValueError(f"Saved artifacts changed: {key}; start a new comparison")
            print(f"[{position}/{len(expanded)}] {key}: saved, skipping", flush=True)
            records.append(previous["result"])
            continue
        number = len(history) + 1
        if target.exists():
            archive = root / "partial" / key / str(number)
            archive.parent.mkdir(parents=True, exist_ok=True)
            target.rename(archive)
        entry = {"number": number, "complete": False}
        history.append(entry)
        atomic_json(root / "progress.json", progress)
        if case.startswith("update-"):
            copytree(root / f"{arm}-a", target, ignore=ignore_patterns("__pycache__"))
            copytree(root / "inputs" / ("packet-" + case[-1]), target, dirs_exist_ok=True)
            prompt = PROMPTS["update"] + COMMON.replace("runs/decision.md", "runs/update.md")
        else:
            source = {"a": "stage-a", "traffic": "traffic-eval", "megafon": "megafon-eval"}[case]
            excludes = ignore_patterns("AGENTS.md", "workflow.md", "megafon-workflow.md") if arm == "baseline" else None
            copytree(root / "inputs" / source, target, ignore=excludes)
            common = COMMON.replace("750 слов", "2000 слов") if case == "megafon" else COMMON
            prompt = PROMPTS[case] + common
        print(f"[{position}/{len(expanded)}] {key}: attempt {number}", flush=True)
        result = launch(root, arm, case, prompt, binary, model, timeout, attempt=number)
        entry["result"] = result
        entry["complete"] = result["exit_status"] == 0 and all(
            result[k] for k in ("answer_written", "state_written", "state_changed"))
        if entry["complete"]:
            entry["hashes"] = output_hashes(target, case)
        records.append(result)
        atomic_json(root / "progress.json", progress)
        atomic_json(root / "results.json", records)
        if not entry["complete"]:
            print(f"Incomplete: {key} ({result['exit_status']}). See logs/{key}/{number}; retry with --resume.")
            return 130 if result["exit_status"] == "interrupted" else 1
    atomic_json(root / "results.json", records)
    print(f"Saved run evidence: {root / 'results.json'}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New evaluation directory, or existing with --resume")
    parser.add_argument("--scenario", choices=("paired", "traffic", "all", "megafon"))
    parser.add_argument("--arm", choices=("agent", "baseline", "both"))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--model", help="Optional identical Codex model for both variants")
    parser.add_argument("--timeout", type=int, default=180, help="Per run, in seconds")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    if args.prepare_only and args.resume:
        parser.error("--prepare-only and --resume cannot be combined")
    binary = which("codex")
    if not args.prepare_only and not binary:
        parser.error("Codex executable unavailable; --prepare-only needs only Python")
    destination = args.destination.resolve()
    try:
        if args.resume:
            progress = json.loads((destination / "progress.json").read_text(encoding="utf-8"))
            if progress.get("version") != 1:
                raise ValueError("Unknown progress format")
            scenario, arm, model = (progress[k] for k in ("scenario", "arm", "model"))
            if any(v is not None and v != saved for v, saved in
                   ((args.scenario, scenario), (args.arm, arm), (args.model, model))):
                raise ValueError("Resume must use the original scenario, arm and model")
        else:
            if destination.exists():
                raise ValueError("Destination already exists; choose a new name or use --resume")
            scenario, arm, model = args.scenario or "paired", args.arm or "both", args.model
            destination.mkdir()
            prepare(destination / "inputs")
            (destination / "logs").mkdir()
            progress = {"version": 1, "scenario": scenario, "arm": arm, "model": model, "attempts": {}}
            atomic_json(destination / "progress.json", progress)
        if args.prepare_only:
            print(f"Prepared local evaluation: {destination / 'inputs'}")
            return 0
        arms = ("agent", "baseline") if arm == "both" else (arm,)
        return execute(destination, select_cases(scenario), arms, binary, model, args.timeout, progress)
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
