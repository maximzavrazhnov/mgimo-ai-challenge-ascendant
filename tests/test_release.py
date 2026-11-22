import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import decision_card
import operator_model
import run_comparison
from prepare_eval import prepare


class OperatorChecks(unittest.TestCase):
    def test_cash_flow_targets_and_unique_recruitment(self):
        inputs = json.loads((ROOT / "demo/megafon/assumptions.json").read_text(encoding="utf-8"))
        report = operator_model.model(inputs)
        main, adverse = (report["scenarios"][k] for k in ("main", "adverse"))
        self.assertEqual(main["prediction"]["profit_rub"], 280770000)
        self.assertEqual(adverse["prediction"]["connected_families"], 8450)
        self.assertEqual(main["missing_paid_number_months_for_target"], 8460)
        self.assertIsNone(main["payback_quarter_after_last_positive_investment"])
        self.assertEqual(report["pilot"]["required_unique_families_per_week"], 546)
        inputs["scenarios"]["main"]["channels"]["app"]["unique_reached"] = 100000
        with self.assertRaisesRegex(ValueError, "unique reach"):
            operator_model.model(inputs)


class ResumeChecks(unittest.TestCase):
    def test_only_incomplete_stage_retried_and_first_state_is_preserved(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root / "inputs")
            progress = {"attempts": {}}

            def fake_launch(root, arm, case, prompt, binary, model, timeout, attempt):
                calls.append((case, attempt))
                workspace = root / f"{arm}-{case}"
                runs = workspace / "runs"
                runs.mkdir(exist_ok=True)
                if case == "a":
                    (runs / "decision.md").write_text("phase A", encoding="utf-8")
                else:
                    self.assertEqual(json.loads((runs / "state.json").read_text())["version"], 1)
                    self.assertEqual((workspace / "demo/update").is_dir(), case == "update-1")
                    self.assertEqual((workspace / "demo/alternative-update").is_dir(), case == "update-2")
                    (runs / "update.md").write_text("update", encoding="utf-8")
                (runs / "state.json").write_text(json.dumps({"version": 1 if case == "a" else 2}))
                return {"case": case, "exit_status": "interrupted" if (case, attempt) == ("update-1", 1) else 0,
                        "answer_written": True, "state_written": True, "state_changed": True}

            with patch.object(run_comparison, "launch", fake_launch):
                self.assertEqual(run_comparison.execute(root, ["a"], ["agent"], "", None, 1, progress), 130)
                checkpoint = json.loads((root / "progress.json").read_text(encoding="utf-8"))
                self.assertEqual(run_comparison.execute(root, ["a"], ["agent"], "", None, 1, checkpoint), 0)
                self.assertTrue((root / "partial/agent-update-1/2/runs/update.md").is_file())
                self.assertEqual(calls, [("a", 1), ("update-1", 1), ("update-1", 2), ("update-2", 1)])
                (root / "agent-a/runs/decision.md").write_text("unexpected change")
                with self.assertRaisesRegex(ValueError, "Saved artifacts changed"):
                    run_comparison.execute(root, ["a"], ["agent"], "", None, 1, checkpoint)

    def test_no_reference_or_saved_results_in_partner_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "inputs"
            prepare(root)
            stage = root / "megafon-eval"
            self.assertTrue((stage / "tools/operator_model.py").is_file())
            self.assertTrue((stage / "demo/megafon/public-source.md").is_file())
            self.assertFalse((stage / "evidence").exists())
            self.assertFalse((stage / "docs").exists())


class HumanDecisionChecks(unittest.TestCase):
    def test_updated_analysis_requires_a_new_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "runs"
            runs.mkdir()
            (runs / "state.json").write_text('{"version": 1}')
            (runs / "decision.md").write_text("recommend pilot")
            card = {"analysis_sha256": decision_card.signature(root)}
            self.assertEqual(decision_card.status(root, card), "current")
            (runs / "update.md").write_text("new evidence")
            self.assertEqual(decision_card.status(root, card), "needs_review")


    def test_input_change_requires_review_before_agent_updates_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runs").mkdir()
            (root / "update").mkdir()
            (root / "runs/state.json").write_text('{"version": 1}')
            (root / "runs/decision.md").write_text("recommend pilot")
            packet = root / "update/recruitment.json"
            packet.write_text('{"families_per_week": 546}')
            card = {"analysis_sha256": decision_card.signature(root)}
            self.assertEqual(decision_card.status(root, card), "current")
            packet.write_text('{"families_per_week": 150}')
            self.assertEqual(decision_card.status(root, card), "needs_review")
