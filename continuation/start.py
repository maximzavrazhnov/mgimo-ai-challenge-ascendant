"""Run the second MegaFon demonstration in an isolated copy of its input files."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "case"
OUTPUTS = ("decision-v2.md", "revision.json", "metrics.json")


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def hashes(case):
    return {str(f.relative_to(case)): hashlib.sha256(f.read_bytes()).hexdigest()
            for folder in ("baseline", "demo", "update", "tools")
            for f in sorted((case / folder).rglob("*"))
            if f.is_file() and "__pycache__" not in f.parts}


def check_baseline(case, input_hashes):
    attempts = load(case / "baseline/progress.json")["attempts"]["agent-megafon"]
    first = attempts[0]
    recorded = load(case / "baseline/results.json")
    if first.get("complete") is not True or [first.get("result")] != recorded:
        raise ValueError("Baseline run metadata does not match.")
    for name in ("decision.md", "state.json"):
        if input_hashes[str(Path("baseline") / name)] != first["hashes"][name]:
            raise ValueError(f"Baseline file changed: {name}")


def events(path):
    data = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                data.append(row)
        except ValueError:
            continue
    return data


def verify_results(case, expected, trace):
    path = case / "results"
    if not (path / "decision-v2.md").read_text(encoding="utf-8-sig").strip():
        raise ValueError("Empty revision decision.")
    actual = load(path / "metrics.json")
    revision = load(path / "revision.json")
    if actual != expected or revision.get("metrics") != expected:
        raise ValueError("Revision metrics do not match the calculator.")
    if revision.get("packet_id") != expected["packet_id"] or revision.get("human_approval") != "pending":
        raise ValueError("Incorrect packet ID or approval status.")
    for name in ("previous", "current"):
        if not isinstance(revision.get(name), str) or not revision[name].strip():
            raise ValueError(f"Missing or invalid field: {name}")
    for name in ("changed", "unchanged"):
        value = revision.get(name)
        if not isinstance(value, list) or not value or not all(isinstance(x, str) and x.strip() for x in value):
            raise ValueError(f"Missing or invalid list: {name}")
    if not any(e.get("type") == "turn.completed" for e in trace):
        raise ValueError("No completed turn in the Codex log.")
    for event in trace:
        item = event.get("item", {})
        if (event.get("type") == "item.completed" and item.get("type") == "command_execution"
                and item.get("exit_code") == 0 and "recruitment.py" in str(item.get("command", ""))):
            return
    raise ValueError("The Codex log does not show a successful calculator call.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify data and calculator without using Codex")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    original_hashes = hashes(SOURCE)
    check_baseline(SOURCE, original_hashes)
    expected = runpy.run_path(str(SOURCE / "tools/recruitment.py"))["calculate"]()
    if args.check:
        print(json.dumps(expected, ensure_ascii=False, indent=2))
        print("CHECK OK: baseline and calculator verified. No model run.")
        return 0

    binary = shutil.which("codex")
    if not binary:
        parser.error("Codex CLI is not on PATH. Run codex --version and codex login status.")
    run = ROOT / ("run-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    case = run / "case"
    shutil.copytree(SOURCE, case, ignore=shutil.ignore_patterns("__pycache__", "results"))
    (case / "results").mkdir()
    prompt = ROOT / "prompt.txt"
    shutil.copyfile(prompt, run / "prompt.txt")
    command = [binary, "exec", "--ephemeral", "--skip-git-repo-check",
               "--sandbox", "workspace-write", "--json", "-C", str(case),
               "-c", 'approval_policy="never"',
               "-c", "sandbox_workspace_write.network_access=false", "-"]
    print(f"[1/1] Starting a new Codex session. Logs: {run}", flush=True)
    started = time.monotonic()
    stdout = run / "codex.jsonl"
    error = None
    exit_status = None
    with stdout.open("wb") as out, (run / "codex.stderr.log").open("wb") as err:
        try:
            process = subprocess.run(command, input=prompt.read_bytes(), stdout=out, stderr=err,
                                     timeout=args.timeout)
            exit_status = process.returncode
            if exit_status:
                error = f"Codex CLI exited with code {exit_status}."
        except subprocess.TimeoutExpired:
            error = f"Codex CLI timed out after {args.timeout} seconds."
        except OSError as exc:
            error = str(exc)
    elapsed = round(time.monotonic() - started, 2)
    trace = events(stdout)
    preserved = hashes(case) == original_hashes and hashes(SOURCE) == original_hashes
    if not preserved:
        error = "Input files changed; this run is not accepted."
    if error is None:
        try:
            verify_results(case, expected, trace)
        except (OSError, TypeError, AttributeError, ValueError) as exc:
            error = str(exc)
    save(run / "summary.json", {
        "status": "completed" if error is None else "failed",
        "elapsed_seconds": elapsed,
        "exit_status": exit_status,
        "error": error,
        "original_input_hashes": original_hashes,
        "input_files_unchanged": preserved,
        "usage": [e["usage"] for e in trace if e.get("type") == "turn.completed" and "usage" in e],
    })
    if error:
        print(f"INCOMPLETE: {error} See {run / 'codex.stderr.log'} and {stdout}.", file=sys.stderr)
        return 1

    archive = run / "megafon-update-result.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zip_out:
        for name in OUTPUTS:
            zip_out.write(case / "results" / name, name)
        zip_out.write(run / "summary.json", "summary.json")
    print(f"Saved revision: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
